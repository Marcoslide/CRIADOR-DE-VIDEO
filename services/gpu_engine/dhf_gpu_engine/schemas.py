"""Contratos do GPU Engine — mesmo vocabulário de status usado em infra/gpu/lib/common.sh
(`record_result`), para que scripts bash e este pacote Python nunca divirjam sobre o que
PASS/WARN/FAIL/SKIP/NOT_TESTED/REQUIRES_GPU significam. Regra ZERO FAKE do projeto: nunca
um `CheckStatus.PASS` sem uma checagem real ter rodado."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from dhf_schemas.system_status import EngineStatus
from pydantic import BaseModel, Field

__all__ = [
    "CheckStatus",
    "EngineStatus",
    "GpuCapabilities",
    "ModelState",
    "ModelInfo",
    "VramSnapshot",
    "TelemetrySnapshot",
    "JobHandle",
    "BenchmarkResult",
]


class CheckStatus(StrEnum):
    """Vocabulário de diagnóstico/preflight/benchmark — distinto de EngineStatus
    (que descreve "esta integração está conectada?"). Este descreve "este teste rodou e
    o que aconteceu?" — categoria diferente, don't conflate."""

    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    SKIP = "SKIP"
    NOT_TESTED = "NOT_TESTED"
    REQUIRES_GPU = "REQUIRES_GPU"


class ModelState(StrEnum):
    """Estado de residência de um modelo/engine na VRAM (seção 18 da missão)."""

    HOT = "hot"  # carregado, pronto para inferência imediata
    WARM = "warm"  # pesos em RAM/disco rápido, não na VRAM — recarrega rápido
    UNLOADED = "unloaded"  # nada residente, precisa recarregar do zero


class GpuCapabilities(BaseModel):
    """Tudo que a seção 5/6 da missão pede registrar. Cada campo é `None` quando não
    detectável nesta máquina/driver — nunca um valor inventado. `source` diz de onde
    cada grupo de campos veio, para nunca confundir uma checagem ao vivo com uma
    tabela estática de hardware conhecido."""

    status: EngineStatus
    detail: str | None = None

    gpu_model: str | None = None
    vram_total_mb: float | None = None
    vram_free_mb: float | None = None
    cuda_capability: str | None = None
    driver_version: str | None = None
    cuda_version: str | None = None
    tensorrt_version: str | None = None

    has_nvenc: bool | None = None
    nvenc_codecs: list[str] = Field(default_factory=list)

    # graphics_capable/raytracing_capable vêm de fontes diferentes: graphics_capable é
    # sondado ao vivo (vulkaninfo); raytracing_capable é lookup numa tabela estática de
    # hardware conhecido (nvidia-smi não expõe "tem RT cores?" via query) — nunca os
    # dois com a mesma confiança, por isso os dois campos "_source" abaixo.
    graphics_capable: bool | None = None
    graphics_capable_source: str | None = None
    raytracing_capable: bool | None = None
    raytracing_capable_source: str | None = None

    temperature_c: float | None = None
    power_draw_w: float | None = None
    power_limit_w: float | None = None
    utilization_gpu_pct: float | None = None
    utilization_memory_pct: float | None = None
    encoder_utilization_pct: float | None = None
    decoder_utilization_pct: float | None = None

    checked_at: datetime


class ModelInfo(BaseModel):
    name: str
    state: ModelState
    vram_mb: float
    capabilities_required: list[str] = Field(default_factory=list)
    loaded_at: datetime | None = None
    last_used_at: datetime | None = None


class VramSnapshot(BaseModel):
    total_mb: float
    allocated_mb: float
    reserved_mb: float
    peak_mb: float
    warning_pct: float
    critical_pct: float
    status: CheckStatus  # PASS (normal) / WARN (>= warning_pct) / FAIL (>= critical_pct)
    by_consumer: dict[str, float] = Field(default_factory=dict)


class TelemetrySnapshot(BaseModel):
    capabilities: GpuCapabilities
    vram: VramSnapshot | None = None
    loaded_models: list[ModelInfo] = Field(default_factory=list)
    processes: list[dict[str, Any]] = Field(default_factory=list)
    captured_at: datetime


class JobHandle(BaseModel):
    job_id: str
    name: str
    reserved_vram_mb: float
    created_at: datetime


class BenchmarkResult(BaseModel):
    name: str
    status: CheckStatus
    detail: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
