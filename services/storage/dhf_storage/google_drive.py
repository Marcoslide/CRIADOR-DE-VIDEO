"""GoogleDriveStorageProvider — implementação real de StorageProvider sobre a Drive API v3.

Regras de segurança que este módulo respeita à risca:
- nunca loga o conteúdo de uma credencial, nem o access token;
- nunca finge estar `CONNECTED` — get_status() faz uma chamada real (list_children na raiz);
- somente bootstrap cria pastas oficiais ausentes; operações de arquivo nunca as alteram;
- delete() sem allow_permanent=True só age em áreas de scratch conhecidas, e ali move
  para a lixeira (recuperável) — nunca exclusão definitiva sem pedido explícito.
"""

import asyncio
import contextlib
import hashlib
import mimetypes
import os
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import aiofiles
import httpx
from dhf_schemas.storage import (
    StorageAuthExpiredError,
    StorageAuthMode,
    StorageConnectionStatus,
    StorageDriveKind,
    StorageIntegrityError,
    StorageManifestEntry,
    StorageNotConfiguredError,
    StoragePermanentDeleteBlockedError,
    StorageRootNotBootstrappedError,
    StorageStatus,
    SyncReport,
    TreeValidationResult,
)
from dhf_shared.errors import sanitize_error
from dhf_shared.logging import get_logger

from dhf_storage import drive_api
from dhf_storage.auth import CredentialLoadError, ensure_fresh_token, load_credentials
from dhf_storage.cache import FolderIdCache
from dhf_storage.config import GoogleDriveSettings, get_google_drive_settings
from dhf_storage.retry import RetryExhaustedError, with_retry
from dhf_storage.state import RootState, RootStateError, load_root_state, save_root_state
from dhf_storage.tree import (
    INTEGRATION_TESTS_PREFIX,
    OFFICIAL_TOP_LEVEL_FOLDERS,
    SAFE_TRASH_PREFIXES,
    is_within_scratch,
    validate_tree,
)

_UPLOAD_MIME_DEFAULT = "application/octet-stream"
_NOT_CONFIGURED_DETAIL = "credencial Google Drive não configurada (OAuth User ou Service Account)"
_AUTH_EXPIRED_DETAIL = (
    "A autorização do Google Drive expirou ou foi revogada; execute o bootstrap OAuth novamente."
)
ROOT_APP_PROPERTIES = {"dhf_storage_root": "v1"}


def _root_cause(exc: BaseException) -> BaseException:
    """`with_retry` embrulha o último erro em RetryExhaustedError quando esgota as
    tentativas — sanitize_error precisa do erro ORIGINAL (httpx.HTTPStatusError etc.) para
    classificar direito, não do wrapper genérico."""
    return exc.last_error if isinstance(exc, RetryExhaustedError) else exc


