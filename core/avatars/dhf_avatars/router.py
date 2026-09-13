"""Rotas FastAPI do Avatar Registry — montadas em apps/api (ver app/main.py)."""

import uuid

from fastapi import APIRouter, HTTPException, Query, Response

from dhf_avatars import service
from dhf_avatars.repository import (
    AvatarNotFoundError,
    AvatarSlugConflictError,
    AvatarVersionConflictError,
)
from dhf_avatars.schemas import Avatar, AvatarCreate, AvatarUpdate
from dhf_avatars.service import (
    AvatarDeleteBlockedError,
    GateProtectedStatusError,
    InvalidStatusTransitionError,
)

router = APIRouter(prefix="/avatars", tags=["avatars"])


@router.post("", response_model=Avatar, status_code=201)
async def create_avatar(payload: AvatarCreate) -> Avatar:
    try:
        return await service.create_avatar(payload)
    except AvatarSlugConflictError as exc:
        raise HTTPException(status_code=409, detail=f"slug '{exc.slug}' já em uso") from exc


@router.get("", response_model=list[Avatar])
async def list_avatars() -> list[Avatar]:
    return await service.list_avatars()


@router.get("/{avatar_id}", response_model=Avatar)
async def get_avatar(avatar_id: uuid.UUID) -> Avatar:
    try:
        return await service.get_avatar(avatar_id)
    except AvatarNotFoundError as exc:
        raise HTTPException(status_code=404, detail="avatar não encontrado") from exc


@router.patch("/{avatar_id}", response_model=Avatar)
async def update_avatar(avatar_id: uuid.UUID, payload: AvatarUpdate) -> Avatar:
    try:
        return await service.update_avatar(avatar_id, payload)
    except AvatarNotFoundError as exc:
        raise HTTPException(status_code=404, detail="avatar não encontrado") from exc
    except AvatarVersionConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail=(f"avatar alterado por outra operação; versão esperada: {exc.expected_version}"),
        ) from exc
    except InvalidStatusTransitionError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"transição de status inválida: {exc.current} -> {exc.target}",
        ) from exc
    except GateProtectedStatusError as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                f"status '{exc.status}' só pode ser alcançado aprovando o quality gate "
                "correspondente (POST /avatars/{id}/quality-gates/{gate}/approve), não via "
                "PATCH genérico"
            ),
        ) from exc


@router.delete("/{avatar_id}", status_code=204)
async def delete_avatar(avatar_id: uuid.UUID, expected_version: int = Query(ge=1)) -> Response:
    try:
        await service.delete_avatar(avatar_id, expected_version=expected_version)
    except AvatarNotFoundError as exc:
        raise HTTPException(status_code=404, detail="avatar não encontrado") from exc
    except AvatarVersionConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail=(f"avatar alterado por outra operação; versão esperada: {exc.expected_version}"),
        ) from exc
    except AvatarDeleteBlockedError as exc:
        raise HTTPException(
            status_code=409,
            detail="somente avatares em draft podem ser excluídos",
        ) from exc
    return Response(status_code=204)
