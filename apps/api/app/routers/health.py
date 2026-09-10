"""Health checks reais — nenhum status aqui é hardcoded (regra ZERO FAKE).

- GET /health        liveness: o processo da API está de pé.
- GET /health/ready   readiness: Postgres e Redis respondem agora.
- GET /health/worker  round-trip real através do Celery (broker -> worker -> backend).
"""

import time
from datetime import UTC, datetime

import redis.asyncio as redis_asyncio
from dhf_schemas.health import ComponentCheck, HealthResponse, ReadinessResponse
from dhf_shared.celery_app import ping as celery_ping
from dhf_shared.config import get_settings
from dhf_shared.db import get_engine
from fastapi import APIRouter
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(status="ok", service="api", version="0.1.0", app_env=settings.app_env)


@router.get("/health/ready", response_model=ReadinessResponse)
async def readiness() -> ReadinessResponse:
    checks = [await _check_postgres(), await _check_redis()]
    ready = all(check.status == "connected" for check in checks)
    return ReadinessResponse(ready=ready, checks=checks, checked_at=datetime.now(UTC))


@router.get("/health/worker", response_model=ComponentCheck)
async def worker_health() -> ComponentCheck:
    start = time.perf_counter()

    def _round_trip() -> dict:
        result = celery_ping.apply_async()
        return result.get(timeout=5)

    try:
        payload = await run_in_threadpool(_round_trip)
        return ComponentCheck(
            name="celery_worker",
            status="connected",
            latency_ms=_elapsed_ms(start),
            detail=str(payload),
        )
    except Exception as exc:  # noqa: BLE001 - reportado ao cliente, não engolido
        return ComponentCheck(
            name="celery_worker",
            status="timeout" if "time" in str(exc).lower() else "error",
            latency_ms=_elapsed_ms(start),
            detail=str(exc),
        )


async def _check_postgres() -> ComponentCheck:
    start = time.perf_counter()
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return ComponentCheck(name="postgres", status="connected", latency_ms=_elapsed_ms(start))
    except Exception as exc:  # noqa: BLE001
        return ComponentCheck(
            name="postgres", status="error", latency_ms=_elapsed_ms(start), detail=str(exc)
        )


async def _check_redis() -> ComponentCheck:
    start = time.perf_counter()
    settings = get_settings()
    client = redis_asyncio.from_url(settings.redis_url)
    try:
        await client.ping()
        return ComponentCheck(name="redis", status="connected", latency_ms=_elapsed_ms(start))
    except Exception as exc:  # noqa: BLE001
        return ComponentCheck(
            name="redis", status="error", latency_ms=_elapsed_ms(start), detail=str(exc)
        )
    finally:
        await client.aclose()


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)
