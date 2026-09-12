"""ORM do Avatar Registry (fundação da Fase 3 — seção 12 do prompt-mestre).

Escopo desta fundação: só os campos que a tela Avatars/CRUD precisa para provar que o
registro persiste de verdade (nome, slug, versão, status, metadata livre). O modelo rico
documentado em `docs/ARCHITECTURE.md` §6 (identity_profile, visual_profile,
master_reference, voice_profile_id, ...) entra quando os subsistemas que preenchem esses
campos (captura multiview, voice bank, motion bank) existirem — até lá esses dados vivem em
`avatar_metadata` (JSONB livre) sem fingir uma referência que ainda não existe.
"""

import uuid
from datetime import datetime
from typing import Any

from dhf_shared.db import Base
from sqlalchemy import CheckConstraint, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column


class AvatarRecord(Base):
    __tablename__ = "avatars"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_avatars_version_positive"),
        CheckConstraint(
            "status IN ('draft', 'identity_locked', 'multiview_in_progress', "
            "'multiview_approved', 'mesh_in_progress', 'mesh_approved', 'rigged', "
            "'materials_approved', 'face_approved', 'voice_approved', "
            "'motion_approved', 'master_approved', 'production_ready')",
            name="ck_avatars_status_valid",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft")
    # Nome do atributo Python evita colidir com `Base.metadata` (reservado pelo SQLAlchemy).
    avatar_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
