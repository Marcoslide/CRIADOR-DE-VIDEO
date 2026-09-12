"""Job de diagnóstico — prova real de ponta a ponta: API enfileira no Redis, o worker
Celery consome e processa, a API consulta o resultado de volta. Não é um job de produção
(ver `docs/ARCHITECTURE.md` §16 Render Queue para isso) — é o encanamento mínimo que
comprova que API -> Redis -> Worker funciona de verdade, sem simular nada.
"""

from datetime import UTC, datetime

from celery.result import AsyncResult
from dhf_schemas.jobs import DiagnosticJobStatus, DiagnosticJobSubmitted, JobState
from dhf_shared.celery_app import celery_app
from dhf_shared.celery_app import diagnostic_job as diagnostic_job_task
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/jobs", tags=["jobs"])

_STATE_MAP = {
    "PENDING": JobState.PENDING,
    "STARTED": JobState.STARTED,
    "SUCCESS": JobState.SUCCESS,
    "FAILURE": JobState.FAILURE,
}


@router.post("/diagnostic", response_model=DiagnosticJobSubmitted, status_code=202)
async def submit_diagnostic_job() -> DiagnosticJobSubmitted:
    triggered_at = datetime.now(UTC)
    result = diagnostic_job_task.apply_async(args=[triggered_at.isoformat()])
    return DiagnosticJobSubmitted(job_id=result.id, triggered_at=triggered_at)


@router.get("/diagnostic/{job_id}", response_model=DiagnosticJobStatus)
async def get_diagnostic_job(job_id: str) -> DiagnosticJobStatus:
    result = AsyncResult(job_id, app=celery_app)
    state = _STATE_MAP.get(result.state, JobState.UNKNOWN)
    if state != JobState.SUCCESS:
        return DiagnosticJobStatus(job_id=job_id, state=state, result=None)
    payload = result.result
    if not isinstance(payload, dict):
        raise HTTPException(status_code=500, detail="resultado do job em formato inesperado")
    return DiagnosticJobStatus(job_id=job_id, state=state, result=payload)
