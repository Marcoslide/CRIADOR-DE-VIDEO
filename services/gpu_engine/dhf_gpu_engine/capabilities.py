"""Detecção real de capabilities da GPU — nunca hardcoded (seção 5/6 da missão).

Cada grupo de campos vem de uma fonte diferente, documentada explicitamente:
- nvidia-smi: modelo, VRAM, driver, temperatura, power, utilização (ao vivo)
- nvcc / /usr/local/cuda/version.json: versão do CUDA Toolkit instalado (ao vivo)
- `import tensorrt`: versão do TensorRT instalado (ao vivo)
- `ffmpeg -encoders`: quais codecs NVENC o build atual expõe (ao vivo)
- vulkaninfo: se o stack gráfico Vulkan responde (ao vivo)
- _RT_CORE_TABLE: RT cores não são expostos por nvidia-smi — só uma tabela estática de
  hardware conhecido pode responder isso. Marcado explicitamente via
  `raytracing_capable_source="known_hardware_table"` — nunca com a mesma confiança de
  uma checagem ao vivo.
"""

from __future__ import annotations

import shutil
import subprocess
from datetime import UTC, datetime

from dhf_schemas.system_status import EngineStatus

from dhf_gpu_engine.schemas import GpuCapabilities

# Só GPUs onde a presença de RT cores é um fato de hardware bem estabelecido e estável.
# Correspondência por substring no nome reportado pelo nvidia-smi. Datacenter compute-only
# (A100/H100/B200) não têm RT cores; toda a linha RTX/GeForce RTX/Quadro RTX tem.
_RT_CORE_TABLE: dict[str, bool] = {
    "RTX": True,
    "A100": False,
    "H100": False,
    "H200": False,
    "B200": False,
    "L40S": True,  # Ada, tem RT cores (diferente da série A/H de datacenter)
    "V100": False,
    "A40": True,
}


def _run(cmd: list[str], timeout: float = 5.0) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def _detect_cuda_version() -> str | None:
    proc = _run(["nvcc", "--version"])
    if proc and proc.returncode == 0:
        for line in proc.stdout.splitlines():
            if "release" in line:
                # ex.: "Cuda compilation tools, release 12.9, V12.9.41"
                parts = line.split("release")[-1].strip().split(",")
                return parts[0].strip()
    return None


def _detect_tensorrt_version() -> str | None:
    proc = _run(["python3", "-c", "import tensorrt; print(tensorrt.__version__)"])
    if proc and proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()
    return None


def _detect_nvenc_codecs() -> tuple[bool, list[str]]:
    if shutil.which("ffmpeg") is None:
        return False, []
    proc = _run(["ffmpeg", "-hide_banner", "-encoders"])
    if not proc or proc.returncode != 0:
        return False, []
    codecs = [c for c in ("h264_nvenc", "hevc_nvenc", "av1_nvenc") if c in proc.stdout]
    return len(codecs) > 0, codecs


def _detect_graphics_capable() -> bool | None:
    if shutil.which("vulkaninfo") is None:
        return None
    proc = _run(["vulkaninfo", "--summary"])
    if proc is None:
        return None
    return proc.returncode == 0


def _lookup_raytracing_capable(gpu_name: str | None) -> bool | None:
    if not gpu_name:
        return None
    for needle, has_rt in _RT_CORE_TABLE.items():
        if needle in gpu_name:
            return has_rt
    return None


def _as_float(value: str) -> float | None:
    value = value.strip()
    if not value or "Not Supported" in value or "N/A" in value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def detect_capabilities() -> GpuCapabilities:
    """Ponto de entrada único — chamado pelo CLI, telemetry.py e pelos testes."""
    now = datetime.now(UTC)

    if shutil.which("nvidia-smi") is None:
        return GpuCapabilities(
            status=EngineStatus.NOT_CONFIGURED,
            detail="nvidia-smi não encontrado no PATH",
            checked_at=now,
        )

    query = (
        "name,driver_version,memory.total,memory.free,temperature.gpu,power.draw,"
        "power.limit,utilization.gpu,utilization.memory,compute_cap"
    )
    proc = _run(["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"])
    if proc is None or proc.returncode != 0:
        detail = proc.stderr.strip() if proc else "timeout ao executar nvidia-smi"
        return GpuCapabilities(status=EngineStatus.ERROR, detail=detail, checked_at=now)

    fields = [f.strip() for f in proc.stdout.strip().splitlines()[0].split(",")]
    if len(fields) < 10:
        return GpuCapabilities(
            status=EngineStatus.ERROR,
            detail=f"saída inesperada do nvidia-smi: {proc.stdout!r}",
            checked_at=now,
        )
    (
        name,
        driver,
        vram_total,
        vram_free,
        temp,
        power_draw,
        power_limit,
        util_gpu,
        util_mem,
        compute_cap,
    ) = fields[:10]

    enc_proc = _run(
        ["nvidia-smi", "--query-gpu=utilization.encoder", "--format=csv,noheader,nounits"]
    )
    dec_proc = _run(
        ["nvidia-smi", "--query-gpu=utilization.decoder", "--format=csv,noheader,nounits"]
    )
    enc_util = (
        _as_float(enc_proc.stdout.splitlines()[0])
        if enc_proc and enc_proc.returncode == 0 and enc_proc.stdout.strip()
        else None
    )
    dec_util = (
        _as_float(dec_proc.stdout.splitlines()[0])
        if dec_proc and dec_proc.returncode == 0 and dec_proc.stdout.strip()
        else None
    )

    has_nvenc, nvenc_codecs = _detect_nvenc_codecs()
    graphics_capable = _detect_graphics_capable()
    raytracing_capable = _lookup_raytracing_capable(name)

    return GpuCapabilities(
        status=EngineStatus.CONNECTED,
        detail=f"{name} detectada via nvidia-smi",
        gpu_model=name,
        vram_total_mb=_as_float(vram_total),
        vram_free_mb=_as_float(vram_free),
        cuda_capability=compute_cap.strip(),
        driver_version=driver.strip(),
        cuda_version=_detect_cuda_version(),
        tensorrt_version=_detect_tensorrt_version(),
        has_nvenc=has_nvenc,
        nvenc_codecs=nvenc_codecs,
        graphics_capable=graphics_capable,
        graphics_capable_source="vulkaninfo_live_probe" if graphics_capable is not None else None,
        raytracing_capable=raytracing_capable,
        raytracing_capable_source="known_hardware_table"
        if raytracing_capable is not None
        else None,
        temperature_c=_as_float(temp),
        power_draw_w=_as_float(power_draw),
        power_limit_w=_as_float(power_limit),
        utilization_gpu_pct=_as_float(util_gpu),
        utilization_memory_pct=_as_float(util_mem),
        encoder_utilization_pct=enc_util,
        decoder_utilization_pct=dec_util,
        checked_at=now,
    )
