"""Configuração central via variáveis de ambiente (.env), compartilhada por api e workers."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    log_level: str = "INFO"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "dhf"
    postgres_user: str = "dhf"
    postgres_password: str = "dhf"

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    celery_broker_url: str = ""
    celery_result_backend: str = ""

    api_cors_origins: list[str] = ["http://localhost:5173"]

    # ---- Fase 5 — Director AI (OpenAI) ------------------------------------------------
    # Vazio = NOT_CONFIGURED honesto (ver app.routers.system_status). Nunca simula conexão.
    openai_api_key: str = ""

    # ---- Fase 7 — Unreal / Audio2Face / MetaHuman (engines de render) -----------------
    # Cada um é NOT_INSTALLED até o caminho/URL apontar para uma instalação real existente
    # (checagem real de arquivo/processo em app.routers.system_status, nunca hardcoded).
    unreal_engine_path: str = ""
    audio2face_path: str = ""
    metahuman_api_url: str = ""

    @property
    def database_url(self) -> str:
        """URL assíncrona (asyncpg) — usada pela aplicação (FastAPI)."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        """URL síncrona (psycopg) — usada pelo Alembic."""
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def resolved_celery_broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def resolved_celery_result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
