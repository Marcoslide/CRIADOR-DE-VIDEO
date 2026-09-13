"""GPU Orchestrator — seção 20 da missão. Serviço independente que compõe
capabilities+VramManager+ModelManager+telemetry por trás de uma API única. Deliberadamente
NÃO conectado a apps/api/apps/web nesta rodada (ver infra/gpu/README.md) — consumido hoje
só pelo CLI (`dhf-gpu`) e pelos scripts de infra/gpu/.
"""

from __future__ import annotations

import subprocess
import uuid
from datetime import UTC, datetime

from dhf_schemas.system_status import EngineStatus

from dhf_gpu_engine.capabilities import detect_capabilities
from dhf_gpu_engine.model_manager import ModelInfo, ModelManager
from dhf_gpu_engine.schemas import (
    BenchmarkResult,
    CheckStatus,
    GpuCapabilities,
    JobHandle,
    TelemetrySnapshot,
)
from dhf_gpu_engine.telemetry import collect_telemetry
from dhf_gpu_engine.vram_manager import VramCriticalError, VramManager


class JobNotFoundError(Exception):
    pass


class GpuOrchestrator:
    def __init__(
        self, vram_total_mb: float, warning_pct: float = 80.0, critical_pct: float = 92.0
    ) -> None:
        self.vram_manager = VramManager(vram_total_mb, warning_pct, critical_pct)
        self.model_manager = ModelManager(self.vram_manager)
        self._jobs: dict[str, JobHandle] = {}

    def get_capabilities(self) -> GpuCapabilities:
        return detect_capabilities()

    def get_status(self) -> dict:
        caps = self.get_capabilities()
        return {
            "gpu": caps.model_dump(mode="json"),
            "vram": self.vram_manager.status().model_dump(mode="json"),
        }

    def get_health(self) -> dict:
        """Veredito agregado — nunca PASS sem checar; REQUIRES_GPU quando honestamente
        não há hardware para testar neste ambiente."""
        caps = self.get_capabilities()
        if caps.status != EngineStatus.CONNECTED:
            return {"status": CheckStatus.REQUIRES_GPU.value, "detail": caps.detail}

        vram_status = self.vram_manager.status()
        if vram_status.status == CheckStatus.FAIL:
            return {"status": CheckStatus.FAIL.value, "detail": "VRAM acima do threshold crítico"}
        if vram_status.status == CheckStatus.WARN:
            return {
                "status": CheckStatus.WARN.value,
                "detail": "VRAM acima do threshold de warning",
            }
        return {"status": CheckStatus.PASS.value, "detail": f"{caps.gpu_model} operacional"}

    def get_loaded_models(self) -> list[ModelInfo]:
        return self.model_manager.all_loaded()

    def prepare_job(self, name: str, required_vram_mb: float, *, force: bool = False) -> JobHandle:
        """Reserva VRAM para um job (não é um scheduler completo — é a base real pedida
        na missão: registra a reserva, propaga VramCriticalError se não houver espaço)."""
        job_id = str(uuid.uuid4())
        self.vram_manager.allocate(f"job:{job_id}:{name}", required_vram_mb, force=force)
        handle = JobHandle(
            job_id=job_id,
            name=name,
            reserved_vram_mb=required_vram_mb,
            created_at=datetime.now(UTC),
        )
        self._jobs[job_id] = handle
        return handle

    def release_job(self, job_id: str) -> None:
        handle = self._jobs.pop(job_id, None)
        if handle is None:
            raise JobNotFoundError(f"job '{job_id}' não encontrado (já liberado ou nunca existiu)")
        self.vram_manager.release(f"job:{job_id}:{handle.name}")

    def get_telemetry(self) -> TelemetrySnapshot:
        return collect_telemetry(self.vram_manager)

    def run_benchmark(self, name: str, *, timeout: float = 60.0) -> BenchmarkResult:
        """Roda um dos scripts de infra/gpu/benchmarks/ como subprocesso e traduz o
        resultado para BenchmarkResult — reusa a lógica já escrita/testada ali em vez
        de duplicá-la aqui."""
        import json
        import sys
        from pathlib import Path

        script_map = {
            "gpu": "benchmark_gpu.py",
            "vram": "benchmark_vram.py",
            "nvenc": "benchmark_nvenc.py",
            "disk": "benchmark_disk.py",
        }
        script = script_map.get(name)
        if script is None:
            return BenchmarkResult(
                name=name,
                status=CheckStatus.FAIL,
                detail=f"benchmark desconhecido: {name!r} (opções: {sorted(script_map)})",
            )

        script_path = Path(__file__).resolve().parents[3] / "infra" / "gpu" / "benchmarks" / script
        try:
            proc = subprocess.run(
                [sys.executable, str(script_path), "--json"],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return BenchmarkResult(
                name=name, status=CheckStatus.FAIL, detail=f"timeout após {timeout}s"
            )
        except FileNotFoundError:
            return BenchmarkResult(
                name=name, status=CheckStatus.FAIL, detail=f"script não encontrado: {script_path}"
            )

        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return BenchmarkResult(
                name=name,
                status=CheckStatus.FAIL,
                detail=f"saída não é JSON válido: {proc.stdout!r} {proc.stderr!r}",
            )

        status_str = payload.get("status", "FAIL")
        try:
            status = CheckStatus(status_str)
        except ValueError:
            status = CheckStatus.FAIL

        return BenchmarkResult(
            name=name, status=status, detail=payload.get("detail"), metrics=payload
        )


__all__ = ["GpuOrchestrator", "JobNotFoundError", "VramCriticalError"]
