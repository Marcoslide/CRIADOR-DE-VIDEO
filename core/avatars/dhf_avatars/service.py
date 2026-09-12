"""Regras de negócio do Avatar Registry — hoje só a validação da máquina de estados
(seção 12). Cresce a partir da Fase 3 conforme identity/multiview/mesh entrarem."""

import uuid

from dhf_avatars import repository
from dhf_avatars.models import AvatarRecord
from dhf_avatars.schemas import (
    ALLOWED_STATUS_TRANSITIONS,
    Avatar,
    AvatarCreate,
    AvatarStatus,
    AvatarUpdate,
)


class InvalidStatusTransitionError(Exception):
    def __init__(self, current: AvatarStatus, target: AvatarStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(f"transição {current} -> {target} não é permitida")


def _to_schema(record: AvatarRecord) -> Avatar:
    return Avatar(
        id=record.id,
        name=record.name,
        slug=record.slug,
        version=record.version,
        status=AvatarStatus(record.status),
        metadata=record.avatar_metadata,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


async def create_avatar(payload: AvatarCreate) -> Avatar:
    record = await repository.create_avatar(payload.name, payload.slug, payload.metadata)
    return _to_schema(record)


async def list_avatars() -> list[Avatar]:
    records = await repository.list_avatars()
    return [_to_schema(record) for record in records]


async def get_avatar(avatar_id: uuid.UUID) -> Avatar:
    record = await repository.get_avatar(avatar_id)
    return _to_schema(record)


async def update_avatar(avatar_id: uuid.UUID, payload: AvatarUpdate) -> Avatar:
    if payload.status is not None:
        current = await repository.get_avatar(avatar_id)
        current_status = AvatarStatus(current.status)
        if (
            payload.status != current_status
            and payload.status not in ALLOWED_STATUS_TRANSITIONS[current_status]
        ):
            raise InvalidStatusTransitionError(current_status, payload.status)

    record = await repository.update_avatar(
        avatar_id,
        name=payload.name,
        metadata=payload.metadata,
        status=payload.status.value if payload.status is not None else None,
    )
    return _to_schema(record)
