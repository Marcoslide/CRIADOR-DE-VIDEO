"""Rotas FastAPI do Avatar Factory Control Plane — sub-recursos de `/avatars/{avatar_id}`
montados ao lado (não em cima) do router de `dhf_avatars` (seção 26)."""

from __future__ import annotations

import uuid

from dhf_avatars.repository import AvatarNotFoundError, AvatarVersionConflictError
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from dhf_avatar_factory import service
from dhf_avatar_factory.enums import QualityGateName, ReferenceAssetCategory
from dhf_avatar_factory.repository import (
    IdentityLockNotDraftError,
    IdentityLockVersionConflictError,
    NoIdentityLockForAvatarError,
    QualityGateNotFoundError,
    QualityGateVersionConflictError,
    ReferenceAssetNotFoundError,
    ReferenceAssetVersionConflictError,
)
from dhf_avatar_factory.schemas import (
    AvatarFactoryView,
    AvatarReadiness,
    AvatarStateTransition,
    DerivedAsset,
    IdentityLock,
    IdentityLockApprove,
    IdentityLockUpsert,
    JobContract,
    MultiviewCompleteness,
    QualityGate,
    QualityGateDecisionRequest,
    ReferenceAsset,
    ReferenceAssetApprove,
    ReferenceAssetMetadataIn,
    ReferenceAssetReject,
)

router = APIRouter(prefix="/avatars", tags=["avatar-factory"])


def _avatar_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="avatar não encontrado")


def _version_conflict(expected_version: int) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail=f"recurso alterado por outra operação; versão esperada: {expected_version}",
    )


_UPLOAD_READ_CHUNK = 1024 * 1024  # 1MB por vez


async def _read_upload_with_limit(file: UploadFile, *, max_bytes: int) -> bytes:
    """Lê em pedaços e aborta assim que ultrapassa `max_bytes` (P2) — um upload de
    vários GB nunca é lido por inteiro só para ser rejeitado depois."""
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(_UPLOAD_READ_CHUNK):
        total += len(chunk)
        if total > max_bytes:
            raise service.UploadTooLargeError(max_bytes)
        chunks.append(chunk)
    return b"".join(chunks)


# --- Identity Lock ------------------------------------------------------------------------


@router.post("/{avatar_id}/identity-lock", response_model=IdentityLock, status_code=201)
async def upsert_identity_lock(avatar_id: uuid.UUID, payload: IdentityLockUpsert) -> IdentityLock:
    try:
        return await service.upsert_identity_lock_draft(avatar_id, payload)
    except AvatarNotFoundError as exc:
        raise _avatar_not_found() from exc
    except IdentityLockVersionConflictError as exc:
        raise _version_conflict(exc.expected_version) from exc


@router.get("/{avatar_id}/identity-lock", response_model=IdentityLock)
async def get_identity_lock(avatar_id: uuid.UUID) -> IdentityLock:
    lock = await service.get_identity_lock(avatar_id)
    if lock is None:
        raise HTTPException(
            status_code=404, detail="nenhum identity lock existe ainda para este avatar"
        )
    return lock


@router.post("/{avatar_id}/identity-lock/approve", response_model=IdentityLock)
async def approve_identity_lock(avatar_id: uuid.UUID, payload: IdentityLockApprove) -> IdentityLock:
    try:
        return await service.approve_identity_lock(avatar_id, payload)
    except NoIdentityLockForAvatarError as exc:
        raise HTTPException(
            status_code=404, detail="nenhum identity lock existe ainda para este avatar"
        ) from exc
    except IdentityLockNotDraftError as exc:
        raise HTTPException(
            status_code=409, detail="só um identity lock em draft pode ser aprovado"
        ) from exc
    except IdentityLockVersionConflictError as exc:
        raise _version_conflict(exc.expected_version) from exc


# --- Reference Assets ----------------------------------------------------------------------


@router.post("/{avatar_id}/references", response_model=ReferenceAsset, status_code=201)
async def upload_reference(
    avatar_id: uuid.UUID,
    category: ReferenceAssetCategory = Form(...),
    angle: int | None = Form(default=None),
    capture_type: str | None = Form(default=None),
    side: str | None = Form(default=None),
    orientation: str | None = Form(default=None),
    source: str | None = Form(default=None),
    file: UploadFile = File(...),
) -> ReferenceAsset:
    if file.content_type is not None and not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=422, detail=f"tipo de arquivo '{file.content_type}' não é uma imagem"
        )
    metadata = ReferenceAssetMetadataIn(
        category=category,
        angle=angle,
        capture_type=capture_type,
        side=side,
        orientation=orientation,
        source=source,
    )
    try:
        data = await _read_upload_with_limit(file, max_bytes=service.MAX_UPLOAD_SIZE_BYTES)
        return await service.upload_reference_asset(
            avatar_id, metadata=metadata, filename=file.filename or "upload.jpg", data=data
        )
    except AvatarNotFoundError as exc:
        raise _avatar_not_found() from exc
    except service.InvalidReferenceAssetError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except service.UploadTooLargeError as exc:
        raise HTTPException(
            status_code=413, detail=f"upload excede o limite de {exc.max_bytes} bytes"
        ) from exc


@router.get("/{avatar_id}/references", response_model=list[ReferenceAsset])
async def list_references(
    avatar_id: uuid.UUID, category: ReferenceAssetCategory | None = Query(default=None)
) -> list[ReferenceAsset]:
    return await service.list_reference_assets(
        avatar_id, category=category.value if category else None
    )


