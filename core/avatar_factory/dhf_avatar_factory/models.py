"""ORM do Avatar Factory Control Plane — tabelas novas que evoluem `dhf_avatars.models`
sem alterá-la. Mesmo padrão de `AvatarRecord`: enums de domínio guardados como `String` +
`CheckConstraint` (não `Enum` nativo do Postgres, para trocar valores só com migration de
constraint, igual já é feito em `dhf_avatars`).

FKs para `avatars.id` usam `ondelete="CASCADE"`: um avatar só pode ser apagado fisicamente
enquanto está em DRAFT (regra já existente em `dhf_avatars.service.delete_avatar`, não
alterada aqui) — nesse ponto do pipeline nenhuma dessas tabelas-filhas pode conter nada
"aprovado" de verdade ainda, então cascatear é limpeza segura, não perda de trabalho
aprovado.
"""

import uuid
from datetime import datetime
from typing import Any

from dhf_shared.db import Base
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column


def _avatar_fk() -> ForeignKey:
    # Uma instância NOVA por coluna — um `ForeignKey` do SQLAlchemy não pode ser
    # compartilhado entre múltiplas colunas (cada uma vira "parent" dele internamente).
    return ForeignKey("avatars.id", ondelete="CASCADE")


class IdentityLockRecord(Base):
    """Uma linha por versão de identidade (seção 5). Uma vez `approved`, nunca é
    atualizada de novo — travar uma nova identidade cria uma NOVA linha com
    `identity_version` incrementada e marca a anterior `superseded` (nunca sobrescreve)."""

    __tablename__ = "avatar_identity_locks"
    __table_args__ = (
        CheckConstraint("identity_version >= 1", name="ck_identity_locks_version_positive"),
        CheckConstraint(
            "status IN ('draft', 'approved', 'superseded')",
            name="ck_identity_locks_status_valid",
        ),
        CheckConstraint("version >= 1", name="ck_identity_locks_optimistic_version_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    avatar_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _avatar_fk(), nullable=False)
    identity_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")

    # Estrutura versionável (seção 6): FaceIdentitySpec/EyeIdentitySpec/MouthIdentitySpec/
    # HairIdentitySpec/BodyIdentitySpec/HandIdentitySpec/ClothingIdentitySpec — a validação
    # de forma/tipo acontece na camada Pydantic (schemas.py), não no banco; JSONB aqui é
    # só a persistência, igual ao padrão já estabelecido por `avatar_metadata`.
    identity_spec: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    height_cm: Mapped[float | None] = mapped_column(nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_asset_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    reference_manifest: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)

    approved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ReferenceAssetRecord(Base):
    """Metadata de uma imagem/vídeo de referência (seção 7) — nunca o binário em si; o
    binário vive no Storage (`dhf_storage`/`dhf_schemas.storage.StorageProvider`),
    `storage_remote_path` é a única referência a ele."""

    __tablename__ = "avatar_reference_assets"
    __table_args__ = (
        CheckConstraint(
            "upload_state IN ('uploaded', 'qa_pending', 'approved', 'rejected')",
            name="ck_reference_assets_upload_state_valid",
        ),
        CheckConstraint(
            "qa_status IN ('pass', 'warn', 'fail', 'not_checked', 'requires_human', "
            "'requires_model')",
            name="ck_reference_assets_qa_status_valid",
        ),
        CheckConstraint(
            "angle IS NULL OR (angle >= 0 AND angle < 360 AND angle % 10 = 0)",
            name="ck_reference_assets_angle_valid",
        ),
        CheckConstraint(
            "capture_version >= 1", name="ck_reference_assets_capture_version_positive"
        ),
        CheckConstraint("version >= 1", name="ck_reference_assets_optimistic_version_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    avatar_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _avatar_fk(), nullable=False)
    capture_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    angle: Mapped[int | None] = mapped_column(Integer, nullable=True)
    capture_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    side: Mapped[str | None] = mapped_column(String(20), nullable=True)
    orientation: Mapped[str | None] = mapped_column(String(40), nullable=True)
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)

    storage_remote_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    storage_provider_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    resolution_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolution_height: Mapped[int | None] = mapped_column(Integer, nullable=True)

    upload_state: Mapped[str] = mapped_column(String(20), nullable=False, default="uploaded")
    qa_status: Mapped[str] = mapped_column(String(20), nullable=False, default="not_checked")
    qa_detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    approved: Mapped[bool] = mapped_column(nullable=False, default=False)
    rejection_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    rejection_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AvatarStateTransitionRecord(Base):
    """Histórico imutável de transição de status (seção 4/33) — INSERT-only, nunca
    UPDATE/DELETE. Uma linha por avanço real de `AvatarRecord.status`."""

    __tablename__ = "avatar_state_transitions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    avatar_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _avatar_fk(), nullable=False)
    from_status: Mapped[str] = mapped_column(String(40), nullable=False)
    to_status: Mapped[str] = mapped_column(String(40), nullable=False)
    actor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    quality_gate: Mapped[str | None] = mapped_column(String(20), nullable=True)
    avatar_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class QualityGateRecord(Base):
    """Estado ATUAL de um gate para um avatar (seções 17, 22-24) — uma linha por
    (avatar_id, gate_name). As decisões que o levaram até aqui ficam em
    `QualityGateDecisionRecord` (append-only, seção 33)."""

    __tablename__ = "avatar_quality_gates"
    __table_args__ = (
        CheckConstraint(
            "gate_name IN ('identity', 'multiview', 'mesh', 'rig', 'materials', 'face', "
            "'voice', 'motion', 'master', 'production')",
            name="ck_quality_gates_name_valid",
        ),
        CheckConstraint(
            "status IN ('not_tested', 'pass', 'warn', 'fail', 'requires_human', 'requires_model')",
            name="ck_quality_gates_status_valid",
        ),
        CheckConstraint("version >= 1", name="ck_quality_gates_optimistic_version_positive"),
        UniqueConstraint("avatar_id", "gate_name", name="uq_quality_gates_avatar_gate"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    avatar_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _avatar_fk(), nullable=False)
    gate_name: Mapped[str] = mapped_column(String(20), nullable=False)
    avatar_version_group: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="not_tested")
    checklist: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class QualityGateDecisionRecord(Base):
    """Log append-only de toda aprovação/rejeição/recaptura pedida sobre um gate (seção
    33) — INSERT-only, nunca UPDATE/DELETE."""

    __tablename__ = "avatar_quality_gate_decisions"
    __table_args__ = (
        CheckConstraint(
            "action IN ('approve', 'reject', 'request_recapture')",
            name="ck_gate_decisions_action_valid",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    avatar_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _avatar_fk(), nullable=False)
    gate_name: Mapped[str] = mapped_column(String(20), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    previous_status: Mapped[str] = mapped_column(String(20), nullable=False)
    new_status: Mapped[str] = mapped_column(String(20), nullable=False)
    # A qual geração de identidade (seção 18 / P1-5) esta decisão pertence — preserva o
    # rastro de qual version group estava "PASS" mesmo depois que `QualityGateRecord` é
    # resetado para NOT_TESTED por uma nova identidade aprovada.
    avatar_version_group: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    actor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DerivedAssetRecord(Base):
    """Placeholder para artefatos futuros gerados por GPU (seção 19) — `status` começa e
    permanece `not_generated` até a RTX 4090 real existir; nenhum valor aqui é fabricado."""

    __tablename__ = "avatar_derived_assets"
    __table_args__ = (
        CheckConstraint(
            "asset_type IN ('reconstructed_mesh', 'retopology_mesh', 'texture_albedo', "
            "'texture_normal', 'texture_roughness', 'groom', 'metahuman_asset', 'rig', "
            "'facial_rig', 'lod', 'thumbnail', 'preview_render')",
            name="ck_derived_assets_type_valid",
        ),
        CheckConstraint(
            "status IN ('not_generated', 'queued', 'generating', 'generated', 'failed')",
            name="ck_derived_assets_status_valid",
        ),
        CheckConstraint("version >= 1", name="ck_derived_assets_optimistic_version_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    avatar_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _avatar_fk(), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(30), nullable=False)
    avatar_version_group: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="not_generated")
    storage_remote_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    asset_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class JobContractRecord(Base):
    """Contrato de job futuro (seção 20) — descreve o que UM DIA vai rodar na GPU.
    Nenhuma linha aqui dispara execução real; `status` fica `pending`/`blocked` até o nó
    RTX 4090 existir e um executor real ser construído (fora do escopo desta missão)."""

    __tablename__ = "avatar_job_contracts"
    __table_args__ = (
        CheckConstraint(
            "job_type IN ('multiview_reconstruction', 'mesh_refinement', "
            "'texture_generation', 'metahuman_conversion', 'facial_rig', 'groom_build', "
            "'material_build', 'quality_render')",
            name="ck_job_contracts_type_valid",
        ),
        CheckConstraint(
            "hardware_requirement IN ('cpu', 'gpu_any', 'rtx_class', 'rtx_4090', 'ai_heavy')",
            name="ck_job_contracts_hardware_valid",
        ),
        CheckConstraint(
            "status IN ('pending', 'ready', 'blocked', 'running', 'completed', 'failed', "
            "'cancelled')",
            name="ck_job_contracts_status_valid",
        ),
        CheckConstraint("attempt >= 0", name="ck_job_contracts_attempt_non_negative"),
        CheckConstraint("version >= 1", name="ck_job_contracts_optimistic_version_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    avatar_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _avatar_fk(), nullable=False)
    job_type: Mapped[str] = mapped_column(String(30), nullable=False)
    input_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    required_assets: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    output_contract: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    hardware_requirement: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
