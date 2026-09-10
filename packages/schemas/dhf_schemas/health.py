"""Contratos de health/readiness — únicos schemas de domínio da Fase 1.

Os schemas de negócio (Avatar, Voice, Motion, Product, Scene, VideoProject, ...)
estão desenhados em `docs/ARCHITECTURE.md` §6 e entram aqui a partir da Fase 3.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

ComponentStatus = Literal["connected", "error", "timeout", "not_configured"]


class ComponentCheck(BaseModel):
    name: str
    status: ComponentStatus
    latency_ms: float | None = None
    detail: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    app_env: str


class ReadinessResponse(BaseModel):
    ready: bool
    checks: list[ComponentCheck]
    checked_at: datetime
