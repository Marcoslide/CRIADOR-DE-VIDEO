"""Status agregado do sistema — GPU Engine, OpenAI (Director AI) e engines de render
futuros (Unreal, Audio2Face, MetaHuman). Regra ZERO FAKE: mesmo princípio de
`storage.StorageConnectionStatus` — CONNECTED só quando checado de verdade nesta
requisição, NOT_CONFIGURED/NOT_INSTALLED quando a integração não está disponível, ERROR
quando a checagem foi tentada e falhou. Nunca um booleano solto, nunca um "connected"
hardcoded.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from dhf_schemas.health import ComponentCheck
from dhf_schemas.storage import StorageStatus


class EngineStatus(StrEnum):
    """Vocabulário para integrações sem estado transitório (checagem é sempre síncrona
    request/resposta) — diferente de StorageConnectionStatus, que tem CONNECTING/DEGRADED
    por ser uma conexão de longa duração com cache."""

    CONNECTED = "connected"
    NOT_CONFIGURED = "not_configured"
    NOT_INSTALLED = "not_installed"
    ERROR = "error"


class GpuStatus(BaseModel):
    status: EngineStatus
    detail: str | None = None
    device_name: str | None = None
    driver_version: str | None = None
    vram_total_mb: int | None = None
    vram_used_mb: int | None = None


class OpenAIStatus(BaseModel):
    status: EngineStatus
    detail: str | None = None
    error_code: str | None = None


class EngineStubStatus(BaseModel):
    """Status de uma integração de render ainda sem implementação real (Unreal,
    Audio2Face, MetaHuman) — a checagem em si é real (verifica caminho/URL configurado),
    só o resultado hoje é sempre NOT_INSTALLED porque nada foi provisionado ainda."""

    name: str
    status: EngineStatus
    detail: str | None = None


class SystemStatusResponse(BaseModel):
    checked_at: datetime
    api: ComponentCheck
    postgres: ComponentCheck
    redis: ComponentCheck
    worker: ComponentCheck
    storage: StorageStatus
    gpu: GpuStatus
    openai: OpenAIStatus
    unreal: EngineStubStatus
    audio2face: EngineStubStatus
    metahuman: EngineStubStatus