@router.post("/{avatar_id}/references/{asset_id}/approve", response_model=ReferenceAsset)
async def approve_reference(
    avatar_id: uuid.UUID, asset_id: uuid.UUID, payload: ReferenceAssetApprove
) -> ReferenceAsset:
    try:
        return await service.approve_reference_asset(avatar_id, asset_id, payload)
    except ReferenceAssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail="reference asset não encontrado") from exc
    except ReferenceAssetVersionConflictError as exc:
        raise _version_conflict(exc.expected_version) from exc


@router.post("/{avatar_id}/references/{asset_id}/reject", response_model=ReferenceAsset)
async def reject_reference(
    avatar_id: uuid.UUID, asset_id: uuid.UUID, payload: ReferenceAssetReject
) -> ReferenceAsset:
    try:
        return await service.reject_reference_asset(avatar_id, asset_id, payload)
    except ReferenceAssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail="reference asset não encontrado") from exc
    except ReferenceAssetVersionConflictError as exc:
        raise _version_conflict(exc.expected_version) from exc


@router.get("/{avatar_id}/references/{asset_id}/content")
async def get_reference_content(avatar_id: uuid.UUID, asset_id: uuid.UUID) -> StreamingResponse:
    """Proxy do binário guardado no Storage — o viewer 360 do frontend nunca fala com o
    Google Drive diretamente (seção 29). Streaming (P2): o binário nunca é carregado
    inteiro em RAM aqui, só lido em pedaços de `dhf_avatar_factory.service` diretamente
    do arquivo temporário para a resposta HTTP."""
    try:
        tmp_path, mime_type = await service.get_reference_asset_content(avatar_id, asset_id)
    except ReferenceAssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail="reference asset não encontrado") from exc
    return StreamingResponse(
        service.stream_file_and_cleanup(tmp_path, chunk_size=service.CONTENT_PROXY_CHUNK_SIZE),
        media_type=mime_type,
    )


@router.get("/{avatar_id}/multiview", response_model=MultiviewCompleteness)
async def get_multiview(avatar_id: uuid.UUID) -> MultiviewCompleteness:
    return await service.get_multiview_completeness(avatar_id)


# --- Quality Gates -------------------------------------------------------------------------


@router.get("/{avatar_id}/quality-gates", response_model=list[QualityGate])
async def list_quality_gates(avatar_id: uuid.UUID) -> list[QualityGate]:
    return await service.list_quality_gates(avatar_id)


@router.post("/{avatar_id}/quality-gates/{gate}/approve", response_model=QualityGate)
async def approve_quality_gate(
    avatar_id: uuid.UUID, gate: QualityGateName, payload: QualityGateDecisionRequest
) -> QualityGate:
    try:
        updated_gate, _transition = await service.approve_gate(avatar_id, gate, payload)
        return updated_gate
    except AvatarNotFoundError as exc:
        raise _avatar_not_found() from exc
    except AvatarVersionConflictError as exc:
        raise _version_conflict(exc.expected_version) from exc
    except service.InvalidGateForCurrentStatusError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"gate '{exc.gate_name}' não se aplica ao status atual '{exc.current_status}'",
        ) from exc
    except service.GateRequirementsNotMetError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"requisitos do gate '{exc.gate_name}' não atendidos",
                "missing": exc.missing,
            },
        ) from exc
    except QualityGateVersionConflictError as exc:
        raise _version_conflict(exc.expected_version) from exc
    except QualityGateNotFoundError as exc:
        raise HTTPException(status_code=404, detail="quality gate não encontrado") from exc


@router.post("/{avatar_id}/quality-gates/{gate}/reject", response_model=QualityGate)
async def reject_quality_gate(
    avatar_id: uuid.UUID, gate: QualityGateName, payload: QualityGateDecisionRequest
) -> QualityGate:
    try:
        return await service.reject_gate(avatar_id, gate, payload)
    except AvatarNotFoundError as exc:
        raise _avatar_not_found() from exc
    except AvatarVersionConflictError as exc:
        raise _version_conflict(exc.expected_version) from exc
    except QualityGateVersionConflictError as exc:
        raise _version_conflict(exc.expected_version) from exc
    except QualityGateNotFoundError as exc:
        raise HTTPException(status_code=404, detail="quality gate não encontrado") from exc


# --- Histórico / readiness / view agregada --------------------------------------------------


@router.get("/{avatar_id}/history", response_model=list[AvatarStateTransition])
async def get_history(avatar_id: uuid.UUID) -> list[AvatarStateTransition]:
    return await service.get_history(avatar_id)


@router.get("/{avatar_id}/readiness", response_model=AvatarReadiness)
async def get_readiness(avatar_id: uuid.UUID) -> AvatarReadiness:
    try:
        return await service.get_readiness(avatar_id)
    except AvatarNotFoundError as exc:
        raise _avatar_not_found() from exc


@router.get("/{avatar_id}/derived-assets", response_model=list[DerivedAsset])
async def list_derived_assets(avatar_id: uuid.UUID) -> list[DerivedAsset]:
    return await service.list_derived_assets(avatar_id)


@router.get("/{avatar_id}/job-contracts", response_model=list[JobContract])
async def list_job_contracts(avatar_id: uuid.UUID) -> list[JobContract]:
    return await service.list_job_contracts(avatar_id)


@router.get("/{avatar_id}/factory", response_model=AvatarFactoryView)
async def get_factory_view(avatar_id: uuid.UUID) -> AvatarFactoryView:
    try:
        return await service.get_factory_view(avatar_id)
    except AvatarNotFoundError as exc:
        raise _avatar_not_found() from exc
