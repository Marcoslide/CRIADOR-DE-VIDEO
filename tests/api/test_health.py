"""Testes de integração dos health checks — Definition of Done da Fase 1.

Requerem PostgreSQL, Redis e um worker Celery (`worker.celery_app`) reais e acessíveis
via as variáveis de ambiente de `.env` (ver README.md "Rodando sem Docker"). Não usam
mocks: o objetivo é provar que a fundação sobe de ponta a ponta de verdade.
"""

from collections.abc import AsyncIterator

import httpx
import pytest
from app.main import app


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_health_liveness(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "api"


async def test_readiness_reports_real_postgres_and_redis(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()

    checks_by_name = {check["name"]: check for check in body["checks"]}
    assert set(checks_by_name) == {"postgres", "redis"}

    assert body["ready"] is True
    for check in checks_by_name.values():
        assert check["status"] == "connected"
        assert check["latency_ms"] is not None and check["latency_ms"] >= 0


async def test_readiness_reports_real_failure_when_redis_is_down(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Garante que a rota nunca finge sucesso: aponta o Redis para uma porta inexistente
    e confirma que o check correspondente reporta erro real (regra ZERO FAKE)."""
    from dhf_shared.config import Settings, get_settings

    broken = Settings(redis_host="localhost", redis_port=1)
    monkeypatch.setattr("app.routers.health.get_settings", lambda: broken)

    response = await client.get("/health/ready")
    body = response.json()

    checks_by_name = {check["name"]: check for check in body["checks"]}
    assert checks_by_name["redis"]["status"] == "error"
    assert checks_by_name["redis"]["detail"]
    assert body["ready"] is False

    get_settings.cache_clear()


async def test_worker_health_round_trip(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/worker")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "celery_worker"
    assert body["status"] == "connected"
    assert "pong" in body["detail"]
