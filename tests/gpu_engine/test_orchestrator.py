"""Testes de dhf_gpu_engine.orchestrator — seção 20 da missão. Sem GPU real, get_health()
precisa reportar REQUIRES_GPU honestamente (nunca PASS); prepare_job/release_job são
testados via VramManager real (não mockado — é lógica pura, não precisa de hardware)."""

from __future__ import annotations

import pytest
from dhf_gpu_engine.orchestrator import GpuOrchestrator, JobNotFoundError
from dhf_gpu_engine.vram_manager import VramCriticalError


def test_get_health_reports_requires_gpu_without_hardware(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("dhf_gpu_engine.capabilities.shutil.which", lambda _: None)
    orchestrator = GpuOrchestrator(vram_total_mb=24576)

    health = orchestrator.get_health()

    assert health["status"] == "REQUIRES_GPU"


def test_get_status_includes_gpu_and_vram(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("dhf_gpu_engine.capabilities.shutil.which", lambda _: None)
    orchestrator = GpuOrchestrator(vram_total_mb=24576)

    status = orchestrator.get_status()

    assert status["gpu"]["status"] == "not_configured"
    assert status["vram"]["total_mb"] == 24576


def test_prepare_job_reserves_vram_and_release_frees_it() -> None:
    orchestrator = GpuOrchestrator(vram_total_mb=24576)

    handle = orchestrator.prepare_job("audio2face-stream-1", required_vram_mb=4096)

    assert handle.reserved_vram_mb == 4096
    assert orchestrator.vram_manager.allocated_mb == 4096

    orchestrator.release_job(handle.job_id)

    assert orchestrator.vram_manager.allocated_mb == 0


def test_release_unknown_job_raises() -> None:
    orchestrator = GpuOrchestrator(vram_total_mb=24576)

    with pytest.raises(JobNotFoundError):
        orchestrator.release_job("job-que-nao-existe")


def test_prepare_job_beyond_critical_threshold_raises() -> None:
    orchestrator = GpuOrchestrator(vram_total_mb=1000, critical_pct=90)

    with pytest.raises(VramCriticalError):
        orchestrator.prepare_job("job-gigante", required_vram_mb=999)


def test_two_jobs_can_coexist_within_budget() -> None:
    orchestrator = GpuOrchestrator(vram_total_mb=24576)

    handle_a = orchestrator.prepare_job("job-a", required_vram_mb=4000)
    handle_b = orchestrator.prepare_job("job-b", required_vram_mb=4000)

    assert orchestrator.vram_manager.allocated_mb == 8000
    assert {m.name for m in orchestrator.get_loaded_models()} == {
        f"job:{handle_a.job_id}:job-a",
        f"job:{handle_b.job_id}:job-b",
    }


def test_run_benchmark_unknown_name_fails_without_running_anything() -> None:
    orchestrator = GpuOrchestrator(vram_total_mb=24576)

    result = orchestrator.run_benchmark("nome-invalido")

    assert result.status.value == "FAIL"
    assert "desconhecido" in (result.detail or "")


def test_run_benchmark_disk_runs_the_real_script() -> None:
    """Único benchmark real deste arquivo — disk não depende de GPU, então é uma prova
    de ponta a ponta genuína do subprocess real (infra/gpu/benchmarks/benchmark_disk.py)."""
    orchestrator = GpuOrchestrator(vram_total_mb=24576)

    result = orchestrator.run_benchmark("disk", timeout=30)

    assert result.status.value == "PASS"
    assert result.metrics["write_mb_s"] is not None
