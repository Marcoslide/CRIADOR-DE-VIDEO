"""Testes unitários dos checks individuais de system_status — exercitam a lógica de
detecção real de cada integração (nvidia-smi, chamada HTTP à OpenAI, existência de
caminho/URL configurado) isoladamente. A maioria não precisa de Postgres/Redis/worker
(por isso não usam requires_services); a exceção é marcada onde depende de rede real.
"""

from pathlib import Path

import pytest
from app.routers.system_status import check_gpu, check_openai, check_render_engine


async def test_check_gpu_reports_not_configured_without_nvidia_smi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.routers.system_status.shutil.which", lambda _: None)
    status = await check_gpu()
    assert status.status == "not_configured"
    assert status.device_name is None


async def test_check_openai_reports_not_configured_without_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dhf_shared.config import Settings

    monkeypatch.setattr(
        "app.routers.system_status.get_settings", lambda: Settings(openai_api_key="")
    )
    status = await check_openai()
    assert status.status == "not_configured"
    assert status.detail == "OPENAI_API_KEY não configurada"


@pytest.mark.requires_services
async def test_check_openai_reports_error_on_invalid_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Confirma, com uma chamada HTTP real à OpenAI, que uma chave configurada mas
    inválida gera ERROR de verdade — nunca CONNECTED sem checar (regra ZERO FAKE).
    Marcado requires_services porque depende de rede externa real, não só de lógica local."""
    from dhf_shared.config import Settings

    monkeypatch.setattr(
        "app.routers.system_status.get_settings",
        lambda: Settings(openai_api_key="sk-invalid-test-key-not-real"),
    )
    status = await check_openai()
    assert status.status == "error"
    assert status.error_code is not None


async def test_check_render_engine_reports_not_installed_when_unconfigured() -> None:
    status = await check_render_engine("unreal", "", "Unreal Engine")
    assert status.status == "not_installed"
    assert status.name == "Unreal Engine"


async def test_check_render_engine_reports_error_when_local_path_missing() -> None:
    status = await check_render_engine("unreal", "/nonexistent/path/unreal-bin", "Unreal Engine")
    assert status.status == "error"


async def test_check_render_engine_reports_not_installed_when_local_path_exists(
    tmp_path: Path,
) -> None:
    existing = tmp_path / "unreal-bin"
    existing.write_text("stub")
    status = await check_render_engine("unreal", str(existing), "Unreal Engine")
    assert status.status == "not_installed"


async def test_check_render_engine_url_never_checks_disk() -> None:
    """MetaHuman é configurado via URL (is_url=True) — não deve tentar checar caminho de
    disco, mesmo com um valor que não existe como arquivo local."""
    status = await check_render_engine(
        "metahuman", "https://example.com/metahuman", "MetaHuman Animator", is_url=True
    )
    assert status.status == "not_installed"