class GoogleDriveStorageProvider:
    """Sempre seguro de construir sem credencial — só operações reais falham (nunca
    silenciosamente) quando `get_status()` reportaria NOT_CONFIGURED."""

    def __init__(self, settings: GoogleDriveSettings | None = None) -> None:
        self._settings = settings or get_google_drive_settings()
        self._logger = get_logger(service="storage", provider="google_drive")
        self._cache = FolderIdCache()
        self._client: httpx.AsyncClient | None = None
        self._credentials = None
        self._auth_mode: StorageAuthMode | None = None
        self._auth_expired = False
        self._credential_load_error: CredentialLoadError | None = None
        self._root_folder_id: str | None = None
        self._root_state_loaded = False
        self._root_state_error: RootStateError | None = None
        self._status_cache: StorageStatus | None = None
        self._status_lock = asyncio.Lock()
        self._bootstrap_lock = asyncio.Lock()
        # A Drive API não oferece "create folder if absent" atômico. Serializar a
        # resolução criadora evita pastas duplicadas entre uploads concorrentes deste
        # processo; coordenação entre múltiplos processos fica para a camada de jobs.
        self._path_create_lock = asyncio.Lock()

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
            loaded = load_credentials(self._settings)
            if loaded is not None:
                self._credentials = loaded.credentials
                self._auth_mode = StorageAuthMode(loaded.mode.value)
        except CredentialLoadError as exc:
            self._credential_load_error = exc
            self._logger.error("storage.credential_load_error", error=str(exc))

    async def _get_token(self) -> str:
        if self._auth_expired:
            raise StorageAuthExpiredError(_AUTH_EXPIRED_DETAIL)
        self._load_credentials_once()
        if self._credential_load_error is not None:
            raise self._credential_load_error
        if self._credentials is None:
            raise StorageNotConfiguredError(_NOT_CONFIGURED_DETAIL)
        try:
            return await asyncio.to_thread(ensure_fresh_token, self._credentials)
        except StorageAuthExpiredError:
            self._auth_expired = True
            raise

    def _require_configured(self) -> None:
        self._load_credentials_once()
        if self._credential_load_error is not None:
            raise self._credential_load_error
        if self._credentials is None:
            raise StorageNotConfiguredError(_NOT_CONFIGURED_DETAIL)

    def _retry_kwargs(self) -> dict:
        return {
            "max_retries": self._settings.google_drive_max_retries,
            "base_delay_s": self._settings.google_drive_retry_base_delay_s,
            "logger": self._logger,
        }

    def _load_root_state_once(self) -> None:
        if self._root_state_loaded:
            return
        self._root_state_loaded = True
        if self._settings.google_drive_root_folder_id.strip():
            self._root_folder_id = self._settings.google_drive_root_folder_id.strip()
            return
        try:
            state = load_root_state(self._settings.root_state_path)
        except RootStateError as exc:
            self._root_state_error = exc
            return
        if state is not None:
            if state.root_folder_name != self._settings.google_drive_root_folder_name:
                self._root_state_error = RootStateError(
                    "nome da root no state file diverge da configuração"
                )
                return
            self._root_folder_id = state.root_folder_id

    def _require_root_id(self) -> str:
        self._load_root_state_once()
        if self._root_state_error is not None:
            raise self._root_state_error
        if self._root_folder_id is None:
            raise StorageRootNotBootstrappedError(
                "root gerenciada ainda não foi criada; execute dhf-storage bootstrap"
            )
        return self._root_folder_id

    @staticmethod
    def _is_not_found(exc: BaseException) -> bool:
        root = _root_cause(exc)
        return isinstance(root, httpx.HTTPStatusError) and root.response.status_code == 404

    def _validate_managed_root(self, metadata: dict) -> None:
        if metadata.get("mimeType") != drive_api.FOLDER_MIME_TYPE:
            raise RootStateError("o ID persistido da root não aponta para uma pasta")
        if metadata.get("name") != self._settings.google_drive_root_folder_name:
            raise RootStateError("o ID persistido aponta para uma pasta com nome inesperado")
        properties = metadata.get("appProperties") or {}
        if any(properties.get(key) != value for key, value in ROOT_APP_PROPERTIES.items()):
            raise RootStateError("a pasta persistida não possui a marca da root gerenciada")

    async def bootstrap(self) -> StorageStatus:
        """Cria/recupera a root marcada e garante a árvore oficial de forma idempotente."""
        self._require_configured()
        async with self._bootstrap_lock:
            client = await self._get_client()
            token = await self._get_token()
            self._load_root_state_once()
            if self._root_state_error is not None:
                raise self._root_state_error

            root_id = self._root_folder_id
            if root_id is not None:
                try:
                    metadata = await drive_api.get_file_metadata(
                        client, token, root_id, **self._retry_kwargs()
                    )
                    self._validate_managed_root(metadata)
                except Exception as exc:
                    is_persisted_state = not bool(
                        self._settings.google_drive_root_folder_id.strip()
                    )
                    if not is_persisted_state or not self._is_not_found(exc):
                        raise
                    root_id = None
                    self._root_folder_id = None

            if root_id is None:
                state_path = self._settings.root_state_path
                if state_path is None:
                    raise RootStateError(
                        "configure GOOGLE_DRIVE_ROOT_STATE_FILE ou OAUTH_USER_FILE "
                        "antes do bootstrap"
                    )
                matches = await drive_api.list_children(
                    client,
                    token,
                    "root",
                    name=self._settings.google_drive_root_folder_name,
                    folders_only=True,
                    app_properties=ROOT_APP_PROPERTIES,
                    **self._retry_kwargs(),
                )
                if len(matches) > 1:
                    raise RootStateError(
                        "mais de uma root marcada foi encontrada; intervenção manual necessária"
                    )
                if matches:
                    root_id = matches[0]["id"]
                    self._validate_managed_root(matches[0])
                else:
                    visible_name_matches = await drive_api.list_children(
                        client,
                        token,
                        "root",
                        name=self._settings.google_drive_root_folder_name,
                        folders_only=True,
                        **self._retry_kwargs(),
                    )
                    if visible_name_matches:
                        raise RootStateError(
                            "já existe uma pasta visível com o nome da root, mas sem a "
                            "marca gerenciada; nenhuma nova root foi criada"
                        )
                    created = await drive_api.create_folder(
                        client,
                        token,
                        "root",
                        self._settings.google_drive_root_folder_name,
                        app_properties=ROOT_APP_PROPERTIES,
                        **self._retry_kwargs(),
                    )
                    root_id = created["id"]
                self._root_folder_id = root_id
                save_root_state(
                    state_path,
                    RootState(
                        root_folder_id=root_id,
                        root_folder_name=self._settings.google_drive_root_folder_name,
                    ),
                )

            folders = await drive_api.list_children(
                client,
                token,
                root_id,
                folders_only=True,
                **self._retry_kwargs(),
            )
            by_name: dict[str, list[dict]] = {}
            for folder in folders:
                by_name.setdefault(folder["name"], []).append(folder)
            duplicates = [
                name for name in OFFICIAL_TOP_LEVEL_FOLDERS if len(by_name.get(name, [])) > 1
            ]
            if duplicates:
                raise RootStateError(
                    "pastas oficiais duplicadas na root gerenciada: " + ", ".join(duplicates)
                )
            for name in OFFICIAL_TOP_LEVEL_FOLDERS:
                if name not in by_name:
                    await drive_api.create_folder(
                        client, token, root_id, name, **self._retry_kwargs()
                    )

            self._cache.invalidate()
            self._status_cache = None
            return await self.get_status(force_refresh=True)

    @staticmethod
    def _split(remote_path: str) -> tuple[list[str], str]:
        normalized = remote_path.strip("/")
        if not normalized:
            raise ValueError("remote_path vazio")
        raw_parts = normalized.split("/")
        if any(part in {"", ".", ".."} or "\x00" in part for part in raw_parts):
            raise ValueError("remote_path contém segmento inválido")
        parts = list(PurePosixPath(normalized).parts)
        allowed_top_level = {*OFFICIAL_TOP_LEVEL_FOLDERS, INTEGRATION_TESTS_PREFIX}
        if len(parts) < 2 or parts[0] not in allowed_top_level:
            raise ValueError(
                "remote_path deve apontar abaixo de uma pasta oficial ou da área interna de testes"
            )
        return parts[:-1], parts[-1]

    async def _resolve_path(self, segments: list[str], *, create_missing: bool) -> str:
        if create_missing:
            async with self._path_create_lock:
                return await self._resolve_path_unlocked(segments, create_missing=True)
        return await self._resolve_path_unlocked(segments, create_missing=False)

    async def _resolve_path_unlocked(self, segments: list[str], *, create_missing: bool) -> str:
        if not segments:
            return self._require_root_id()

        top = segments[0]
        if top not in {*OFFICIAL_TOP_LEVEL_FOLDERS, INTEGRATION_TESTS_PREFIX}:
            raise ValueError(
                f"'{top}' não é uma pasta gerenciada da árvore do Drive. "
                f"Válidas: {OFFICIAL_TOP_LEVEL_FOLDERS} e {INTEGRATION_TESTS_PREFIX}"
            )

        client = await self._get_client()
        token = await self._get_token()

        root_id = self._require_root_id()
        parent_id = self._cache.get(top)
        if parent_id is None:
            matches = await drive_api.list_children(
                client,
                token,
                root_id,
                name=top,
                folders_only=True,
                shared_drive_id=self._settings.google_drive_shared_drive_id or None,
                **self._retry_kwargs(),
            )
            if not matches:
                if top == INTEGRATION_TESTS_PREFIX and create_missing:
                    created = await drive_api.create_folder(
                        client, token, root_id, top, **self._retry_kwargs()
                    )
                    parent_id = created["id"]
                    self._logger.info("storage.folder_created", path=top)
                else:
                    qualifier = "interna" if top == INTEGRATION_TESTS_PREFIX else "oficial"
                    raise FileNotFoundError(
                        f"pasta {qualifier} '{top}' não encontrada na raiz do Drive "
                        f"({root_id}) — execute dhf-storage bootstrap para reparar a árvore"
                    )
            else:
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
                    shared_drive_id=self._settings.google_drive_shared_drive_id or None,
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
            client,
            token,
            parent_id,
            name=filename,
            folders_only=False,
            shared_drive_id=self._settings.google_drive_shared_drive_id or None,
            **self._retry_kwargs(),
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
    async def _read_chunk(local_path: str, offset: int, length: int) -> bytes:
        async with aiofiles.open(local_path, "rb") as f:
            await f.seek(offset)
            return await f.read(length)

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
                    auth_mode=self._auth_mode,
                    checked_at=now,
                )
                self._status_cache = status
                return status

            if self._credentials is None:
                status = StorageStatus(
                    status=StorageConnectionStatus.NOT_CONFIGURED,
                    detail=_NOT_CONFIGURED_DETAIL,
                    auth_mode=self._auth_mode,
                    checked_at=now,
                )
                self._status_cache = status
                return status

            root_id: str | None = None
            try:
                client = await self._get_client()
                token = await self._get_token()
                root_id = self._require_root_id()
                root_metadata = await drive_api.get_file_metadata(
                    client, token, root_id, **self._retry_kwargs()
                )
                self._validate_managed_root(root_metadata)
                actual_shared_drive_id = root_metadata.get("driveId")
                configured_shared_drive_id = self._settings.google_drive_shared_drive_id or None
                if configured_shared_drive_id != actual_shared_drive_id:
                    raise ValueError(
                        "GOOGLE_DRIVE_SHARED_DRIVE_ID não corresponde ao Drive da pasta raiz"
                    )
                children = await drive_api.list_children(
                    client,
                    token,
                    root_id,
                    folders_only=True,
                    shared_drive_id=configured_shared_drive_id,
                    **self._retry_kwargs(),
                )
                quota = await drive_api.get_storage_quota(client, token, **self._retry_kwargs())
            except StorageAuthExpiredError:
                status = StorageStatus(
                    status=StorageConnectionStatus.AUTH_EXPIRED,
                    detail=_AUTH_EXPIRED_DETAIL,
                    error_code="AUTH_EXPIRED",
                    root_folder_id=root_id,
                    auth_mode=self._auth_mode,
                    checked_at=now,
                )
                self._status_cache = status
                return status
            except StorageRootNotBootstrappedError as exc:
                status = StorageStatus(
                    status=StorageConnectionStatus.NOT_CONFIGURED,
                    detail=str(exc),
                    error_code="ROOT_NOT_BOOTSTRAPPED",
                    auth_mode=self._auth_mode,
                    checked_at=now,
                )
                self._status_cache = status
                return status
            except RootStateError as exc:
                status = StorageStatus(
                    status=StorageConnectionStatus.ERROR,
                    detail=str(exc),
                    error_code="ROOT_STATE_ERROR",
                    root_folder_id=root_id,
                    auth_mode=self._auth_mode,
                    checked_at=now,
                )
                self._status_cache = status
                return status
            except Exception as exc:  # noqa: BLE001 - logado completo, exposto só sanitizado
                self._logger.error("storage.status_check_failed", error_type=type(exc).__name__)
                sanitized = sanitize_error(_root_cause(exc))
                status = StorageStatus(
                    status=StorageConnectionStatus.ERROR,
                    detail=sanitized.message,
                    error_code=sanitized.code,
                    root_folder_id=root_id,
                    auth_mode=self._auth_mode,
                    checked_at=now,
                )
                self._status_cache = status
                return status

            tree: TreeValidationResult = validate_tree([c["name"] for c in children])
            quota_limit = quota["limit"]
            quota_usage = quota["usage"]
            quota_exhausted = (
                quota_limit is not None and quota_usage is not None and quota_usage >= quota_limit
            )
            degraded = not tree.valid or quota_exhausted
            if quota_exhausted:
                detail = (
                    "cota de armazenamento Google esgotada; libere espaço antes de "
                    "enviar novos arquivos"
                )
                error_code = "STORAGE_QUOTA_EXCEEDED"
            elif not tree.valid:
                detail = f"faltam {len(tree.missing)} pasta(s) oficiais"
                error_code = "STORAGE_TREE_INCOMPLETE"
            else:
                detail = None
                error_code = None
            status = StorageStatus(
                status=(
                    StorageConnectionStatus.DEGRADED
                    if degraded
                    else StorageConnectionStatus.CONNECTED
                ),
                detail=detail,
                error_code=error_code,
                root_folder_id=root_id,
                auth_mode=self._auth_mode,
                drive_kind=(
                    StorageDriveKind.SHARED_DRIVE
                    if root_metadata.get("driveId")
                    else StorageDriveKind.MY_DRIVE
                ),
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
        local_checksum = await asyncio.to_thread(self._md5, Path(local_path))

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

        chunk_size = self._settings.google_drive_upload_chunk_size_bytes
        start = time.perf_counter()
        raw = await drive_api.upload_content_resumable(
            client,
            token,
            upload_url,
            lambda offset, length: self._read_chunk(local_path, offset, length),
            mime_type,
            size_bytes,
            chunk_size,
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
        entry = self._map_metadata(raw, remote_path)
        if entry.checksum != local_checksum:
            self._logger.error(
                "storage.upload_checksum_mismatch",
                remote_path=remote_path,
                size_bytes=size_bytes,
            )
            raise StorageIntegrityError("checksum do upload diverge do arquivo local")
        return entry

    async def download(self, remote_path: str, local_path: str) -> None:
        self._require_configured()
        folder_segments, filename = self._split(remote_path)
        parent_id = await self._resolve_path(folder_segments, create_missing=False)
        existing = await self._find_file(parent_id, filename)
        if existing is None:
            raise FileNotFoundError(f"'{remote_path}' não existe no Drive")

        token = await self._get_token()
        client = await self._get_client()

        destination = Path(local_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".part", dir=destination.parent
        )
        os.close(fd)
        temporary_path = Path(temporary_name)
        start = time.perf_counter()
        written = 0
        try:

            async def _download_once() -> int:
                attempt_written = 0
                async with aiofiles.open(temporary_path, "wb") as f:
                    async for chunk in drive_api.download_stream(client, token, existing["id"]):
                        await f.write(chunk)
                        attempt_written += len(chunk)
                return attempt_written

            written = await with_retry(_download_once, **self._retry_kwargs())
            expected_checksum = existing.get("md5Checksum")
            actual_checksum = await asyncio.to_thread(self._md5, temporary_path)
            if expected_checksum is None or actual_checksum != expected_checksum:
                raise StorageIntegrityError("checksum do download diverge do metadata do Drive")
            # Troca atômica: um destino pré-existente só é substituído depois que o
            # download termina. Falhas preservam a última cópia íntegra.
            os.replace(temporary_path, destination)
        except BaseException:
            with contextlib.suppress(OSError):
                temporary_path.unlink()
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
            safe_areas = ", ".join(f"{prefix}/" for prefix in SAFE_TRASH_PREFIXES)
            raise StoragePermanentDeleteBlockedError(
                f"'{remote_path}' está fora das áreas seguras ({safe_areas}) — "
                "delete() aqui exige "
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
        normalized = prefix.strip("/")
        raw_segments = normalized.split("/") if normalized else []
        if any(segment in {"", ".", ".."} or "\x00" in segment for segment in raw_segments):
            raise ValueError("prefix contém segmento inválido")
        segments = list(PurePosixPath(normalized).parts) if normalized else []
        try:
            parent_id = await self._resolve_path(segments, create_missing=False)
        except FileNotFoundError:
            return []

        client = await self._get_client()
        token = await self._get_token()
        children = await drive_api.list_children(
            client,
            token,
            parent_id,
            folders_only=False,
            shared_drive_id=self._settings.google_drive_shared_drive_id or None,
            **self._retry_kwargs(),
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
        if src.strip("/") == dst.strip("/"):
            raise ValueError("origem e destino de copy não podem ser iguais")
        src_folder, src_name = self._split(src)
        dst_folder, dst_name = self._split(dst)

        src_parent = await self._resolve_path(src_folder, create_missing=False)
        existing = await self._find_file(src_parent, src_name)
        if existing is None:
            raise FileNotFoundError(f"'{src}' não existe no Drive")

        dst_parent = await self._resolve_path(dst_folder, create_missing=True)
        if await self._find_file(dst_parent, dst_name) is not None:
            raise FileExistsError(f"destino '{dst}' já existe no Drive")
        client = await self._get_client()
        token = await self._get_token()
        await drive_api.copy_file(
            client, token, existing["id"], dst_name, dst_parent, **self._retry_kwargs()
        )
        self._logger.info("storage.copy", src=src, dst=dst)

    async def move(self, src: str, dst: str) -> None:
        self._require_configured()
        if src.strip("/") == dst.strip("/"):
            raise ValueError("origem e destino de move não podem ser iguais")
        src_folder, src_name = self._split(src)
        dst_folder, dst_name = self._split(dst)

        src_parent = await self._resolve_path(src_folder, create_missing=False)
        existing = await self._find_file(src_parent, src_name)
        if existing is None:
            raise FileNotFoundError(f"'{src}' não existe no Drive")

        dst_parent = await self._resolve_path(dst_folder, create_missing=True)
        destination = await self._find_file(dst_parent, dst_name)
        if destination is not None and destination["id"] != existing["id"]:
            raise FileExistsError(f"destino '{dst}' já existe no Drive")
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
        if not local_root.exists():
            raise FileNotFoundError(f"diretório local '{local_dir}' não existe")
        if not local_root.is_dir():
            raise NotADirectoryError(f"caminho local '{local_dir}' não é um diretório")
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
                sanitized = sanitize_error(_root_cause(exc))
                failed.append((remote_path, f"{sanitized.code}: {sanitized.message}"))
                self._logger.error(
                    "storage.sync_file_failed",
                    remote_path=remote_path,
                    error_code=sanitized.code,
                    error_type=type(exc).__name__,
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
