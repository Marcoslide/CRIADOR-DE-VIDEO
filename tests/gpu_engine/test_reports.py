"""Testes de dhf_gpu_engine.reports — geração de relatório (seção 35 da missão)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from dhf_gpu_engine.reports import build_report, render_markdown, write_report


@pytest.fixture
def results_file(tmp_path: Path) -> Path:
    path = tmp_path / "results.jsonl"
    rows = [
        {
            "ts": "2026-01-01T00:00:00Z",
            "script": "00-preflight",
            "name": "ram",
            "status": "FAIL",
            "detail": "pouca RAM",
        },
        {
            "ts": "2026-01-01T00:00:01Z",
            "script": "00-preflight",
            "name": "cpu_cores",
            "status": "WARN",
            "detail": "poucos cores",
        },
        {
            "ts": "2026-01-01T00:00:02Z",
            "script": "00-preflight",
            "name": "kernel",
            "status": "PASS",
            "detail": "ok",
        },
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows))
    return path


def test_build_report_without_results_file_still_includes_hardware_and_telemetry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("dhf_gpu_engine.capabilities.shutil.which", lambda _: None)

    report = build_report(results_file=None)

    assert report["gpu_status"] == "not_configured"
    assert report["all_checks"] == []
    assert report["checks_summary"] == {}
    assert "telemetry" in report


def test_build_report_aggregates_bash_results(
    monkeypatch: pytest.MonkeyPatch, results_file: Path
) -> None:
    monkeypatch.setattr("dhf_gpu_engine.capabilities.shutil.which", lambda _: None)

    report = build_report(results_file=results_file)

    assert report["checks_summary"] == {"FAIL": 1, "WARN": 1, "PASS": 1}
    assert len(report["failures"]) == 1
    assert report["failures"][0]["name"] == "ram"
    assert len(report["warnings"]) == 1


def test_build_report_ignores_malformed_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("dhf_gpu_engine.capabilities.shutil.which", lambda _: None)
    bad_file = tmp_path / "bad.jsonl"
    bad_file.write_text('{"status": "PASS", "script": "x", "name": "y"}\nnao é json\n')

    report = build_report(results_file=bad_file)

    assert report["checks_summary"] == {"PASS": 1}


def test_render_markdown_includes_failures_and_warnings(
    monkeypatch: pytest.MonkeyPatch, results_file: Path
) -> None:
    monkeypatch.setattr("dhf_gpu_engine.capabilities.shutil.which", lambda _: None)
    report = build_report(results_file=results_file)

    markdown = render_markdown(report)

    assert "## Falhas" in markdown
    assert "ram" in markdown
    assert "## Avisos" in markdown
    assert "cpu_cores" in markdown


def test_write_report_creates_both_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, results_file: Path
) -> None:
    monkeypatch.setattr("dhf_gpu_engine.capabilities.shutil.which", lambda _: None)
    output_dir = tmp_path / "reports"

    json_path, md_path = write_report(output_dir, results_file)

    assert json_path.exists()
    assert md_path.exists()
    assert json_path.suffix == ".json"
    assert md_path.suffix == ".md"

    parsed = json.loads(json_path.read_text())
    assert parsed["checks_summary"]["FAIL"] == 1
