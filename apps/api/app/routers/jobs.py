"""Job de diagnóstico real: API -> Redis -> worker -> backend de resultado."""

import asyncio
import uuid
from datetime import UTC, datetime

import redis.asyncio as redis_asyncio
from celery.result import AsyncResult
from dhf_schemas.jobs import DiagnosticJobStatus, DiagnosticJobSubmitted, JobState
from dhf_shared.celery_app import celery_app
from dhf_shared.celery_app import diagnostic_job as diagnostic_job_task
from dhf_shared.config import get_settings
from dhf_shared.errors import sanitize_error
from dhf_shared.logging import get_logger
from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool

router = APIRouter(prefix="/jobs", tags=["jobs"])
_logger = get_logger(service="api", component="diagnostic_jobs")

_STATE_MAP = {
    "PENDING": JobState.PENDING,
    "STARTED": JobState.STARTED,
    "SUCCESS": JobState.SUCCESS,
    "FAILURE": JobState.FAILURE,
}


def _job_marker(job_id: str) -> str:
    """Distingue um job nosso de um UUID arbitrário (Celery chama ambos de PENDING)."""
    return f"dhf:diagnostic-job:{job_id}"


@router.post("/diagnostic", response_model=DiagnosticJobSubmitted, status_code=202)
async def submit_diagnostic_job() -> DiagnosticJobSubmitted:
    triggered_at = datetime.now(UTC)
    job_id = str(uuid.uuid4())
    settings = get_settings()
    client = redis_asyncio.from_url(
        settings.redis_url,
        socket_connect_timeout=settings.redis_connect_timeout_s,
        socket_timeout=settings.redis_socket_timeout_s,
    )
    marker = _job_marker(job_id)
    try:
        # O marcador vem antes do publish; assim uma resposta 202 sempre é consultável.
        await client.set(marker, "1", ex=settings.diagnostic_job_ttl_s)
        await asyncio.wait_for(
            run_in_threadpool(
                diagnostic_job_task.apply_async,
                args=[triggered_at.isoformat()],
                task_id=job_id,
            ),
            timeout=8,
        )
    except Exception as exc:  # noqa: BLE001
        try:
            await client.delete(marker)
        except Exception:  # noqa: BLE001 - limpeza best-effort
            pass
        _logger.error("diagnostic_job.submit_failed", error=str(exc), error_type=type(exc).__name__)
        sanitized = sanitize_error(exc)
        raise HTTPException(status_code=503, detail=sanitized.message) from exc
    finally:
        await client.aclose()
    return DiagnosticJobSubmitted(job_id=job_id, triggered_at=triggered_at)


@router.get("/diagnostic/{job_id}", response_model=DiagnosticJobStatus)
async def get_diagnostic_job(job_id: uuid.UUID) -> DiagnosticJobStatus:
    job_id_text = str(job_id)
    settings = get_settings()
    client = redis_asyncio.from_url(
        settings.redis_url,
        socket_connect_timeout=settings.redis_connect_timeout_s,
        socket_timeout=settings.redis_socket_timeout_s,
    )
    try:
        if not await client.exists(_job_marker(job_id_text)):
            raise HTTPException(status_code=404, detail="job de diagnóstico não encontrado")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        _logger.error("diagnostic_job.lookup_failed", error=str(exc), error_type=type(exc).__name__)
        sanitized = sanitize_error(exc)
        raise HTTPException(status_code=503, detail=sanitized.message) from exc
    finally:
        await client.aclose()

    def _read_result() -> tuple[str, object]:
        result = AsyncResult(job_id_text, app=celery_app)
        state = result.state
        return state, result.result if state == "SUCCESS" else None

    try:
        raw_state, payload = await asyncio.wait_for(run_in_threadpool(_read_result), timeout=8)
    except Exception as exc:  # noqa: BLE001
        _logger.error("diagnostic_job.result_failed", error=str(exc), error_type=type(exc).__name__)
        sanitized = sanitize_error(exc)
        raise HTTPException(status_code=503, detail=sanitized.message) from exc

    state = _STATE_MAP.get(raw_state, JobState.UNKNOWN)
    if state != JobState.SUCCESS:
        return DiagnosticJobStatus(job_id=job_id_text, state=state, result=None)
    if not isinstance(payload, dict):
        raise HTTPException(status_code=500, detail="resultado do job em formato inesperado")
    return DiagnosticJobStatus(job_id=job_id_text, state=state, result=payload)
