"""Configuração do GoogleDriveStorageProvider via variáveis de ambiente.

Fica em `dhf_storage` (não em `dhf_shared.config.Settings`) de propósito: cada provider
externo (Storage aqui; Voice, Director AI etc. nas próximas fases) traz o próprio bloco de
configuração, lido do mesmo `.env`, sem inchar o Settings central que todo processo carrega.
"""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from dhf_storage.drive_api import UPLOAD_CHUNK_GRANULARITY


class GoogleDriveAuthMode(StrEnum):
    AUTO = "auto"
    SERVICE_ACCOUNT = "service_account"
    OAUTH_USER = "oauth_user"


class GoogleDriveSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # A root V1 é criada pelo app com drive.file. ID explícito é especialmente útil em
    # produção; no desenvolvimento ele também pode vir do state file persistido.
    google_drive_root_folder_name: str = "CRIADOR DE VIDEO — STORAGE"
    google_drive_root_folder_id: str = ""
    google_drive_root_state_file: str = ""

    # AUTO detecta a única fonte configurada. Em produção, prefira declarar o modo para
    # que uma variável inesperada não troque a identidade que acessa o Drive.
    google_drive_auth_mode: GoogleDriveAuthMode = GoogleDriveAuthMode.AUTO

    # Shared Drive + Service Account (ou pasta explicitamente compartilhada com a conta de
    # serviço). Exatamente uma fonte JSON/FILE dentro deste modo.
    google_drive_service_account_json: str = ""
    google_drive_service_account_file: str = ""

    # My Drive + OAuth User. O arquivo/JSON é a credencial de usuário autorizado gerada por
    # `dhf-storage authorize`; contém refresh token e é segredo. Exatamente uma fonte.
    google_drive_oauth_user_json: str = ""
    google_drive_oauth_user_file: str = ""

    # Alternativa ao JSON de OAuth Client baixado: o bootstrap Desktop pode construir a
    # configuração a partir deste par fornecido por secret/env.
    google_drive_client_id: str = ""
    google_drive_client_secret: str = ""

    # Opcional para Shared Drive. Quando preenchido, as listagens usam corpora=drive e
    # driveId; todas as mutações já enviam supportsAllDrives=true.
    google_drive_shared_drive_id: str = ""

    google_drive_request_timeout_s: float = 30.0
    google_drive_upload_chunk_size_bytes: int = 8 * 1024 * 1024
    google_drive_download_chunk_size_bytes: int = 8 * 1024 * 1024
    google_drive_max_retries: int = 5
    google_drive_retry_base_delay_s: float = 1.0
    google_drive_status_cache_ttl_s: float = 30.0

    @field_validator("google_drive_upload_chunk_size_bytes")
    @classmethod
    def validate_upload_chunk_size(cls, value: int) -> int:
        if value <= 0 or value % UPLOAD_CHUNK_GRANULARITY:
            raise ValueError("deve ser múltiplo positivo de 256 KiB")
        return value

    @field_validator("google_drive_download_chunk_size_bytes")
    @classmethod
    def validate_download_chunk_size(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("deve ser positivo")
        return value

    @field_validator("google_drive_request_timeout_s")
    @classmethod
    def validate_positive_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("deve ser positivo")
        return value

    @field_validator("google_drive_retry_base_delay_s", "google_drive_status_cache_ttl_s")
    @classmethod
    def validate_nonnegative_float(cls, value: float) -> float:
        if value < 0:
            raise ValueError("não pode ser negativo")
        return value

    @field_validator("google_drive_max_retries")
    @classmethod
    def validate_max_retries(cls, value: int) -> int:
        if value < 0:
            raise ValueError("não pode ser negativo")
        return value

    @model_validator(mode="after")
    def validate_oauth_client_pair(self):
        if bool(self.google_drive_client_id.strip()) != bool(
            self.google_drive_client_secret.strip()
        ):
            raise ValueError(
                "GOOGLE_DRIVE_CLIENT_ID e GOOGLE_DRIVE_CLIENT_SECRET devem ser configurados juntos"
            )
        return self

    @property
    def has_credential_source(self) -> bool:
        return bool(
            self.google_drive_service_account_json.strip()
            or self.google_drive_service_account_file.strip()
            or self.google_drive_oauth_user_json.strip()
            or self.google_drive_oauth_user_file.strip()
        )

    @property
    def root_state_path(self) -> Path | None:
        if self.google_drive_root_state_file.strip():
            return Path(self.google_drive_root_state_file).expanduser().resolve()
        if self.google_drive_oauth_user_file.strip():
            token_path = Path(self.google_drive_oauth_user_file).expanduser().resolve()
            return token_path.with_name(f"{token_path.stem}.storage-state.json")
        return None


@lru_cache
def get_google_drive_settings() -> GoogleDriveSettings:
    return GoogleDriveSettings()
