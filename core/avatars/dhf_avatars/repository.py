"""Acesso a dados do Avatar Registry — só SQL/ORM aqui, nenhuma regra de negócio (isso é
`service.py`). Toda operação abre e fecha sua própria sessão (mesmo padrão de
`dhf_shared.db.get_session`, mas sem depender do request scope do FastAPI — repositórios
também precisam funcionar fora de uma requisição, ex.: em jobs do worker no futuro)."""

import uuid
from typing import Any

from dhf_shared.db import get_sessionmaker
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from dhf_avatars.models import AvatarRecord
from dhf_avatars.schemas import GATE_PROTECTED_STATUSES

_GATE_PROTECTED_STATUS_VALUES: frozenset[str] = frozenset(s.value for s in GATE_PROTECTED_STATUSES)


class AvatarNotFoundError(Exception):
    def __init__(self, avatar_id: uuid.UUID) -> None:
        self.avatar_id = avatar_id
        super().__init__(f"avatar {avatar_id} não encontrado")


class GateProtectedStatusError(Exception):
    """`update_avatar` recebeu um status gate-protected sem `allow_gate_protected_status=True`
    — P1-1 da correção obrigatória: nenhum caminho de código, nem um bug futuro em outra
    camada, consegue setar esses status sem passar pela transação atômica do quality gate
    (`dhf_avatar_factory.repository.approve_gate_atomic`), a única chamadora autorizada a
    passar essa flag."""

    def __init__(self, status: str) -> None:
        self.status = status
        super().__init__(
            f"status '{status}' só pode ser alcançado via quality gate aprovado, nunca "
            "diretamente por update_avatar"
        )


class AvatarSlugConflictError(Exception):
    def __init__(self, slug: str) -> None:
        self.slug = slug
        super().__init__(f"slug '{slug}' já em uso")


class AvatarVersionConflictError(Exception):
    def __init__(self, avatar_id: uuid.UUID, expected_version: int) -> None:
        self.avatar_id = avatar_id
        self.expected_version = expected_version
        super().__init__(f"avatar {avatar_id} foi alterado depois da versão {expected_version}")


async def create_avatar(name: str, slug: str, metadata: dict[str, Any]) -> AvatarRecord:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        existing = await session.scalar(select(AvatarRecord).where(AvatarRecord.slug == slug))
        if existing is not None:
            raise AvatarSlugConflictError(slug)
        record = AvatarRecord(name=name, slug=slug, avatar_metadata=metadata)
        session.add(record)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            # A restrição UNIQUE do banco é a autoridade final. O pre-check acima melhora
            # a mensagem no caso comum; este catch cobre duas criações concorrentes.
            raise AvatarSlugConflictError(slug) from exc
        await session.refresh(record)
        return record


async def list_avatars() -> list[AvatarRecord]:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        result = await session.scalars(
            select(AvatarRecord).order_by(AvatarRecord.created_at.desc())
        )
        return list(result)


async def get_avatar(avatar_id: uuid.UUID) -> AvatarRecord:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        record = await session.get(AvatarRecord, avatar_id)
        if record is None:
            raise AvatarNotFoundError(avatar_id)
        return record


async def update_avatar(
    avatar_id: uuid.UUID,
    *,
    name: str | None = None,
    metadata: dict[str, Any] | None = None,
    status: str | None = None,
    expected_version: int,
    allow_gate_protected_status: bool = False,
) -> AvatarRecord:
    if (
        status is not None
        and status in _GATE_PROTECTED_STATUS_VALUES
        and not allow_gate_protected_status
    ):
        raise GateProtectedStatusError(status)

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        values: dict[str, Any] = {
            "version": AvatarRecord.version + 1,
            "updated_at": func.now(),
        }
        if name is not None:
            values["name"] = name
        if metadata is not None:
            values["avatar_metadata"] = metadata
        if status is not None:
            values["status"] = status

        statement = (
            update(AvatarRecord)
            .where(
                AvatarRecord.id == avatar_id,
                AvatarRecord.version == expected_version,
            )
            .values(**values)
            .returning(AvatarRecord)
        )
        record = (await session.execute(statement)).scalar_one_or_none()
        if record is None:
            exists = await session.scalar(
                select(AvatarRecord.id).where(AvatarRecord.id == avatar_id)
            )
            if exists is None:
                raise AvatarNotFoundError(avatar_id)
            raise AvatarVersionConflictError(avatar_id, expected_version)
        await session.commit()
        return record


async def delete_avatar(avatar_id: uuid.UUID, *, expected_version: int) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        deleted_id = await session.scalar(
            delete(AvatarRecord)
            .where(
                AvatarRecord.id == avatar_id,
                AvatarRecord.version == expected_version,
                AvatarRecord.status == "draft",
            )
            .returning(AvatarRecord.id)
        )
        if deleted_id is None:
            existing = await session.get(AvatarRecord, avatar_id)
            if existing is None:
                raise AvatarNotFoundError(avatar_id)
            raise AvatarVersionConflictError(avatar_id, expected_version)
        await session.commit()
