"""VRAM Manager — seção 18 da missão: a RTX 4090 tem 24GB, e não podemos presumir que
todo engine (Audio2Face, TTS, upscaler, modelo generativo) fica residente ao mesmo
tempo. Rastreia alocação por consumidor nomeado com estado HOT/WARM/UNLOADED e
thresholds de warning/critical configuráveis — base real (não simulação), mas sem
scheduler completo (isso é o Model Manager por cima, orchestrator.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from dhf_gpu_engine.schemas import CheckStatus, ModelInfo, ModelState, VramSnapshot


@dataclass
class _Consumer:
    name: str
    vram_mb: float
    state: ModelState
    loaded_at: datetime | None = None
    last_used_at: datetime | None = None


class VramCriticalError(Exception):
    """Levantado quando uma alocação levaria o uso além do threshold crítico e
    `force=False` — nunca uma alocação silenciosa que arrisca OOM real na GPU."""

    def __init__(self, requested_mb: float, available_mb: float) -> None:
        self.requested_mb = requested_mb
        self.available_mb = available_mb
        super().__init__(
            f"alocação de {requested_mb}MB recusada — só {available_mb}MB disponíveis "
            "antes do threshold crítico (use force=True para sobrescrever conscientemente)"
        )


class VramManager:
    def __init__(
        self,
        total_mb: float,
        warning_pct: float = 80.0,
        critical_pct: float = 92.0,
    ) -> None:
        if total_mb <= 0:
            raise ValueError("total_mb precisa ser positivo")
        self.total_mb = total_mb
        self.warning_pct = warning_pct
        self.critical_pct = critical_pct
        self._consumers: dict[str, _Consumer] = {}
        self._peak_mb = 0.0

    @property
    def allocated_mb(self) -> float:
        return sum(c.vram_mb for c in self._consumers.values() if c.state == ModelState.HOT)

    def allocate(self, name: str, vram_mb: float, *, force: bool = False) -> None:
        """Registra `name` como HOT consumindo `vram_mb`. Recusa (VramCriticalError) se
        isso ultrapassar o threshold crítico, a menos que `force=True` — a decisão de
        forçar é sempre explícita de quem chama, nunca automática."""
        projected = self.allocated_mb + vram_mb
        critical_mb = self.total_mb * self.critical_pct / 100
        if projected > critical_mb and not force:
            available = max(critical_mb - self.allocated_mb, 0)
            raise VramCriticalError(vram_mb, available)

        now = datetime.now(UTC)
        self._consumers[name] = _Consumer(
            name=name, vram_mb=vram_mb, state=ModelState.HOT, loaded_at=now, last_used_at=now
        )
        self._peak_mb = max(self._peak_mb, self.allocated_mb)

    def mark_warm(self, name: str) -> None:
        """Move um consumidor de HOT para WARM — libera VRAM mas mantém metadata (o
        Model Manager decide quando recarregar)."""
        if name in self._consumers:
            self._consumers[name].state = ModelState.WARM

    def release(self, name: str) -> None:
        self._consumers.pop(name, None)

    def touch(self, name: str) -> None:
        if name in self._consumers:
            self._consumers[name].last_used_at = datetime.now(UTC)

    def status(self) -> VramSnapshot:
        allocated = self.allocated_mb
        pct = (allocated / self.total_mb * 100) if self.total_mb else 0
        if pct >= self.critical_pct:
            status = CheckStatus.FAIL
        elif pct >= self.warning_pct:
            status = CheckStatus.WARN
        else:
            status = CheckStatus.PASS

        return VramSnapshot(
            total_mb=self.total_mb,
            allocated_mb=allocated,
            reserved_mb=allocated,  # sem um alocador de baixo nível real, reserved == allocated
            peak_mb=self._peak_mb,
            warning_pct=self.warning_pct,
            critical_pct=self.critical_pct,
            status=status,
            by_consumer={
                c.name: c.vram_mb for c in self._consumers.values() if c.state == ModelState.HOT
            },
        )

    def loaded_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(
                name=c.name,
                state=c.state,
                vram_mb=c.vram_mb,
                loaded_at=c.loaded_at,
                last_used_at=c.last_used_at,
            )
            for c in self._consumers.values()
        ]
