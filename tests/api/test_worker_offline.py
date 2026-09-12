"""Prova real de que o health não chama um worker ausente de conectado."""

import httpx
import pytest

pytestmark = pytest.mark.requires_worker_offline


async def test_worker_offline_is_reported_as_timeout_or_error(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/health/worker")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"timeout", "error"}
    assert body["status"] != "connected"
    assert body["error_code"] in {"timeout", "connection_error"}
