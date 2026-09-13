"""Regras de negócio do Avatar Factory Control Plane — orquestra `repository.py`
(dados), `gate_requirements.py` (decisão pura de requisito) e `dhf_storage`/`dhf_avatars`
(os dois subsistemas que este pacote consome sem alterar)."""

from __future__ import annotations

import os
import tempfile
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from dhf_avatars import repository as avatars_repository
from dhf_avatars.repository import AvatarVersionConflictError
from dhf_avatars.schemas import ALLOWED_STATUS_TRANSITIONS, AvatarStatus
from dhf_storage.factory import get_storage_provider

from dhf_avatar_factory import gate_requirements, qa_checks, repository
from dhf_avatar_factory.enums import (
    ANGLE_360_CATEGORIES,
    GATE_CHECKLISTS,
    REQUIRED_ANGLES,
    IdentityLockStatus,
    QualityGateName,
    QualityGateStatus,
    ReferenceAssetCategory,
)
from dhf_avatar_factory.models import (
    AvatarStateTransitionRecord,
    DerivedAssetRecord,
    IdentityLockRecord,
    JobContractRecord,
    QualityGateRecord,
    ReferenceAssetRecord,
)
from dhf_avatar_factory.repository import (
    IdentityLockNotDraftError,
    NoIdentityLockForAvatarError,
    ReferenceAssetNotFoundError,
)
from dhf_avatar_factory.schemas import (
    AvatarFactoryView,
    AvatarReadiness,
    AvatarStateTransition,
    DerivedAsset,
    GateRequirementCheck,
    IdentityLock,
    IdentityLockApprove,
    IdentityLockUpsert,
    JobContract,
    QualityGate,
    QualityGateDecisionRequest,
    ReadinessRequirement,
    ReferenceAsset,
    ReferenceAssetApprove,
    ReferenceAssetMetadataIn,
    ReferenceAssetReject,
)

STORAGE_ROOT_FOLDER = "03_AVATAR_IDENTITY_FOTOS"

# P2: nenhum upload sem teto — protege memória do processo e o Storage contra um binário
# absurdamente grande. 25MB é folgado para uma foto de referência (mesmo 4K/RAW comprimido).
MAX_UPLOAD_SIZE_BYTES = 25 * 1024 * 1024

# Streaming do content proxy em pedaços de 1MB — nunca o arquivo inteiro de uma vez além
# deste tamanho de chunk (P2).
CONTENT_PROXY_CHUNK_SIZE = 1024 * 1024


class InvalidReferenceAssetError(Exception):
    pass


class UploadTooLargeError(Exception):
    def __init__(self, max_bytes: int) -> None:
        self.max_bytes = max_bytes
        super().__init__(f"upload excede o limite de {max_bytes} bytes")


class InvalidGateForCurrentStatusError(Exception):
    def __init__(self, gate_name: QualityGateName, current_status: AvatarStatus) -> None:
        self.gate_name = gate_name
        self.current_status = current_status
        super().__init__(f"gate '{gate_name}' não se aplica ao status atual '{current_status}'")


class GateRequirementsNotMetError(Exception):
    def __init__(self, gate_name: QualityGateName, missing: list[str]) -> None:
        self.gate_name = gate_name
        self.missing = missing
        super().__init__(f"requisitos do gate '{gate_name}' não atendidos: {'; '.join(missing)}")


# --- gate -> status alvo (seção 4) — as únicas 10 transições que exigem evidência real;
# as duas transições "_IN_PROGRESS" continuam pelo PATCH genérico de dhf_avatars, que por
# sua vez recusa (P1-1) qualquer uma DESTAS dez sem passar por `approve_gate` -------------
_GATE_TARGET_STATUS: dict[QualityGateName, AvatarStatus] = {
    QualityGateName.IDENTITY: AvatarStatus.IDENTITY_LOCKED,
    QualityGateName.MULTIVIEW: AvatarStatus.MULTIVIEW_APPROVED,
    QualityGateName.MESH: AvatarStatus.MESH_APPROVED,
    QualityGateName.RIG: AvatarStatus.RIGGED,
    QualityGateName.MATERIALS: AvatarStatus.MATERIALS_APPROVED,
    QualityGateName.FACE: AvatarStatus.FACE_APPROVED,
    QualityGateName.VOICE: AvatarStatus.VOICE_APPROVED,
    QualityGateName.MOTION: AvatarStatus.MOTION_APPROVED,
    QualityGateName.MASTER: AvatarStatus.MASTER_APPROVED,
    QualityGateName.PRODUCTION: AvatarStatus.PRODUCTION_READY,
}

