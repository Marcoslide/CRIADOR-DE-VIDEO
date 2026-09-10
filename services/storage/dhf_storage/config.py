"""Configuração do GoogleDriveStorageProvider via variáveis de ambiente.

Fica em `dhf_storage` (não em `dhf_shared.config.Settings`) de propósito: cada provider
externo (Storage aqui; Voice, Director AI etc. nas próximas fases) traz o próprio bloco de
configuração, lido do mesmo `.env`, sem inchar o Settings central que todo processo carrega.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class GoogleDriveSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Pasta raiz oficial "CRIADOR DE VIDEO" — não é segredo, é só um identificador; sem
    # credencial válida ele não dá acesso a nada.
    google_drive_root_folder_id: str = "13BTUf5Oyp8fb_CT2H0OJ6LeuZKzm3pxE"

    # Exatamente uma das duas deve ser preenchida em produção. Nenhuma delas tem default —
    # ausência de ambas é o caminho normal para NOT_CONFIGURED (dev sem credencial).
    google_drive_service_account_json: str = ""
    google_drive_service_account_file: str = ""

    google_drive_request_timeout_s: float = 30.0
    google_drive_upload_chunk_size_bytes: int = 8 * 1024 * 1024
    google_drive_download_chunk_size_bytes: int = 8 * 1024 * 1024
    google_drive_max_retries: int = 5
    google_drive_retry_base_delay_s: float = 1.0
    google_drive_status_cache_ttl_s: float = 30.0

    @property
    def has_credential_source(self) -> bool:
        return bool(
            self.google_drive_service_account_json.strip()
            or self.google_drive_service_account_file.strip()
        )


@lru_cache
def get_google_drive_settings() -> GoogleDriveSettings:
    return GoogleDriveSettings()
