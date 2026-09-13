"""Testes reais contra o Google Drive — nenhuma resposta da API é mockada.

Só rodam quando uma credencial OAuth User ou Service Account está configurada. Todas as
mutações ficam em ``_integration_tests/<uuid>`` e a limpeza usa lixeira recuperável.
"""

import hashlib
import os
import uuid
from pathlib import Path

import httpx
import pytest
from dhf_schemas.storage import (
    StorageAuthMode,
    StorageConnectionStatus,
    StorageDriveKind,
    StoragePermanentDeleteBlockedError,
)
from dhf_storage import drive_api
from dhf_storage.config import get_google_drive_settings
from dhf_storage.google_drive import GoogleDriveStorageProvider

pytestmark = pytest.mark.integration


class LoseFirstChunkResponseTransport(httpx.AsyncBaseTransport):
    """Entrega o primeiro chunk ao Drive e simula perda da resposta no cliente."""

    def __init__(self) -> None:
        self._inner = httpx.AsyncHTTPTransport()
        self.injected = False

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._inner.handle_async_request(request)
        content_range = request.headers.get("Content-Range", "")
        if not self.injected and content_range.startswith("bytes 0-"):
            self.injected = True
            await response.aread()
            await response.aclose()
            raise httpx.ReadError(
                "falha local injetada após o Drive receber o bloco", request=request
            )
        return response

    async def aclose(self) -> None:
        await self._inner.aclose()


@pytest.fixture
async def real_provider():
    settings = get_google_drive_settings().model_copy(
        update={"google_drive_upload_chunk_size_bytes": 256 * 1024}
    )
    if not settings.has_credential_source:
        pytest.skip(
            "credencial Google Drive OAuth User/Service Account não configurada — "
            "integração real pulada (ver docs/STORAGE_GOOGLE_DRIVE.md)"
        )
    provider = GoogleDriveStorageProvider(settings)
    await provider.bootstrap()
    yield provider
    await provider.aclose()


async def _trash_if_present(provider: GoogleDriveStorageProvider, remote_paths: list[str]) -> None:
    for remote_path in remote_paths:
        try:
            if await provider.exists(remote_path):
                await provider.delete(remote_path)
        except Exception:  # noqa: BLE001 - limpeza não mascara a falha original
            pass


async def _trash_run_folder(provider: GoogleDriveStorageProvider, remote_dir: str) -> None:
    """Remove de forma recuperável somente a pasta UUID criada pelo teste atual."""
    try:
        segments = remote_dir.strip("/").split("/")
        folder_id = await provider._resolve_path(segments, create_missing=False)
        client = await provider._get_client()
        token = await provider._get_token()
        await drive_api.trash_file(client, token, folder_id, **provider._retry_kwargs())
        provider._cache.invalidate(remote_dir)
    except Exception:  # noqa: BLE001 - limpeza não mascara a falha original
        pass


async def test_real_connection_health_and_official_tree(
    real_provider: GoogleDriveStorageProvider,
) -> None:
    status = await real_provider.get_status(force_refresh=True)
    assert status.status == StorageConnectionStatus.CONNECTED, (
        f"esperado CONNECTED, obtido {status.status.value}: {status.detail} (árvore: {status.tree})"
    )
    assert status.auth_mode == StorageAuthMode.OAUTH_USER
    assert status.drive_kind == StorageDriveKind.MY_DRIVE
    assert status.tree is not None
    assert status.tree.missing == []


async def test_real_complete_storage_contract(
    real_provider: GoogleDriveStorageProvider, tmp_path: Path
) -> None:
    run_id = uuid.uuid4().hex
    remote_dir = f"_integration_tests/{run_id}"
    original = f"{remote_dir}/original.bin"
    copied = f"{remote_dir}/copy.bin"
    moved = f"{remote_dir}/moved.bin"
    sync_one = f"{remote_dir}/sync-a.txt"
    sync_two = f"{remote_dir}/sync-b.txt"
    cleanup = [original, copied, moved, sync_one, sync_two]

    content = os.urandom(600 * 1024)
    local_upload = tmp_path / "upload.bin"
    local_upload.write_bytes(content)
    local_download = tmp_path / "download.bin"

    sync_dir = tmp_path / "sync"
    sync_dir.mkdir()
    (sync_dir / "sync-a.txt").write_text("alpha")
    (sync_dir / "sync-b.txt").write_text("beta")

    try:
        entry = await real_provider.upload(str(local_upload), original)
        assert entry.size_bytes == len(content)
        assert entry.checksum == hashlib.md5(content).hexdigest()  # noqa: S324

        assert await real_provider.exists(original) is True
        metadata = await real_provider.get_metadata(original)
        assert metadata.provider_id == entry.provider_id
        assert metadata.checksum == entry.checksum

        names = {item.remote_path for item in await real_provider.list(remote_dir)}
        assert original in names

        await real_provider.download(original, str(local_download))
        assert local_download.read_bytes() == content

        await real_provider.copy(original, copied)
        assert await real_provider.exists(copied)
        await real_provider.move(copied, moved)
        assert not await real_provider.exists(copied)
        assert await real_provider.exists(moved)

        first_sync = await real_provider.sync(str(sync_dir), remote_dir)
        assert set(first_sync.uploaded) == {sync_one, sync_two}
        assert first_sync.failed == []
        second_sync = await real_provider.sync(str(sync_dir), remote_dir)
        assert set(second_sync.skipped_unchanged) == {sync_one, sync_two}
        assert second_sync.failed == []

        (sync_dir / "sync-a.txt").write_text("alpha alterado")
        third_sync = await real_provider.sync(str(sync_dir), remote_dir)
        assert third_sync.uploaded == [sync_one]
        assert third_sync.skipped_unchanged == [sync_two]

        await real_provider.delete(original)
        assert not await real_provider.exists(original)
    finally:
        await _trash_if_present(real_provider, cleanup)
        await _trash_run_folder(real_provider, remote_dir)


async def test_real_resumable_upload_recovers_after_lost_response(
    real_provider: GoogleDriveStorageProvider, tmp_path: Path
) -> None:
    run_id = uuid.uuid4().hex
    remote_path = f"_integration_tests/{run_id}/resume.bin"
    local_path = tmp_path / "resume.bin"
    content = os.urandom(600 * 1024)
    local_path.write_bytes(content)
    transport = LoseFirstChunkResponseTransport()
    await real_provider.aclose()
    real_provider._client = httpx.AsyncClient(
        transport=transport,
        timeout=httpx.Timeout(real_provider._settings.google_drive_request_timeout_s),
    )

    try:
        entry = await real_provider.upload(str(local_path), remote_path)
        assert transport.injected is True
        assert entry.checksum == hashlib.md5(content).hexdigest()  # noqa: S324
        downloaded = tmp_path / "resumed-download.bin"
        await real_provider.download(remote_path, str(downloaded))
        assert downloaded.read_bytes() == content
    finally:
        await _trash_if_present(real_provider, [remote_path])
        await _trash_run_folder(real_provider, f"_integration_tests/{run_id}")


async def test_real_permanent_delete_is_blocked_outside_scratch(
    real_provider: GoogleDriveStorageProvider,
) -> None:
    with pytest.raises(StoragePermanentDeleteBlockedError):
        await real_provider.delete(
            f"03_AVATAR_IDENTITY_FOTOS/dhf-integration-test-guard-{uuid.uuid4().hex}.bin"
        )