_GATE_LABELS: dict[QualityGateName, str] = {
    QualityGateName.IDENTITY: "Identity Lock aprovado",
    QualityGateName.MULTIVIEW: "Multiview aprovado",
    QualityGateName.MESH: "Mesh aprovado",
    QualityGateName.RIG: "Rig concluído",
    QualityGateName.MATERIALS: "Materiais aprovados",
    QualityGateName.FACE: "Face aprovada",
    QualityGateName.VOICE: "Voz aprovada",
    QualityGateName.MOTION: "Motion aprovado",
    QualityGateName.MASTER: "Master aprovado",
}

_READINESS_GATES: tuple[QualityGateName, ...] = (
    QualityGateName.IDENTITY,
    QualityGateName.MULTIVIEW,
    QualityGateName.MESH,
    QualityGateName.RIG,
    QualityGateName.MATERIALS,
    QualityGateName.FACE,
    QualityGateName.VOICE,
    QualityGateName.MOTION,
    QualityGateName.MASTER,
)


def _checklist_for(gate_name: QualityGateName) -> dict[str, str]:
    return dict.fromkeys(GATE_CHECKLISTS.get(gate_name, ()), QualityGateStatus.NOT_TESTED.value)


async def _current_version_group(avatar_id: uuid.UUID) -> int:
    """A geração de identidade OFICIAL vigente (P1-5) — usada uniformemente como
    `capture_version` de novos uploads, `avatar_version_group` de gates/derived assets, e
    filtro de completude do multiview. Um draft de identidade mais novo em andamento NÃO
    move este número até ser aprovado (ver `repository.get_latest_approved_identity_lock`)."""
    lock = await repository.get_latest_approved_identity_lock(avatar_id)
    return lock.identity_version if lock is not None else 1


# --- serialização ORM -> Pydantic --------------------------------------------------------


