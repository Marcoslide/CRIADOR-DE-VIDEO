"""Contratos Pydantic do Avatar Factory Control Plane (request/response da API)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from dhf_avatars.schemas import AvatarStatus
from pydantic import BaseModel, Field

from dhf_avatar_factory.enums import (
    DerivedAssetStatus,
    DerivedAssetType,
    GateDecisionAction,
    HardwareRequirement,
    IdentityLockStatus,
    JobContractStatus,
    JobContractType,
    QAStatus,
    QualityGateName,
    QualityGateStatus,
    ReferenceAssetCategory,
    RejectionReason,
)

# --- Identity Lock — sub-specs estruturados (seção 6) ---------------------------------


class FaceIdentitySpec(BaseModel):
    face_shape: str | None = None
    symmetry_notes: str | None = None
    nose_shape: str | None = None
    jaw_shape: str | None = None
    cheekbones: str | None = None


class EyeIdentitySpec(BaseModel):
    eye_shape: str | None = None
    eye_distance: str | None = None
    eye_color: str | None = None
    iris_pattern: str | None = None


class MouthIdentitySpec(BaseModel):
    lip_shape: str | None = None
    lip_thickness: str | None = None
    mouth_width: str | None = None
    teeth_alignment: str | None = None
    teeth_color: str | None = None
    has_dental_appliance: bool | None = None


class HairIdentitySpec(BaseModel):
    hairline: str | None = None
    hair_color: str | None = None
    hair_texture: str | None = None
    hair_length: str | None = None
    hair_part: str | None = None


class BodyIdentitySpec(BaseModel):
    build: str | None = None
    skin_tone: str | None = None
    skin_marks: str | None = None
    ear_shape: str | None = None
    ear_visibility: str | None = None


class HandIdentitySpec(BaseModel):
    hand_shape: str | None = None
    nail_notes: str | None = None


class ClothingIdentitySpec(BaseModel):
    base_clothing_description: str | None = None


class IdentitySpec(BaseModel):
    face: FaceIdentitySpec = Field(default_factory=FaceIdentitySpec)
    eyes: EyeIdentitySpec = Field(default_factory=EyeIdentitySpec)
    mouth: MouthIdentitySpec = Field(default_factory=MouthIdentitySpec)
    hair: HairIdentitySpec = Field(default_factory=HairIdentitySpec)
    body: BodyIdentitySpec = Field(default_factory=BodyIdentitySpec)
    hands: HandIdentitySpec = Field(default_factory=HandIdentitySpec)
    clothing: ClothingIdentitySpec = Field(default_factory=ClothingIdentitySpec)


class IdentityLockUpsert(BaseModel):
    """Cria ou atualiza o IdentityLock em DRAFT do avatar (nunca toca num já aprovado —
    ver `service_identity.upsert_draft`)."""

    identity_spec: IdentitySpec = Field(default_factory=IdentitySpec)
    height_cm: float | None = Field(default=None, gt=0, lt=300)
    notes: str | None = None
    source_asset_ids: list[UUID] = Field(default_factory=list)


class IdentityLockApprove(BaseModel):
    expected_version: int = Field(ge=1)
    approved_by: str = Field(min_length=1, max_length=200)


class IdentityLock(BaseModel):
    id: UUID
    avatar_id: UUID
    identity_version: int
    status: IdentityLockStatus
    identity_spec: IdentitySpec
    height_cm: float | None
    notes: str | None
    source_asset_ids: list[UUID]
    checksum: str | None
    approved_by: str | None
    approved_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


# --- Reference Asset Manifest (seções 7-12) --------------------------------------------


class ReferenceAssetMetadataIn(BaseModel):
    """Campos de formulário que acompanham o upload multipart (seção 7)."""

    category: ReferenceAssetCategory
    angle: int | None = Field(default=None, ge=0, lt=360)
    capture_type: str | None = None
    side: str | None = None
    orientation: str | None = None
    source: str | None = None


class ReferenceAssetReject(BaseModel):
    expected_version: int = Field(ge=1)
    reason: RejectionReason
    notes: str | None = None
    reviewed_by: str = Field(min_length=1, max_length=200)


class ReferenceAssetApprove(BaseModel):
    expected_version: int = Field(ge=1)
    reviewed_by: str = Field(min_length=1, max_length=200)


class ReferenceAsset(BaseModel):
    id: UUID
    avatar_id: UUID
    capture_version: int
    category: ReferenceAssetCategory
    angle: int | None
    capture_type: str | None
    side: str | None
    orientation: str | None
    source: str | None
    storage_remote_path: str
    storage_provider_id: str | None
    checksum: str | None
    mime_type: str | None
    size_bytes: int | None
    resolution_width: int | None
    resolution_height: int | None
    upload_state: str
    qa_status: QAStatus
    qa_detail: dict[str, Any] | None
    approved: bool
    rejection_reason: RejectionReason | None
    rejection_notes: str | None
    reviewed_by: str | None
    reviewed_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class AngleSlot(BaseModel):
    angle: int
    state: str
    asset_id: UUID | None = None


class MultiviewFamilyProgress(BaseModel):
    total: int
    done: int
    slots: list[AngleSlot] = Field(default_factory=list)


class CategoryProgress(BaseModel):
    category: ReferenceAssetCategory
    state: str
    asset_id: UUID | None = None


class MultiviewCompleteness(BaseModel):
    """Cálculo de progresso (seção 16)."""

    head_360: MultiviewFamilyProgress
    half_body_360: MultiviewFamilyProgress
    full_body_360: MultiviewFamilyProgress
    specialized: list[CategoryProgress]
    expression: list[CategoryProgress]
    specialized_done: int
    specialized_total: int
    expression_done: int
    expression_total: int
    all_required_approved: bool
    open_rejections: int


# --- State transitions / histórico (seção 4/33) ----------------------------------------


class AvatarStateTransition(BaseModel):
    id: UUID
    avatar_id: UUID
    from_status: AvatarStatus
    to_status: AvatarStatus
    actor: str | None
    reason: str | None
    evidence: dict[str, Any] | None
    quality_gate: QualityGateName | None
    avatar_version: int
    created_at: datetime


# --- Quality Gates (seções 17, 22-25) ---------------------------------------------------


class QualityGateDecisionRequest(BaseModel):
    expected_version: int = Field(ge=1)
    actor: str = Field(min_length=1, max_length=200)
    reason: str | None = None
    evidence: dict[str, Any] | None = None


class QualityGate(BaseModel):
    id: UUID
    avatar_id: UUID
    gate_name: QualityGateName
    avatar_version_group: int
    status: QualityGateStatus
    checklist: dict[str, str]
    reason: str | None
    evidence: dict[str, Any] | None
    approved_by: str | None
    approved_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class QualityGateDecision(BaseModel):
    id: UUID
    avatar_id: UUID
    gate_name: QualityGateName
    action: GateDecisionAction
    previous_status: QualityGateStatus
    new_status: QualityGateStatus
    actor: str | None
    reason: str | None
    evidence: dict[str, Any] | None
    created_at: datetime


class GateRequirementCheck(BaseModel):
    """O que falta (ou não) para um gate poder ser aprovado agora — devolvido tanto em
    caso de sucesso quanto de bloqueio, para a UI explicar exatamente o motivo."""

    gate_name: QualityGateName
    satisfied: bool
    missing: list[str] = Field(default_factory=list)
    blocked_reason: str | None = None


# --- Derived assets / job contracts (seções 19-21) ---------------------------------------


class DerivedAsset(BaseModel):
    id: UUID
    avatar_id: UUID
    asset_type: DerivedAssetType
    avatar_version_group: int
    status: DerivedAssetStatus
    storage_remote_path: str | None
    metadata: dict[str, Any]
    version: int
    created_at: datetime
    updated_at: datetime


class JobContract(BaseModel):
    id: UUID
    avatar_id: UUID
    job_type: JobContractType
    input_version: int
    required_assets: list[str]
    output_contract: dict[str, Any]
    hardware_requirement: HardwareRequirement
    status: JobContractStatus
    attempt: int
    error: str | None
    started_at: datetime | None
    completed_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


# --- Readiness / factory aggregate (seções 25-26, 28) ------------------------------------


class ReadinessRequirement(BaseModel):
    key: str
    label: str
    satisfied: bool


class AvatarReadiness(BaseModel):
    avatar_id: UUID
    status: AvatarStatus
    production_ready: bool
    requirements: list[ReadinessRequirement]
    missing: list[str]


class AvatarFactoryView(BaseModel):
    """Resposta agregada de `GET /avatars/{id}/factory` — tudo que o dashboard precisa
    numa chamada só (seção 26/28)."""

    avatar_id: UUID
    name: str
    slug: str
    status: AvatarStatus
    version: int
    identity_lock: IdentityLock | None
    multiview: MultiviewCompleteness
    quality_gates: list[QualityGate]
    derived_assets: list[DerivedAsset]
    job_contracts: list[JobContract]
    readiness: AvatarReadiness
