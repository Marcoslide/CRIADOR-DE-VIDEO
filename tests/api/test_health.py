"""Testes de integração dos health checks — Definition of Done da Fase 1.

Requerem PostgreSQL, Redis e um worker Celery (`worker.celery_app`) reais e acessíveis
via as variáveis de ambiente de `.env` (ver README.md "Rodando sem Docker"). Não usam
mocks: o objetivo é provar que a fundação sobe de ponta a ponta de verdade.
"""

from collections.abc import AsyncIterator

import httpx
import pytest
from app.main import app

pytestmark = pytest.mark.requires_services


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
    e confirma que o check correspondente reporta erro real (regra ZERO FAKE) — e que o
    detail é sanitizado, nunca a exceção crua com host/porta internos."""
    from dhf_shared.config import Settings, get_settings

    broken_host, broken_port = "localhost", 1
    broken = Settings(redis_host=broken_host, redis_port=broken_port)
    monkeypatch.setattr("app.routers.health.get_settings", lambda: broken)

    response = await client.get("/health/ready")
    body = response.json()

    checks_by_name = {check["name"]: check for check in body["checks"]}
    redis_check = checks_by_name["redis"]
    assert redis_check["status"] == "error"
    assert redis_check["error_code"] == "connection_error"
    assert redis_check["detail"] == "Não foi possível conectar ao serviço."
    assert broken_host not in redis_check["detail"]
    assert str(broken_port) not in redis_check["detail"]
    assert body["ready"] is False

    get_settings.cache_clear()


async def test_readiness_logs_full_error_internally_even_though_response_is_sanitized(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """O detalhe sanitizado sai da resposta, mas o erro completo (incluindo host/porta)
    precisa continuar disponível para quem opera o sistema — via log estruturado."""
    from dhf_shared.config import Settings, get_settings

    broken_host, broken_port = "localhost", 1
    broken = Settings(redis_host=broken_host, redis_port=broken_port)
    monkeypatch.setattr("app.routers.health.get_settings", lambda: broken)

    await client.get("/health/ready")
    logged = capsys.readouterr().out
    assert broken_host in logged
    assert "health.redis_check_failed" in logged

    get_settings.cache_clear()


async def test_worker_health_round_trip(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/worker")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "celery_worker"
    assert body["status"] == "connected"
    assert "pong" in body["detail"]


async def test_worker_health_reports_timeout_when_round_trip_times_out(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simula o que celery.exceptions.TimeoutError real dispara quando
    AsyncResult.get(timeout=...) não recebe resposta a tempo (ex.: worker sem consumidor —
    o que aconteceu de verdade no 1º run do CI desta fase). Confirma que /health/worker
    reporta status="timeout" e error_code="timeout" de verdade, não o fallback genérico
    "internal_error" (celery.exceptions.TimeoutError não herda do TimeoutError embutido)."""
    import celery.exceptions

    class _FakeAsyncResult:
        def get(self, timeout: float) -> dict:
            raise celery.exceptions.TimeoutError("The operation timed out.")

    class _FakePing:
        def apply_async(self) -> _FakeAsyncResult:
            return _FakeAsyncResult()

    monkeypatch.setattr("app.routers.health.celery_ping", _FakePing())

    response = await client.get("/health/worker")
    body = response.json()

    assert body["status"] == "timeout"
    assert body["error_code"] == "timeout"
    assert body["detail"] == "A operação excedeu o tempo limite."
