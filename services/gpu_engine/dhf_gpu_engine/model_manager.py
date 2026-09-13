"""Model Manager — seção 19 da missão: base real de load/unload/status/memory_estimate/
last_used/capabilities_required. Não integra nenhum modelo de verdade ainda (isso é
trabalho de fases futuras, quando Audio2Face/TTS/upscaler/generativo existirem) — a base
precisa existir e funcionar de ponta a ponta com um "modelo" registrado por metadata,
sem precisar dos pesos reais para ser testável.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from dhf_gpu_engine.schemas import ModelInfo, ModelState
from dhf_gpu_engine.vram_manager import VramManager


@dataclass
class ModelSpec:
    """Metadata de um modelo/engine que o Model Manager pode carregar — registrado uma
    vez (ex.: no startup do orchestrator), sem precisar dos pesos reais existirem para
    a base ser testável."""

    name: str
    vram_estimate_mb: float
    capabilities_required: list[str] = field(default_factory=list)


class ModelNotRegisteredError(Exception):
    pass


class ModelManager:
    def __init__(self, vram_manager: VramManager) -> None:
        self._vram = vram_manager
        self._specs: dict[str, ModelSpec] = {}

    def register(self, spec: ModelSpec) -> None:
        self._specs[spec.name] = spec

    def memory_estimate(self, name: str) -> float:
        spec = self._specs.get(name)
        if spec is None:
            raise ModelNotRegisteredError(f"modelo '{name}' não registrado")
        return spec.vram_estimate_mb

    def capabilities_required(self, name: str) -> list[str]:
        spec = self._specs.get(name)
        if spec is None:
            raise ModelNotRegisteredError(f"modelo '{name}' não registrado")
        return spec.capabilities_required

    def load(self, name: str, *, force: bool = False) -> ModelInfo:
        """Consulta o VramManager antes de admitir — propaga VramCriticalError se não
        houver espaço e `force=False` (a decisão de forçar nunca é implícita)."""
        spec = self._specs.get(name)
        if spec is None:
            raise ModelNotRegisteredError(f"modelo '{name}' não registrado")

        self._vram.allocate(name, spec.vram_estimate_mb, force=force)
        return self.status(name)

    def unload(self, name: str) -> None:
        self._vram.release(name)

    def mark_warm(self, name: str) -> None:
        self._vram.mark_warm(name)

    def touch(self, name: str) -> None:
        self._vram.touch(name)

    def status(self, name: str) -> ModelInfo:
        for info in self._vram.loaded_models():
            if info.name == name:
                spec = self._specs.get(name)
                if spec:
                    info = info.model_copy(
                        update={"capabilities_required": spec.capabilities_required}
                    )
                return info
        return ModelInfo(
            name=name,
            state=ModelState.UNLOADED,
            vram_mb=self._specs.get(
                name, ModelSpec(name=name, vram_estimate_mb=0)
            ).vram_estimate_mb,
            capabilities_required=self._specs.get(
                name, ModelSpec(name=name, vram_estimate_mb=0)
            ).capabilities_required,
        )

    def last_used(self, name: str) -> datetime | None:
        return self.status(name).last_used_at

    def all_loaded(self) -> list[ModelInfo]:
        return self._vram.loaded_models()
