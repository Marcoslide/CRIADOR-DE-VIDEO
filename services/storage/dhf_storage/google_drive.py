"""GoogleDriveStorageProvider — implementação real de StorageProvider sobre a Drive API v3.

Regras de segurança que este módulo respeita à risca:
- nunca loga o conteúdo de uma credencial, nem o access token;
- nunca finge estar `CONNECTED` — get_status() faz uma chamada real (list_children na raiz);
- nunca cria/renomeia/apaga uma das 18 pastas oficiais de topo, só descobre por nome;
- delete() sem allow_permanent=True só age dentro de SCRATCH_PREFIX, e ali move para a
  lixeira (recuperável) — nunca exclusão definitiva sem o caller pedir explicitamente.
"""

import asyncio
import contextlib
import hashlib
import mimetypes
import os
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import aiofiles
import httpx
from dhf_schemas.storage import (
    StorageConnectionStatus,
    StorageManifestEntry,
    StorageNotConfiguredError,
    StoragePermanentDeleteBlockedError,
    StorageStatus,
    SyncReport,
    TreeValidationResult,
)
from dhf_shared.logging import get_logger

from dhf_storage import drive_api
from dhf_storage.auth import CredentialLoadError, ensure_fresh_token, load_credentials
from dhf_storage.cache import FolderIdCache
from dhf_storage.config import GoogleDriveSettings, get_google_drive_settings
from dhf_storage.tree import (
    OFFICIAL_TOP_LEVEL_FOLDERS,
    SCRATCH_PREFIX,
    is_within_scratch,
    validate_tree,
)

_UPLOAD_MIME_DEFAULT = "application/octet-stream"


