"""Contratos de Storage — interface `StorageProvider` e os schemas que ela usa.

`packages/schemas` é o lugar certo para isto (e não `services/storage`, que contém a
implementação `GoogleDriveStorageProvider`): qualquer domínio futuro que precise gravar ou
ler ativos (Avatar Registry na Fase 3, Voice Bank na Fase 4, ...) depende só deste contrato,
nunca da implementação concreta nem de `google-auth`/`httpx`.

Ver `docs/ARCHITECTURE.md` §5-6 e `docs/STORAGE_GOOGLE_DRIVE.md` para o desenho completo.
"""

from datetime import datetime
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel


class StorageConnectionStatus(StrEnum):
    NOT_CONFIGURED = "not_configured"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DEGRADED = "degraded"
    ERROR = "error"


class TreeValidationResult(BaseModel):
    expected: list[str]
    found: list[str]
    missing: list[str]
    unexpected: list[str]
    valid: bool


class StorageStatus(BaseModel):
    status: StorageConnectionStatus
    detail: str | None = None
    root_folder_id: str | None = None
    tree: TreeValidationResult | None = None
    checked_at: datetime


class StorageManifestEntry(BaseModel):
    remote_path: str
    provider_id: str
    size_bytes: int
    mime_type: str
    checksum: str | None = None
    version: str | None = None
    modified_at: datetime
    web_view_url: str | None = None


class SyncReport(BaseModel):
    uploaded: list[str]
    skipped_unchanged: list[str]
    failed: list[tuple[str, str]]
    duration_s: float


class StorageError(Exception):
    """Base de erros de storage — sempre real, nunca engolido em sucesso falso."""


class StorageNotConfiguredError(StorageError):
    """Levantado por operações (não pelo status check) quando não há credencial válida."""


class StoragePermanentDeleteBlockedError(StorageError):
    """delete() fora da área de scratch exige allow_permanent=True explícito."""


class StorageProvider(Protocol):
    """Ver seção 67 do prompt-mestre (Provider Pattern) e seção 6 (métodos)."""

    async def get_status(self, *, force_refresh: bool = False) -> StorageStatus: ...

    async def upload(self, local_path: str, remote_path: str) -> StorageManifestEntry: ...

    async def download(self, remote_path: str, local_path: str) -> None: ...

    async def exists(self, remote_path: str) -> bool: ...

    async def delete(self, remote_path: str, *, allow_permanent: bool = False) -> None: ...

    async def list(self, prefix: str) -> list[StorageManifestEntry]: ...

    async def move(self, src: str, dst: str) -> None: ...

    async def copy(self, src: str, dst: str) -> None: ...

    async def get_metadata(self, remote_path: str) -> StorageManifestEntry: ...

    async def sync(self, local_dir: str, remote_dir: str) -> SyncReport: ...
