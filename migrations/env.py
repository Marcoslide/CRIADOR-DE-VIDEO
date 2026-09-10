"""Ambiente Alembic. A URL de conexão (síncrona, via psycopg) vem de dhf_shared.config,
nunca hardcoded — o mesmo `.env` usado pela API define o alvo das migrations.
"""

from logging.config import fileConfig

from alembic import context
from dhf_shared.config import get_settings
from dhf_shared.db import Base
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url_sync)

# Metadata alvo do autogenerate. Vazio na Fase 1 (nenhum modelo de domínio ainda) —
# populado a partir da Fase 3 conforme os modelos de core/<dominio>/models.py forem
# importados aqui.
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
