"""Ambiente Alembic. A URL de conexão (síncrona, via psycopg) vem de dhf_shared.config,
nunca hardcoded — o mesmo `.env` usado pela API define o alvo das migrations.
"""

from logging.config import fileConfig

from alembic import context

# Cada domínio de core/<dominio>/models.py precisa ser importado aqui para que suas
# tabelas entrem em Base.metadata (e portanto no autogenerate/target_metadata abaixo) —
# mesmo que a migration em si seja escrita à mão, como as demais deste projeto.
from dhf_avatar_factory.models import (  # noqa: F401
    AvatarStateTransitionRecord,
    DerivedAssetRecord,
    IdentityLockRecord,
    JobContractRecord,
    QualityGateDecisionRecord,
    QualityGateRecord,
    ReferenceAssetRecord,
)
from dhf_avatars.models import AvatarRecord  # noqa: F401
from dhf_shared.config import get_settings
from dhf_shared.db import Base
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
# Alembic usa ConfigParser, onde '%' é interpolação. URLs corretamente percent-encoded
# precisam duplicar o caractere para sobreviver ao round-trip da configuração.
config.set_main_option("sqlalchemy.url", settings.database_url_sync.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
