"""Testes do CLI dhf-gpu (seção 34 da missão) — chamando as funções de comando
diretamente (sem subprocess) para manter os testes rápidos; a instalação real do
entry point `dhf-gpu` já foi validada manualmente via
`uv run --project services/gpu_engine dhf-gpu ...`."""

from __future__ import annotations

import json

import pytest
from dhf_gpu_engine.cli import build_parser


def _parse(args: list[str]):
    return build_parser().parse_args(args)


def test_health_command_without_gpu_exits_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("dhf_gpu_engine.capabilities.shutil.which", lambda _: None)
    args = _parse(["health", "--json"])

    exit_code = args.func(args)

    assert exit_code == 2
    body = json.loads(capsys.readouterr().out)
    assert body["status"] == "REQUIRES_GPU"


def test_status_command_text_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("dhf_gpu_engine.capabilities.shutil.which", lambda _: None)
    args = _parse(["status"])

    args.func(args)

    out = capsys.readouterr().out
    assert "não detectada" in out
    assert "VRAM:" in out


def test_capabilities_command_always_prints_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("dhf_gpu_engine.capabilities.shutil.which", lambda _: None)
    args = _parse(["capabilities"])

    exit_code = args.func(args)

    body = json.loads(capsys.readouterr().out)
    assert body["status"] == "not_configured"
    assert exit_code == 2


def test_benchmark_disk_command_runs_real_script(capsys: pytest.CaptureFixture[str]) -> None:
    args = _parse(["benchmark", "disk", "--json"])

    exit_code = args.func(args)

    body = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert body["status"] == "PASS"


def test_report_command_writes_files(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("dhf_gpu_engine.capabilities.shutil.which", lambda _: None)
    args = _parse(["report", "--out", str(tmp_path)])

    exit_code = args.func(args)

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "Relatório JSON" in out
    assert list(tmp_path.glob("GPU_ENGINE_REPORT_*.json"))


def test_vram_total_mb_default_matches_rtx_4090() -> None:
    args = _parse(["status"])
    assert args.vram_total_mb == 24576.0
