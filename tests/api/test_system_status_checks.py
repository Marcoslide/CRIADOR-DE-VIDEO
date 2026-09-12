"""Testes unitários dos checks individuais de system_status — exercitam a lógica de
detecção real de cada integração (nvidia-smi, chamada HTTP à OpenAI, existência de
caminho/URL configurado) isoladamente. A maioria não precisa de Postgres/Redis/worker
(por isso não usam requires_services); a exceção é marcada onde depende de rede real.
"""

from pathlib import Path

import httpx
import pytest
import respx
from app.routers.system_status import check_gpu, check_openai, check_render_engine


async def test_check_gpu_reports_not_configured_without_nvidia_smi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.routers.system_status.shutil.which", lambda _: None)
    status = await check_gpu()
    assert status.status == "not_configured"
    assert status.device_name is None


async def test_check_gpu_kills_and_reaps_timed_out_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeProcess:
        returncode = None

        def __init__(self) -> None:
            self.killed = False
            self.communicate_calls = 0

        def communicate(self):
            self.communicate_calls += 1

            async def done():
                return b"", b""

            return done()

        def kill(self) -> None:
            self.killed = True

    process = FakeProcess()

    async def fake_create_subprocess_exec(*args, **kwargs):
        return process

    async def fake_wait_for(awaitable, *, timeout):
        awaitable.close()
        raise TimeoutError

    monkeypatch.setattr("app.routers.system_status.shutil.which", lambda _: "/usr/bin/nvidia-smi")
    monkeypatch.setattr(
        "app.routers.system_status.asyncio.create_subprocess_exec", fake_create_subprocess_exec
    )
    monkeypatch.setattr("app.routers.system_status.asyncio.wait_for", fake_wait_for)

    status = await check_gpu()

    assert status.status == "error"
    assert process.killed is True
    assert process.communicate_calls == 2


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


@respx.mock
async def test_check_openai_reports_error_on_invalid_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Uma resposta 401 realista prova o ramo sem tornar o CI dependente da internet."""
    from dhf_shared.config import Settings

    monkeypatch.setattr(
        "app.routers.system_status.get_settings",
        lambda: Settings(openai_api_key="sk-invalid-test-key-not-real"),
    )
    respx.get("https://api.openai.com/v1/models").mock(
        return_value=httpx.Response(401, json={"error": {"message": "invalid key"}})
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