class GoogleDriveStorageProvider:
    """Sempre seguro de construir sem credencial — só operações reais falham (nunca
    silenciosamente) quando `get_status()` reportaria NOT_CONFIGURED."""

    def __init__(self, settings: GoogleDriveSettings | None = None) -> None:
        self._settings = settings or get_google_drive_settings()
        self._logger = get_logger(service="storage", provider="google_drive")
        self._cache = FolderIdCache()
        self._client: httpx.AsyncClient | None = None
        self._credentials = None
        self._credential_load_error: CredentialLoadError | None = None
        self._status_cache: StorageStatus | None = None
        self._status_lock = asyncio.Lock()

    # ------------------------------------------------------------------ infra interna

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._settings.google_drive_request_timeout_s)
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _load_credentials_once(self):
        if self._credentials is not None or self._credential_load_error is not None:
            return
        try:
            self._credentials = load_credentials(self._settings)
        except CredentialLoadError as exc:
            self._credential_load_error = exc
            self._logger.error("storage.credential_load_error", error=str(exc))

    async def _get_token(self) -> str:
        self._load_credentials_once()
        if self._credential_load_error is not None:
            raise self._credential_load_error
        if self._credentials is None:
            raise StorageNotConfiguredError(
                "GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON/_FILE não configurados"
            )
        return await asyncio.to_thread(ensure_fresh_token, self._credentials)

    def _require_configured(self) -> None:
        self._load_credentials_once()
        if self._credential_load_error is not None:
            raise self._credential_load_error
        if self._credentials is None:
            raise StorageNotConfiguredError(
                "GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON/_FILE não configurados"
            )

    def _retry_kwargs(self) -> dict:
        return {
            "max_retries": self._settings.google_drive_max_retries,
            "base_delay_s": self._settings.google_drive_retry_base_delay_s,
            "logger": self._logger,
        }

    @staticmethod
    def _split(remote_path: str) -> tuple[list[str], str]:
        parts = [p for p in PurePosixPath(remote_path.strip("/")).parts]
        if not parts:
            raise ValueError("remote_path vazio")
        return parts[:-1], parts[-1]

    async def _resolve_path(self, segments: list[str], *, create_missing: bool) -> str:
        if not segments:
            return self._settings.google_drive_root_folder_id

        top = segments[0]
        if top not in OFFICIAL_TOP_LEVEL_FOLDERS:
            raise ValueError(
                f"'{top}' não é uma das 18 pastas oficiais da árvore do Drive. "
                f"Válidas: {OFFICIAL_TOP_LEVEL_FOLDERS}"
            )

        client = await self._get_client()
        token = await self._get_token()

        parent_id = self._cache.get(top)
        if parent_id is None:
            matches = await drive_api.list_children(
                client,
                token,
                self._settings.google_drive_root_folder_id,
                name=top,
                folders_only=True,
                **self._retry_kwargs(),
            )
            if not matches:
                raise FileNotFoundError(
                    f"pasta oficial '{top}' não encontrada na raiz do Drive "
                    f"({self._settings.google_drive_root_folder_id}) — precisa existir "
                    "manualmente, o provider nunca a cria"
                )
            parent_id = matches[0]["id"]
            self._cache.set(top, parent_id)

        resolved = top
        for segment in segments[1:]:
            resolved = f"{resolved}/{segment}"
            folder_id = self._cache.get(resolved)
            if folder_id is None:
                matches = await drive_api.list_children(
                    client,
                    token,
                    parent_id,
                    name=segment,
                    folders_only=True,
                    **self._retry_kwargs(),
                )
                if matches:
                    folder_id = matches[0]["id"]
                elif create_missing:
                    created = await drive_api.create_folder(
                        client, token, parent_id, segment, **self._retry_kwargs()
                    )
                    folder_id = created["id"]
                    self._logger.info("storage.folder_created", path=resolved)
                else:
                    raise FileNotFoundError(f"pasta '{resolved}' não existe no Drive")
                self._cache.set(resolved, folder_id)
            parent_id = folder_id

        return parent_id

    async def _find_file(self, parent_id: str, filename: str) -> dict | None:
        client = await self._get_client()
        token = await self._get_token()
        matches = await drive_api.list_children(
            client, token, parent_id, name=filename, folders_only=False, **self._retry_kwargs()
        )
        files_only = [m for m in matches if m.get("mimeType") != drive_api.FOLDER_MIME_TYPE]
        return files_only[0] if files_only else None

    def _map_metadata(self, raw: dict, remote_path: str) -> StorageManifestEntry:
        return StorageManifestEntry(
            remote_path=remote_path,
            provider_id=raw["id"],
            size_bytes=int(raw.get("size", 0) or 0),
            mime_type=raw.get("mimeType", _UPLOAD_MIME_DEFAULT),
            checksum=raw.get("md5Checksum"),
            version=None,
            modified_at=datetime.fromisoformat(raw["modifiedTime"].replace("Z", "+00:00")),
            web_view_url=raw.get("webViewLink"),
        )

    @staticmethod
    async def _read_chunks(local_path: str, chunk_size: int) -> AsyncIterator[bytes]:
        async with aiofiles.open(local_path, "rb") as f:
            while True:
                chunk = await f.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    # ------------------------------------------------------------------ status (público)

    async def get_status(self, *, force_refresh: bool = False) -> StorageStatus:
        now = datetime.now(UTC)

        if not force_refresh and self._status_cache is not None:
            age = (now - self._status_cache.checked_at).total_seconds()
            if age < self._settings.google_drive_status_cache_ttl_s:
                return self._status_cache

        if self._status_lock.locked():
            return StorageStatus(
                status=StorageConnectionStatus.CONNECTING,
                detail="verificação de status já em andamento",
                checked_at=now,
            )

        async with self._status_lock:
            self._load_credentials_once()

            if self._credential_load_error is not None:
                status = StorageStatus(
                    status=StorageConnectionStatus.ERROR,
                    detail=str(self._credential_load_error),
                    checked_at=now,
                )
                self._status_cache = status
                return status

            if self._credentials is None:
                status = StorageStatus(
                    status=StorageConnectionStatus.NOT_CONFIGURED,
                    detail="GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON/_FILE não configurados",
                    checked_at=now,
                )
                self._status_cache = status
                return status

            root_id = self._settings.google_drive_root_folder_id
            try:
                client = await self._get_client()
                token = await self._get_token()
                children = await drive_api.list_children(
                    client, token, root_id, folders_only=True, **self._retry_kwargs()
                )
            except Exception as exc:  # noqa: BLE001 - reportado como ERROR, nunca engolido
                self._logger.error("storage.status_check_failed", error=str(exc))
                status = StorageStatus(
                    status=StorageConnectionStatus.ERROR,
                    detail=f"{type(exc).__name__}: {exc}",
                    root_folder_id=root_id,
                    checked_at=now,
                )
                self._status_cache = status
                return status

            tree: TreeValidationResult = validate_tree([c["name"] for c in children])
            status = StorageStatus(
                status=StorageConnectionStatus.CONNECTED
                if tree.valid
                else StorageConnectionStatus.DEGRADED,
                detail=None if tree.valid else f"faltam {len(tree.missing)} pasta(s) oficiais",
                root_folder_id=root_id,
                tree=tree,
                checked_at=now,
            )
            self._status_cache = status
            self._logger.info("storage.status_checked", status=status.status.value)
            return status

    # ------------------------------------------------------------------ StorageProvider

    async def upload(self, local_path: str, remote_path: str) -> StorageManifestEntry:
        self._require_configured()
        folder_segments, filename = self._split(remote_path)
        parent_id = await self._resolve_path(folder_segments, create_missing=True)

        size_bytes = os.path.getsize(local_path)
        mime_type = mimetypes.guess_type(local_path)[0] or _UPLOAD_MIME_DEFAULT

        existing = await self._find_file(parent_id, filename)

        client = await self._get_client()
        token = await self._get_token()

        upload_url = await drive_api.initiate_resumable_upload(
            client,
            token,
            parent_id,
            filename,
            mime_type,
            size_bytes,
            existing_file_id=existing["id"] if existing else None,
            **self._retry_kwargs(),
        )

        start = time.perf_counter()
        raw = await drive_api.upload_content_stream(
            client,
            upload_url,
            self._read_chunks(local_path, self._settings.google_drive_upload_chunk_size_bytes),
            mime_type,
            size_bytes,
            **self._retry_kwargs(),
        )
        duration_s = round(time.perf_counter() - start, 3)
        self._logger.info(
            "storage.upload",
            remote_path=remote_path,
            size_bytes=size_bytes,
            duration_s=duration_s,
            overwrote_existing=existing is not None,
        )
        return self._map_metadata(raw, remote_path)

    async def download(self, remote_path: str, local_path: str) -> None:
        self._require_configured()
        folder_segments, filename = self._split(remote_path)
        parent_id = await self._resolve_path(folder_segments, create_missing=False)
        existing = await self._find_file(parent_id, filename)
        if existing is None:
            raise FileNotFoundError(f"'{remote_path}' não existe no Drive")

        token = await self._get_token()
        client = await self._get_client()

        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        start = time.perf_counter()
        written = 0
        try:
            async with aiofiles.open(local_path, "wb") as f:
                async for chunk in drive_api.download_stream(client, token, existing["id"]):
                    await f.write(chunk)
                    written += len(chunk)
        except Exception:
            # nunca deixar um arquivo local parcial/corrompido se o download falhar no meio
            with contextlib.suppress(OSError):
                os.remove(local_path)
            raise
        duration_s = round(time.perf_counter() - start, 3)
        self._logger.info(
            "storage.download", remote_path=remote_path, size_bytes=written, duration_s=duration_s
        )

    async def exists(self, remote_path: str) -> bool:
        self._require_configured()
        folder_segments, filename = self._split(remote_path)
        try:
            parent_id = await self._resolve_path(folder_segments, create_missing=False)
        except FileNotFoundError:
            return False
        return await self._find_file(parent_id, filename) is not None

    async def delete(self, remote_path: str, *, allow_permanent: bool = False) -> None:
        self._require_configured()

        # Checagem de segurança primeiro, antes de qualquer chamada à API: um caminho fora
        # da área de scratch sem allow_permanent=True nem chega a resolver pasta/arquivo.
        if not allow_permanent and not is_within_scratch(remote_path):
            raise StoragePermanentDeleteBlockedError(
                f"'{remote_path}' está fora de {SCRATCH_PREFIX}/ — delete() aqui exige "
                "allow_permanent=True explícito (proteção contra exclusão de arquivos "
                "permanentes)"
            )

        folder_segments, filename = self._split(remote_path)
        parent_id = await self._resolve_path(folder_segments, create_missing=False)
        existing = await self._find_file(parent_id, filename)
        if existing is None:
            raise FileNotFoundError(f"'{remote_path}' não existe no Drive")

        client = await self._get_client()
        token = await self._get_token()
        if allow_permanent:
            await drive_api.delete_file_permanently(
                client, token, existing["id"], **self._retry_kwargs()
            )
            self._logger.warning("storage.delete_permanent", remote_path=remote_path)
        else:
            await drive_api.trash_file(client, token, existing["id"], **self._retry_kwargs())
            self._logger.info("storage.delete_trashed", remote_path=remote_path)

    async def list(self, prefix: str) -> list[StorageManifestEntry]:
        self._require_configured()
        segments = [p for p in PurePosixPath(prefix.strip("/")).parts]
        try:
            parent_id = await self._resolve_path(segments, create_missing=False)
        except FileNotFoundError:
            return []

        client = await self._get_client()
        token = await self._get_token()
        children = await drive_api.list_children(
            client, token, parent_id, folders_only=False, **self._retry_kwargs()
        )
        files_only = [c for c in children if c.get("mimeType") != drive_api.FOLDER_MIME_TYPE]
        prefix_norm = "/".join(segments)
        return [self._map_metadata(c, f"{prefix_norm}/{c['name']}") for c in files_only]

    async def get_metadata(self, remote_path: str) -> StorageManifestEntry:
        self._require_configured()
        folder_segments, filename = self._split(remote_path)
        parent_id = await self._resolve_path(folder_segments, create_missing=False)
        existing = await self._find_file(parent_id, filename)
        if existing is None:
            raise FileNotFoundError(f"'{remote_path}' não existe no Drive")
        return self._map_metadata(existing, remote_path)

    async def copy(self, src: str, dst: str) -> None:
        self._require_configured()
        src_folder, src_name = self._split(src)
        dst_folder, dst_name = self._split(dst)

        src_parent = await self._resolve_path(src_folder, create_missing=False)
        existing = await self._find_file(src_parent, src_name)
        if existing is None:
            raise FileNotFoundError(f"'{src}' não existe no Drive")

        dst_parent = await self._resolve_path(dst_folder, create_missing=True)
        client = await self._get_client()
        token = await self._get_token()
        await drive_api.copy_file(
            client, token, existing["id"], dst_name, dst_parent, **self._retry_kwargs()
        )
        self._logger.info("storage.copy", src=src, dst=dst)

    async def move(self, src: str, dst: str) -> None:
        self._require_configured()
        src_folder, src_name = self._split(src)
        dst_folder, dst_name = self._split(dst)

        src_parent = await self._resolve_path(src_folder, create_missing=False)
        existing = await self._find_file(src_parent, src_name)
        if existing is None:
            raise FileNotFoundError(f"'{src}' não existe no Drive")

        dst_parent = await self._resolve_path(dst_folder, create_missing=True)
        client = await self._get_client()
        token = await self._get_token()
        await drive_api.move_file(
            client, token, existing["id"], dst_name, src_parent, dst_parent, **self._retry_kwargs()
        )
        self._logger.info("storage.move", src=src, dst=dst)

    async def sync(self, local_dir: str, remote_dir: str) -> SyncReport:
        self._require_configured()
        start = time.perf_counter()
        uploaded: list[str] = []
        skipped: list[str] = []
        failed: list[tuple[str, str]] = []

        local_root = Path(local_dir)
        for local_file in sorted(local_root.rglob("*")):
            if not local_file.is_file():
                continue
            rel = local_file.relative_to(local_root).as_posix()
            remote_path = f"{remote_dir.rstrip('/')}/{rel}"

            try:
                local_md5 = await asyncio.to_thread(self._md5, local_file)
                try:
                    remote_meta = await self.get_metadata(remote_path)
                except FileNotFoundError:
                    remote_meta = None

                if remote_meta is not None and remote_meta.checksum == local_md5:
                    skipped.append(remote_path)
                    continue

                await self.upload(str(local_file), remote_path)
                uploaded.append(remote_path)
            except Exception as exc:  # noqa: BLE001 - um arquivo falho não derruba o sync inteiro
                failed.append((remote_path, f"{type(exc).__name__}: {exc}"))
                self._logger.error(
                    "storage.sync_file_failed", remote_path=remote_path, error=str(exc)
                )

        duration_s = round(time.perf_counter() - start, 3)
        self._logger.info(
            "storage.sync_complete",
            uploaded=len(uploaded),
            skipped=len(skipped),
            failed=len(failed),
            duration_s=duration_s,
        )
        return SyncReport(
            uploaded=uploaded, skipped_unchanged=skipped, failed=failed, duration_s=duration_s
        )

    @staticmethod
    def _md5(path: Path) -> str:
        digest = hashlib.md5()  # noqa: S324 - não é uso criptográfico, é o algoritmo do próprio Drive (md5Checksum)
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
