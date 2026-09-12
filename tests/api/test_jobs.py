"""Teste de integração do job de diagnóstico — prova real de ponta a ponta API -> Redis ->
Worker. Requer Redis e um worker Celery reais consumindo a fila (ver README.md "Rodando
sem Docker"). Sem mocks: enfileira de verdade e espera o worker processar.
"""

import asyncio
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
