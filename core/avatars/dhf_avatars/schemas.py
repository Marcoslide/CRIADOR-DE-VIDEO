"""Contratos Pydantic do Avatar Registry — request/response da API e a máquina de estados
(seção 12 do prompt-mestre). `AvatarStatus` é literal — os 13 estados definidos no
prompt-mestre, sem adição nem omissão.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AvatarStatus(StrEnum):
    DRAFT = "draft"
    IDENTITY_LOCKED = "identity_locked"
    MULTIVIEW_IN_PROGRESS = "multiview_in_progress"
    MULTIVIEW_APPROVED = "multiview_approved"
    MESH_IN_PROGRESS = "mesh_in_progress"
    MESH_APPROVED = "mesh_approved"
    RIGGED = "rigged"
    MATERIALS_APPROVED = "materials_approved"
    FACE_APPROVED = "face_approved"
    VOICE_APPROVED = "voice_approved"
    MOTION_APPROVED = "motion_approved"
    MASTER_APPROVED = "master_approved"
    PRODUCTION_READY = "production_ready"


# Máquina de estados linear (seção 12): cada status só avança para o próximo. Nenhum salto,
# nenhum retrocesso nesta fundação — refinamentos (ex.: reprovação volta um estágio) entram
# quando os subsistemas que geram cada aprovação existirem de verdade.
_ORDER = list(AvatarStatus)
ALLOWED_STATUS_TRANSITIONS: dict[AvatarStatus, set[AvatarStatus]] = {
    status: ({_ORDER[i + 1]} if i + 1 < len(_ORDER) else set()) for i, status in enumerate(_ORDER)
}


class AvatarCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=200, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    metadata: dict[str, Any] = Field(default_factory=dict)


class AvatarUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    metadata: dict[str, Any] | None = None
    status: AvatarStatus | None = None


class Avatar(BaseModel):
    id: UUID
    name: str
    slug: str
    version: int
    status: AvatarStatus
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
