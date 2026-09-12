"""Camada de banco de dados compartilhada (SQLAlchemy assíncrono).

`Base` é o declarative base para todos os modelos ORM futuros (Fase 3+). Nesta
fase não há tabelas de domínio — apenas a fundação de engine/sessão usada pelos
health checks e, a partir da Fase 3, pelos repositórios de cada domínio.
"""

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from dhf_shared.config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args={"timeout": settings.database_connect_timeout_s},
    )


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Dependency do FastAPI: `session: AsyncSession = Depends(get_session)`."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        yield session
