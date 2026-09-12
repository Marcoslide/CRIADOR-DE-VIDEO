"""Teste de integração do job de diagnóstico — prova real de ponta a ponta API -> Redis ->
Worker. Requer Redis e um worker Celery reais consumindo a fila (ver README.md "Rodando
sem Docker"). Sem mocks: enfileira de verdade e espera o worker processar.
"""

import asyncio
import uuid
from datetime import datetime

import httpx
import pytest

pytestmark = pytest.mark.requires_services


def _parse(iso_value: str) -> datetime:
    return datetime.fromisoformat(iso_value.replace("Z", "+00:00"))


async def test_diagnostic_job_round_trips_through_redis_and_worker(
    client: httpx.AsyncClient,
) -> None:
    submit = await client.post("/jobs/diagnostic")
    assert submit.status_code == 202
    submitted = submit.json()
    job_id = submitted["job_id"]
    assert submitted["triggered_at"]

    body = None
    for _ in range(30):
        status_response = await client.get(f"/jobs/diagnostic/{job_id}")
        assert status_response.status_code == 200
        body = status_response.json()
        if body["state"] == "success":
            break
        await asyncio.sleep(0.5)
    else:
        pytest.fail(
            f"job {job_id} não completou a tempo (último estado: {body['state'] if body else '?'})"
        )

    assert body["result"]["status"] == "OK"
    # A API serializa o datetime original via Pydantic (sufixo "Z"); o worker recebeu o
    # mesmo instante já convertido para string por `datetime.isoformat()` puro (sufixo
    # "+00:00") antes de entrar na fila — formatos diferentes, mesmo instante.
    assert _parse(body["result"]["triggered_at"]) == _parse(submitted["triggered_at"])
    assert body["result"]["processed_at"]
    assert _parse(body["result"]["processed_at"]) >= _parse(body["result"]["triggered_at"])


async def test_nonexistent_diagnostic_job_returns_404(client: httpx.AsyncClient) -> None:
    response = await client.get(f"/jobs/diagnostic/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_malformed_diagnostic_job_id_returns_422(client: httpx.AsyncClient) -> None:
    response = await client.get("/jobs/diagnostic/not-a-uuid")
    assert response.status_code == 422


async def test_submit_reports_503_when_redis_is_unavailable(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dhf_shared.config import Settings

    monkeypatch.setattr(
        "app.routers.jobs.get_settings",
        lambda: Settings(redis_host="localhost", redis_port=1),
    )
    response = await client.post("/jobs/diagnostic")
    assert response.status_code == 503
    assert "localhost" not in response.json()["detail"]


async def test_failed_job_is_reported_without_leaking_result(
    client: httpx.AsyncClient,
) -> None:
    import redis.asyncio as redis_asyncio
    from dhf_shared.celery_app import celery_app
    from dhf_shared.config import get_settings

    job_id = str(uuid.uuid4())
    settings = get_settings()
    redis_client = redis_asyncio.from_url(settings.redis_url)
    try:
        await redis_client.set(f"dhf:diagnostic-job:{job_id}", "1", ex=60)
        celery_app.backend.store_result(job_id, RuntimeError("falha controlada"), state="FAILURE")

        response = await client.get(f"/jobs/diagnostic/{job_id}")
        assert response.status_code == 200
        assert response.json() == {"job_id": job_id, "state": "failure", "result": None}
    finally:
        await redis_client.delete(f"dhf:diagnostic-job:{job_id}")
        await redis_client.aclose()
