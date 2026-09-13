"""Regras de negócio do Avatar Registry — hoje só a validação da máquina de estados
(seção 12). Cresce a partir da Fase 3 conforme identity/multiview/mesh entrarem."""

import uuid

from dhf_avatars import repository
from dhf_avatars.models import AvatarRecord
from dhf_avatars.schemas import (
    ALLOWED_STATUS_TRANSITIONS,
    GATE_PROTECTED_STATUSES,
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


class GateProtectedStatusError(Exception):
    """PATCH genérico tentou setar um status que só um quality gate aprovado pode alcançar
    (P1-1). Distinta de `InvalidStatusTransitionError` para a API dar uma mensagem que
    explique O CAMINHO CORRETO (aprovar o gate), não só "transição inválida"."""

    def __init__(self, status: AvatarStatus) -> None:
        self.status = status
        super().__init__(
            f"status '{status}' só pode ser alcançado aprovando o quality gate "
            "correspondente, não via PATCH genérico"
        )


class AvatarDeleteBlockedError(Exception):
    """Evita apagar fisicamente um avatar que já entrou no pipeline produtivo."""


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
    current = await repository.get_avatar(avatar_id)
    if current.version != payload.expected_version:
        raise repository.AvatarVersionConflictError(avatar_id, payload.expected_version)

    if payload.status is not None:
        current_status = AvatarStatus(current.status)
        if payload.status != current_status:
            if payload.status in GATE_PROTECTED_STATUSES:
                raise GateProtectedStatusError(payload.status)
            if payload.status not in ALLOWED_STATUS_TRANSITIONS[current_status]:
                raise InvalidStatusTransitionError(current_status, payload.status)

    status = payload.status.value if payload.status is not None else None
    changed = any(
        (
            payload.name is not None and payload.name != current.name,
            payload.metadata is not None and payload.metadata != current.avatar_metadata,
            status is not None and status != current.status,
        )
    )
    if not changed:
        return _to_schema(current)

    record = await repository.update_avatar(
        avatar_id,
        name=payload.name,
        metadata=payload.metadata,
        status=status,
        expected_version=payload.expected_version,
    )
    return _to_schema(record)


async def delete_avatar(avatar_id: uuid.UUID, *, expected_version: int) -> None:
    current = await repository.get_avatar(avatar_id)
    if current.version != expected_version:
        raise repository.AvatarVersionConflictError(avatar_id, expected_version)
    if AvatarStatus(current.status) != AvatarStatus.DRAFT:
        raise AvatarDeleteBlockedError
    await repository.delete_avatar(avatar_id, expected_version=expected_version)
