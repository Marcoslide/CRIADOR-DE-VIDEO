"""Teste de integração do endpoint agregado GET /status/system, consumido pelo Dashboard.
Requer PostgreSQL, Redis e worker reais (mesmo requisito de test_health.py). Confirma que
API/Postgres/Redis/Worker aparecem genuinamente "connected" e que integrações ainda não
providas neste ambiente (OpenAI sem chave, GPU sem nvidia-smi, engines de render sem
caminho configurado) aparecem honestamente not_configured/not_installed — nunca
"connected" fingido (regra ZERO FAKE, seção 68 do prompt-mestre).
"""

import httpx
import pytest

pytestmark = pytest.mark.requires_services


async def test_system_status_reports_real_core_infra(client: httpx.AsyncClient) -> None:
    response = await client.get("/status/system")
    assert response.status_code == 200
    body = response.json()

    assert body["checked_at"]
    assert body["api"]["status"] == "connected"
    assert body["postgres"]["status"] == "connected"
    assert body["postgres"]["latency_ms"] >= 0
    assert body["redis"]["status"] == "connected"
    assert body["redis"]["latency_ms"] >= 0
    assert body["worker"]["status"] == "connected"
    assert "pong" in body["worker"]["detail"]


async def test_system_status_never_fakes_unconfigured_integrations(
    client: httpx.AsyncClient,
) -> None:
    """Neste ambiente não há credencial do Drive, OPENAI_API_KEY, GPU nem engines de
    render configurados — o endpoint precisa reportar isso honestamente, nunca
    "connected"."""
    response = await client.get("/status/system")
    body = response.json()

    assert body["storage"]["status"] == "not_configured"
    assert body["gpu"]["status"] == "not_configured"
    assert body["openai"]["status"] == "not_configured"
    assert body["openai"]["detail"] == "OPENAI_API_KEY não configurada"
    for engine in ("unreal", "audio2face", "metahuman"):
        assert body[engine]["status"] == "not_installed"
        assert body[engine]["name"]
