"""Acesso a dados do Avatar Registry — só SQL/ORM aqui, nenhuma regra de negócio (isso é
`service.py`). Toda operação abre e fecha sua própria sessão (mesmo padrão de
`dhf_shared.db.get_session`, mas sem depender do request scope do FastAPI — repositórios
também precisam funcionar fora de uma requisição, ex.: em jobs do worker no futuro)."""

import uuid
from typing import Any

from dhf_shared.db import get_sessionmaker
from sqlalchemy import select

from dhf_avatars.models import AvatarRecord


class AvatarNotFoundError(Exception):
    def __init__(self, avatar_id: uuid.UUID) -> None:
        self.avatar_id = avatar_id
        super().__init__(f"avatar {avatar_id} não encontrado")


class AvatarSlugConflictError(Exception):
    def __init__(self, slug: str) -> None:
        self.slug = slug
        super().__init__(f"slug '{slug}' já em uso")


async def create_avatar(name: str, slug: str, metadata: dict[str, Any]) -> AvatarRecord:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        existing = await session.scalar(select(AvatarRecord).where(AvatarRecord.slug == slug))
        if existing is not None:
            raise AvatarSlugConflictError(slug)
        record = AvatarRecord(name=name, slug=slug, avatar_metadata=metadata)
        session.add(record)
        await session.commit()
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
) -> AvatarRecord:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        record = await session.get(AvatarRecord, avatar_id)
        if record is None:
            raise AvatarNotFoundError(avatar_id)
        changed = False
        if name is not None and name != record.name:
            record.name = name
            changed = True
        if metadata is not None and metadata != record.avatar_metadata:
            record.avatar_metadata = metadata
            changed = True
        if status is not None and status != record.status:
            record.status = status
            changed = True
        if changed:
            record.version += 1
        await session.commit()
        await session.refresh(record)
        return record