def _to_identity_lock_schema(record: IdentityLockRecord) -> IdentityLock:
    return IdentityLock(
        id=record.id,
        avatar_id=record.avatar_id,
        identity_version=record.identity_version,
        status=IdentityLockStatus(record.status),
        identity_spec=record.identity_spec,
        height_cm=record.height_cm,
        notes=record.notes,
        source_asset_ids=list(record.source_asset_ids),
        checksum=record.checksum,
        approved_by=record.approved_by,
        approved_at=record.approved_at,
        version=record.version,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _to_reference_asset_schema(record: ReferenceAssetRecord) -> ReferenceAsset:
    return ReferenceAsset(
        id=record.id,
        avatar_id=record.avatar_id,
        capture_version=record.capture_version,
        category=ReferenceAssetCategory(record.category),
        angle=record.angle,
        capture_type=record.capture_type,
        side=record.side,
        orientation=record.orientation,
        source=record.source,
        storage_remote_path=record.storage_remote_path,
        storage_provider_id=record.storage_provider_id,
        checksum=record.checksum,
        mime_type=record.mime_type,
        size_bytes=record.size_bytes,
        resolution_width=record.resolution_width,
        resolution_height=record.resolution_height,
        upload_state=record.upload_state,
        qa_status=record.qa_status,
        qa_detail=record.qa_detail,
        approved=record.approved,
        rejection_reason=record.rejection_reason,
        rejection_notes=record.rejection_notes,
        reviewed_by=record.reviewed_by,
        reviewed_at=record.reviewed_at,
        version=record.version,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _to_transition_schema(record: AvatarStateTransitionRecord) -> AvatarStateTransition:
    return AvatarStateTransition(
        id=record.id,
        avatar_id=record.avatar_id,
        from_status=AvatarStatus(record.from_status),
        to_status=AvatarStatus(record.to_status),
        actor=record.actor,
        reason=record.reason,
        evidence=record.evidence,
        quality_gate=QualityGateName(record.quality_gate) if record.quality_gate else None,
        avatar_version=record.avatar_version,
        created_at=record.created_at,
    )


def _to_gate_schema(record: QualityGateRecord) -> QualityGate:
    return QualityGate(
        id=record.id,
        avatar_id=record.avatar_id,
        gate_name=QualityGateName(record.gate_name),
        avatar_version_group=record.avatar_version_group,
        status=QualityGateStatus(record.status),
        checklist=record.checklist,
        reason=record.reason,
        evidence=record.evidence,
        approved_by=record.approved_by,
        approved_at=record.approved_at,
        version=record.version,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _to_derived_asset_schema(record: DerivedAssetRecord) -> DerivedAsset:
    return DerivedAsset(
        id=record.id,
        avatar_id=record.avatar_id,
        asset_type=record.asset_type,
        avatar_version_group=record.avatar_version_group,
        status=record.status,
        storage_remote_path=record.storage_remote_path,
        metadata=record.asset_metadata,
        version=record.version,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _to_job_contract_schema(record: JobContractRecord) -> JobContract:
    return JobContract(
        id=record.id,
        avatar_id=record.avatar_id,
        job_type=record.job_type,
        input_version=record.input_version,
        required_assets=list(record.required_assets),
        output_contract=record.output_contract,
        hardware_requirement=record.hardware_requirement,
        status=record.status,
        attempt=record.attempt,
        error=record.error,
        started_at=record.started_at,
        completed_at=record.completed_at,
        version=record.version,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


# --- Identity Lock (seções 5-6, 18) -------------------------------------------------------


async def get_identity_lock(avatar_id: uuid.UUID) -> IdentityLock | None:
    record = await repository.get_current_identity_lock(avatar_id)
    return _to_identity_lock_schema(record) if record else None


async def upsert_identity_lock_draft(
    avatar_id: uuid.UUID, payload: IdentityLockUpsert
) -> IdentityLock:
    await avatars_repository.get_avatar(avatar_id)  # 404 honesto se o avatar não existir
    current = await repository.get_current_identity_lock(avatar_id)
    spec_dict = payload.identity_spec.model_dump(mode="json")
    source_ids = payload.source_asset_ids

    if current is None or current.status == IdentityLockStatus.SUPERSEDED:
        next_version = (current.identity_version + 1) if current else 1
        record = await repository.create_identity_lock_draft(
            avatar_id,
            identity_version=next_version,
            identity_spec=spec_dict,
            height_cm=payload.height_cm,
            notes=payload.notes,
            source_asset_ids=source_ids,
        )
        return _to_identity_lock_schema(record)

    if current.status == IdentityLockStatus.APPROVED:
        record = await repository.create_identity_lock_draft(
            avatar_id,
            identity_version=current.identity_version + 1,
            identity_spec=spec_dict,
            height_cm=payload.height_cm,
            notes=payload.notes,
            source_asset_ids=source_ids,
        )
        return _to_identity_lock_schema(record)

    # status == draft: edita a mesma linha em vez de criar uma nova a cada chamada.
    record = await repository.update_identity_lock_draft(
        current.id,
        identity_spec=spec_dict,
        height_cm=payload.height_cm,
        notes=payload.notes,
        source_asset_ids=source_ids,
        expected_version=current.version,
    )
    return _to_identity_lock_schema(record)


async def approve_identity_lock(avatar_id: uuid.UUID, payload: IdentityLockApprove) -> IdentityLock:
    current = await repository.get_current_identity_lock(avatar_id)
    if current is None:
        raise NoIdentityLockForAvatarError(avatar_id)
    if current.status != IdentityLockStatus.DRAFT:
        raise IdentityLockNotDraftError
    record, _new_version_group = await repository.approve_identity_lock(
        current.id, approved_by=payload.approved_by, expected_version=payload.expected_version
    )
    return _to_identity_lock_schema(record)


# --- Reference Assets (seções 7-12, P1-2, P1-3) --------------------------------------------


def _guess_extension(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return suffix if suffix else ".jpg"


async def upload_reference_asset(
    avatar_id: uuid.UUID, *, metadata: ReferenceAssetMetadataIn, filename: str, data: bytes
) -> ReferenceAsset:
    avatar = await avatars_repository.get_avatar(avatar_id)

    if len(data) > MAX_UPLOAD_SIZE_BYTES:
        raise UploadTooLargeError(MAX_UPLOAD_SIZE_BYTES)

    is_angle_category = metadata.category in ANGLE_360_CATEGORIES
    if is_angle_category and metadata.angle is None:
        raise InvalidReferenceAssetError(f"categoria '{metadata.category}' exige o campo 'angle'")
    if not is_angle_category and metadata.angle is not None:
        raise InvalidReferenceAssetError(f"'angle' não se aplica à categoria '{metadata.category}'")
    if metadata.angle is not None and metadata.angle not in REQUIRED_ANGLES:
        raise InvalidReferenceAssetError(f"'angle' precisa ser um dos {REQUIRED_ANGLES}")

    existing_checksums = await repository.list_checksums(avatar_id)
    qa_result = qa_checks.run_deterministic_checks(data, existing_checksums=existing_checksums)

    capture_version = await _current_version_group(avatar_id)
    asset_id = uuid.uuid4()
    ext = _guess_extension(filename)
    slot = f"{metadata.angle:03d}" if metadata.angle is not None else metadata.category.value
    # P1-3: o UUID do asset faz parte do path — uma recaptura do MESMO slot nunca aponta
    # para o mesmo objeto remoto que a captura anterior, então o binário antigo nunca é
    # sobrescrito (a linha antiga do banco continua apontando para ele, recuperável).
    remote_path = (
        f"{STORAGE_ROOT_FOLDER}/{avatar.slug}/identity-v{capture_version}/"
        f"multiview-v{capture_version}/{metadata.category.value}/{slot}/{asset_id}{ext}"
    )

    fd, tmp_path = tempfile.mkstemp(suffix=ext)
    try:
        with os.fdopen(fd, "wb") as tmp_file:
            tmp_file.write(data)
        manifest_entry = await get_storage_provider().upload(tmp_path, remote_path)
    finally:
        os.unlink(tmp_path)

    qa_detail: dict[str, Any] = {name: dict(detail) for name, detail in qa_result.checks.items()}
    record = await repository.create_reference_asset(
        avatar_id,
        id=asset_id,
        capture_version=capture_version,
        category=metadata.category.value,
        angle=metadata.angle,
        capture_type=metadata.capture_type,
        side=metadata.side,
        orientation=metadata.orientation,
        source=metadata.source,
        storage_remote_path=manifest_entry.remote_path,
        storage_provider_id=manifest_entry.provider_id,
        checksum=qa_result.checksum,
        mime_type=manifest_entry.mime_type,
        size_bytes=manifest_entry.size_bytes,
        resolution_width=qa_result.width,
        resolution_height=qa_result.height,
        qa_status=qa_result.status.value,
        qa_detail=qa_detail,
    )
    return _to_reference_asset_schema(record)


async def list_reference_assets(
    avatar_id: uuid.UUID, *, category: str | None = None
) -> list[ReferenceAsset]:
    records = await repository.list_reference_assets(avatar_id, category=category)
    return [_to_reference_asset_schema(record) for record in records]


async def _get_reference_asset_for_avatar(
    avatar_id: uuid.UUID, asset_id: uuid.UUID
) -> ReferenceAssetRecord:
    """P1-2: garante que `asset_id` pertence de fato a `avatar_id` — sem isso, qualquer
    avatar conseguia aprovar/rejeitar/baixar o binário de um asset de OUTRO avatar só por
    adivinhar o UUID, já que os três endpoints ignoravam completamente o `avatar_id` da
    URL. 404 (não 403) para não vazar se o asset existe em outro avatar."""
    record = await repository.get_reference_asset(asset_id)
    if record.avatar_id != avatar_id:
        raise ReferenceAssetNotFoundError(asset_id)
    return record


async def get_reference_asset_content(avatar_id: uuid.UUID, asset_id: uuid.UUID) -> tuple[str, str]:
    """Baixa o binário do Storage para um arquivo temporário e devolve seu caminho (para
    o router fazer streaming — P2: nunca carregamos o arquivo inteiro em RAM aqui) e o
    mime type. O chamador é responsável por apagar o arquivo depois de servir a resposta."""
    record = await _get_reference_asset_for_avatar(avatar_id, asset_id)
    fd, tmp_path = tempfile.mkstemp(suffix=_guess_extension(record.storage_remote_path))
    os.close(fd)
    await get_storage_provider().download(record.storage_remote_path, tmp_path)
    return tmp_path, record.mime_type or "application/octet-stream"


async def stream_file_and_cleanup(path: str, *, chunk_size: int) -> AsyncIterator[bytes]:
    try:
        with open(path, "rb") as handle:
            while chunk := handle.read(chunk_size):
                yield chunk
    finally:
        os.unlink(path)


async def approve_reference_asset(
    avatar_id: uuid.UUID, asset_id: uuid.UUID, payload: ReferenceAssetApprove
) -> ReferenceAsset:
    await _get_reference_asset_for_avatar(avatar_id, asset_id)
    record = await repository.review_reference_asset(
        asset_id,
        approved=True,
        rejection_reason=None,
        rejection_notes=None,
        reviewed_by=payload.reviewed_by,
        expected_version=payload.expected_version,
    )
    return _to_reference_asset_schema(record)


async def reject_reference_asset(
    avatar_id: uuid.UUID, asset_id: uuid.UUID, payload: ReferenceAssetReject
) -> ReferenceAsset:
    await _get_reference_asset_for_avatar(avatar_id, asset_id)
    record = await repository.review_reference_asset(
        asset_id,
        approved=False,
        rejection_reason=payload.reason.value,
        rejection_notes=payload.notes,
        reviewed_by=payload.reviewed_by,
        expected_version=payload.expected_version,
    )
    return _to_reference_asset_schema(record)


async def get_multiview_completeness(avatar_id: uuid.UUID):
    assets = await repository.list_reference_assets(avatar_id)
    capture_version = await _current_version_group(avatar_id)
    return gate_requirements.compute_multiview_completeness(assets, capture_version=capture_version)


# --- Quality Gates (seções 17, 22-25, P1-4, P1-5) -------------------------------------------


async def list_quality_gates(avatar_id: uuid.UUID) -> list[QualityGate]:
    version_group = await _current_version_group(avatar_id)
    gates = []
    for gate_name in QualityGateName:
        record = await repository.get_or_create_gate(
            avatar_id,
            gate_name.value,
            version_group=version_group,
            checklist=_checklist_for(gate_name),
        )
        gates.append(_to_gate_schema(record))
    return gates


async def _check_requirements(
    avatar_id: uuid.UUID, gate_name: QualityGateName, *, version_group: int
) -> GateRequirementCheck:
    if gate_name == QualityGateName.IDENTITY:
        lock = await repository.get_latest_approved_identity_lock(avatar_id)
        return gate_requirements.check_identity_gate(lock)
    if gate_name == QualityGateName.MULTIVIEW:
        lock = await repository.get_latest_approved_identity_lock(avatar_id)
        assets = await repository.list_reference_assets(avatar_id)
        return gate_requirements.check_multiview_gate(lock, assets, capture_version=version_group)
    if gate_name == QualityGateName.PRODUCTION:
        gates = await repository.list_gates(avatar_id)
        statuses = {
            QualityGateName(g.gate_name): g.status
            for g in gates
            if g.avatar_version_group == version_group
        }
        return gate_requirements.check_production_gate(statuses)
    derived = await repository.list_derived_assets(avatar_id, version_group=version_group)
    return gate_requirements.check_gpu_dependent_gate(gate_name, derived)


async def approve_gate(
    avatar_id: uuid.UUID, gate_name: QualityGateName, payload: QualityGateDecisionRequest
) -> tuple[QualityGate, AvatarStateTransition | None]:
    avatar = await avatars_repository.get_avatar(avatar_id)
    if avatar.version != payload.expected_version:
        raise AvatarVersionConflictError(avatar_id, payload.expected_version)

    current_status = AvatarStatus(avatar.status)
    target_status = _GATE_TARGET_STATUS[gate_name]
    if target_status not in ALLOWED_STATUS_TRANSITIONS.get(current_status, set()):
        raise InvalidGateForCurrentStatusError(gate_name, current_status)

    version_group = await _current_version_group(avatar_id)
    requirement_check = await _check_requirements(avatar_id, gate_name, version_group=version_group)
    if not requirement_check.satisfied:
        raise GateRequirementsNotMetError(gate_name, requirement_check.missing)

    # P1-4: tudo (avançar o avatar, marcar o gate PASS, logar a decisão e a transição)
    # acontece numa ÚNICA transação — ver `repository.approve_gate_atomic`.
    gate_record, transition_record, _avatar_record = await repository.approve_gate_atomic(
        avatar_id,
        gate_name=gate_name.value,
        current_status=current_status.value,
        target_status=target_status.value,
        expected_avatar_version=avatar.version,
        version_group=version_group,
        checklist=_checklist_for(gate_name),
        reason=payload.reason,
        actor=payload.actor,
        evidence=payload.evidence,
    )
    return _to_gate_schema(gate_record), _to_transition_schema(transition_record)


async def reject_gate(
    avatar_id: uuid.UUID, gate_name: QualityGateName, payload: QualityGateDecisionRequest
) -> QualityGate:
    avatar = await avatars_repository.get_avatar(avatar_id)
    if avatar.version != payload.expected_version:
        raise AvatarVersionConflictError(avatar_id, payload.expected_version)

    version_group = await _current_version_group(avatar_id)
    updated_gate = await repository.reject_gate_atomic(
        avatar_id,
        gate_name=gate_name.value,
        version_group=version_group,
        checklist=_checklist_for(gate_name),
        reason=payload.reason,
        actor=payload.actor,
        evidence=payload.evidence,
    )
    return _to_gate_schema(updated_gate)


# --- Histórico / readiness / view agregada (seções 25, 26, 28, 33) ------------------------


async def get_history(avatar_id: uuid.UUID) -> list[AvatarStateTransition]:
    records = await repository.list_state_transitions(avatar_id)
    return [_to_transition_schema(record) for record in records]


async def get_readiness(avatar_id: uuid.UUID) -> AvatarReadiness:
    avatar = await avatars_repository.get_avatar(avatar_id)
    version_group = await _current_version_group(avatar_id)
    gates = await repository.list_gates(avatar_id)
    status_by_gate = {
        g.gate_name: g.status for g in gates if g.avatar_version_group == version_group
    }

    requirements = []
    missing = []
    for gate_name in _READINESS_GATES:
        satisfied = status_by_gate.get(gate_name.value) == QualityGateStatus.PASS.value
        requirements.append(
            ReadinessRequirement(
                key=gate_name.value, label=_GATE_LABELS[gate_name], satisfied=satisfied
            )
        )
        if not satisfied:
            missing.append(gate_name.value)

    status = AvatarStatus(avatar.status)
    return AvatarReadiness(
        avatar_id=avatar.id,
        status=status,
        production_ready=status == AvatarStatus.PRODUCTION_READY,
        requirements=requirements,
        missing=missing,
    )


async def list_derived_assets(avatar_id: uuid.UUID) -> list[DerivedAsset]:
    version_group = await _current_version_group(avatar_id)
    records = await repository.ensure_derived_asset_placeholders(
        avatar_id, avatar_version_group=version_group
    )
    return [_to_derived_asset_schema(record) for record in records]


async def list_job_contracts(avatar_id: uuid.UUID) -> list[JobContract]:
    records = await repository.ensure_default_job_contracts(avatar_id, input_version=1)
    return [_to_job_contract_schema(record) for record in records]


async def get_factory_view(avatar_id: uuid.UUID) -> AvatarFactoryView:
    avatar = await avatars_repository.get_avatar(avatar_id)
    identity_lock = await get_identity_lock(avatar_id)
    multiview = await get_multiview_completeness(avatar_id)
    gates = await list_quality_gates(avatar_id)
    derived_assets = await list_derived_assets(avatar_id)
    job_contracts = await list_job_contracts(avatar_id)
    readiness = await get_readiness(avatar_id)

    return AvatarFactoryView(
        avatar_id=avatar.id,
        name=avatar.name,
        slug=avatar.slug,
        status=AvatarStatus(avatar.status),
        version=avatar.version,
        identity_lock=identity_lock,
        multiview=multiview,
        quality_gates=gates,
        derived_assets=derived_assets,
        job_contracts=job_contracts,
        readiness=readiness,
    )
