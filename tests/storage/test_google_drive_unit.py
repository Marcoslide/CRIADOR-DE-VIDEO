"""Testes unitários do GoogleDriveStorageProvider — toda chamada de rede é mockada via
respx (intercepta o httpx de verdade, não é um stub à parte). Nenhum destes testes prova a
integração real com o Google Drive — isso é `test_google_drive_integration.py`.
"""

import asyncio
import hashlib
import json

import httpx
import pytest
import respx
from dhf_schemas.storage import (
    StorageAuthMode,
    StorageConnectionStatus,
    StorageDriveKind,
    StorageIntegrityError,
    StorageNotConfiguredError,
    StoragePermanentDeleteBlockedError,
)
from dhf_storage.drive_api import FILES_URL, UPLOAD_URL
from dhf_storage.google_drive import ROOT_APP_PROPERTIES
from dhf_storage.retry import RetryExhaustedError
from dhf_storage.tree import OFFICIAL_TOP_LEVEL_FOLDERS


def _folder(folder_id: str, name: str) -> dict:
    return {
        "id": folder_id,
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "modifiedTime": "2026-09-10T12:00:00.000Z",
    }


def _file(
    file_id: str,
    name: str,
    *,
    size: int = 1024,
    checksum: str = "d41d8cd98f00b204e9800998ecf8427e",
) -> dict:
    return {
        "id": file_id,
        "name": name,
        "mimeType": "image/png",
        "size": str(size),
        "md5Checksum": checksum,
        "modifiedTime": "2026-09-10T12:00:00.000Z",
        "webViewLink": f"https://drive.google.com/file/d/{file_id}/view",
    }


def _root(*, drive_id: str | None = None) -> dict:
    result = _folder("root-folder-id", "CRIADOR DE VIDEO — STORAGE")
    result["appProperties"] = ROOT_APP_PROPERTIES
    if drive_id is not None:
        result["driveId"] = drive_id
    return result


# ------------------------------------------------------------------ get_status


async def test_get_status_not_configured_without_credentials(unconfigured_provider) -> None:
    status = await unconfigured_provider.get_status(force_refresh=True)
    assert status.status == StorageConnectionStatus.NOT_CONFIGURED
    assert status.tree is None


async def test_get_status_reports_auth_expired_specifically(unit_settings, monkeypatch) -> None:
    from dhf_schemas.storage import StorageAuthExpiredError
    from dhf_storage.google_drive import GoogleDriveStorageProvider

    expired_provider = GoogleDriveStorageProvider(unit_settings)
    expired_provider._credentials = object()
    expired_provider._auth_mode = StorageAuthMode.OAUTH_USER

    refresh_attempts = 0

    def expired_token(credentials):
        nonlocal refresh_attempts
        refresh_attempts += 1
        raise StorageAuthExpiredError("expirada")

    monkeypatch.setattr("dhf_storage.google_drive.ensure_fresh_token", expired_token)

    status = await expired_provider.get_status(force_refresh=True)

    assert status.status == StorageConnectionStatus.AUTH_EXPIRED
    assert status.error_code == "AUTH_EXPIRED"
    assert "expirou" in status.detail
    second = await expired_provider.get_status(force_refresh=True)
    assert second.status == StorageConnectionStatus.AUTH_EXPIRED
    assert refresh_attempts == 1
    await expired_provider.aclose()


async def test_get_status_requires_root_bootstrap(unit_settings, monkeypatch) -> None:
    from dhf_storage.google_drive import GoogleDriveStorageProvider

    settings = unit_settings.model_copy(
        update={
            "google_drive_root_folder_id": "",
            "google_drive_root_state_file": "",
        }
    )
    rootless_provider = GoogleDriveStorageProvider(settings)

    async def fake_token():
        return "token"

    monkeypatch.setattr(rootless_provider, "_get_token", fake_token)
    status = await rootless_provider.get_status(force_refresh=True)

    assert status.status == StorageConnectionStatus.NOT_CONFIGURED
    assert status.error_code == "ROOT_NOT_BOOTSTRAPPED"
    await rootless_provider.aclose()


@respx.mock
async def test_get_status_connected_when_all_folders_present(provider) -> None:
    respx.get(f"{FILES_URL}/root-folder-id").mock(return_value=httpx.Response(200, json=_root()))
    respx.get(FILES_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "files": [
                    _folder(f"id-{i}", name) for i, name in enumerate(OFFICIAL_TOP_LEVEL_FOLDERS)
                ]
            },
        )
    )
    status = await provider.get_status(force_refresh=True)
    assert status.status == StorageConnectionStatus.CONNECTED
    assert status.tree.valid is True
    assert status.auth_mode == StorageAuthMode.OAUTH_USER
    assert status.drive_kind == StorageDriveKind.MY_DRIVE


@respx.mock
async def test_get_status_degraded_when_folder_missing(provider) -> None:
    incomplete = OFFICIAL_TOP_LEVEL_FOLDERS[:-1]
    respx.get(f"{FILES_URL}/root-folder-id").mock(return_value=httpx.Response(200, json=_root()))
    respx.get(FILES_URL).mock(
        return_value=httpx.Response(
            200, json={"files": [_folder(f"id-{i}", n) for i, n in enumerate(incomplete)]}
        )
    )
    status = await provider.get_status(force_refresh=True)
    assert status.status == StorageConnectionStatus.DEGRADED
    assert status.error_code == "STORAGE_TREE_INCOMPLETE"
    assert status.tree.missing == [OFFICIAL_TOP_LEVEL_FOLDERS[-1]]


@respx.mock
async def test_get_status_degraded_when_storage_quota_is_exhausted(provider, monkeypatch) -> None:
    async def exhausted_quota(*args, **kwargs):
        return {
            "limit": 15 * 1024**3,
            "usage": 15 * 1024**3,
            "usage_in_drive": 14 * 1024**3,
            "usage_in_drive_trash": 1024**3,
        }

    monkeypatch.setattr("dhf_storage.google_drive.drive_api.get_storage_quota", exhausted_quota)
    respx.get(f"{FILES_URL}/root-folder-id").mock(return_value=httpx.Response(200, json=_root()))
    respx.get(FILES_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "files": [
                    _folder(f"id-{i}", name) for i, name in enumerate(OFFICIAL_TOP_LEVEL_FOLDERS)
                ]
            },
        )
    )

    status = await provider.get_status(force_refresh=True)

    assert status.status == StorageConnectionStatus.DEGRADED
    assert status.error_code == "STORAGE_QUOTA_EXCEEDED"
    assert status.tree.valid is True
    assert "libere espaço" in status.detail


@respx.mock
async def test_get_status_connected_on_matching_shared_drive(provider, monkeypatch) -> None:
    monkeypatch.setattr(provider._settings, "google_drive_shared_drive_id", "shared-drive-id")
    respx.get(f"{FILES_URL}/root-folder-id").mock(
        return_value=httpx.Response(200, json=_root(drive_id="shared-drive-id"))
    )
    list_route = respx.get(FILES_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "files": [
                    _folder(f"id-{i}", name) for i, name in enumerate(OFFICIAL_TOP_LEVEL_FOLDERS)
                ]
            },
        )
    )

    status = await provider.get_status(force_refresh=True)

    assert status.status == StorageConnectionStatus.CONNECTED
    assert status.drive_kind == StorageDriveKind.SHARED_DRIVE
    assert list_route.calls.last.request.url.params["corpora"] == "drive"
    assert list_route.calls.last.request.url.params["driveId"] == "shared-drive-id"


@respx.mock
async def test_get_status_error_when_api_fails(provider) -> None:
    """Também prova a sanitização: mesmo depois de with_retry embrulhar o erro em
    RetryExhaustedError, o detail exposto é a mensagem genérica — nunca a URL real da
    Drive API nem o corpo/erro cru da resposta."""
    respx.get(f"{FILES_URL}/root-folder-id").mock(
        return_value=httpx.Response(500, json={"error": "boom"})
    )
    status = await provider.get_status(force_refresh=True)
    assert status.status == StorageConnectionStatus.ERROR
    assert status.error_code == "upstream_error"
    assert status.detail == "O serviço externo respondeu com erro."
    assert FILES_URL not in status.detail
    assert "boom" not in status.detail


async def test_get_status_connecting_when_refresh_already_in_progress(provider) -> None:
    async with provider._status_lock:
        status = await provider.get_status(force_refresh=True)
    assert status.status == StorageConnectionStatus.CONNECTING


async def test_get_status_uses_cache_within_ttl(provider, monkeypatch) -> None:
    from datetime import UTC, datetime

    from dhf_schemas.storage import StorageStatus

    monkeypatch.setattr(provider._settings, "google_drive_status_cache_ttl_s", 3600)
    cached = StorageStatus(status=StorageConnectionStatus.CONNECTED, checked_at=datetime.now(UTC))
    provider._status_cache = cached

    # nenhuma rota respx registrada — se o provider tentasse uma chamada real, isto falharia
    status = await provider.get_status(force_refresh=False)
    assert status is cached


# ------------------------------------------------------------------ operações sem credencial


async def test_upload_without_credentials_raises(unconfigured_provider, tmp_path) -> None:
    local_file = tmp_path / "x.png"
    local_file.write_bytes(b"data")
    with pytest.raises(StorageNotConfiguredError):
        await unconfigured_provider.upload(str(local_file), "03_AVATAR_IDENTITY_FOTOS/x.png")


# ------------------------------------------------------------------ resolução de caminho


async def test_resolve_path_rejects_unofficial_top_level(provider) -> None:
    with pytest.raises(ValueError, match="não é uma pasta gerenciada"):
        await provider._resolve_path(["PASTA_INVENTADA"], create_missing=False)


@respx.mock
async def test_resolve_path_top_level_not_found_raises(provider) -> None:
    respx.get(FILES_URL).mock(return_value=httpx.Response(200, json={"files": []}))
    with pytest.raises(FileNotFoundError):
        await provider._resolve_path(["03_AVATAR_IDENTITY_FOTOS"], create_missing=False)


@respx.mock
async def test_resolve_path_creates_missing_nested_folder(provider) -> None:
    respx.get(FILES_URL).mock(
        side_effect=[
            httpx.Response(200, json={"files": [_folder("top-id", "03_AVATAR_IDENTITY_FOTOS")]}),
            httpx.Response(200, json={"files": []}),  # "lia" não existe ainda
        ]
    )
    respx.post(FILES_URL).mock(return_value=httpx.Response(200, json=_folder("lia-id", "lia")))

    resolved = await provider._resolve_path(
        ["03_AVATAR_IDENTITY_FOTOS", "lia"], create_missing=True
    )

    assert resolved == "lia-id"
    assert provider._cache.get("03_AVATAR_IDENTITY_FOTOS") == "top-id"
    assert provider._cache.get("03_AVATAR_IDENTITY_FOTOS/lia") == "lia-id"


@respx.mock
async def test_resolve_path_missing_nested_without_create_raises(provider) -> None:
    respx.get(FILES_URL).mock(
        side_effect=[
            httpx.Response(200, json={"files": [_folder("top-id", "03_AVATAR_IDENTITY_FOTOS")]}),
            httpx.Response(200, json={"files": []}),
        ]
    )
    with pytest.raises(FileNotFoundError):
        await provider._resolve_path(["03_AVATAR_IDENTITY_FOTOS", "lia"], create_missing=False)


async def test_create_path_resolution_is_serialized_within_process(provider, monkeypatch) -> None:
    active = 0
    peak = 0

    async def fake_unlocked(segments, *, create_missing):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        active -= 1
        return "folder-id"

    monkeypatch.setattr(provider, "_resolve_path_unlocked", fake_unlocked)
    await asyncio.gather(
        provider._resolve_path(["03_AVATAR_IDENTITY_FOTOS", "a"], create_missing=True),
        provider._resolve_path(["03_AVATAR_IDENTITY_FOTOS", "b"], create_missing=True),
    )
    assert peak == 1


# ------------------------------------------------------------------ upload


@respx.mock
async def test_upload_creates_new_file(provider, tmp_path, monkeypatch) -> None:
    async def fake_resolve(segments, *, create_missing):
        return "parent-id"

    async def fake_find(parent_id, filename):
        return None  # não existe ainda -> cria (POST), não atualiza (PATCH)

    monkeypatch.setattr(provider, "_resolve_path", fake_resolve)
    monkeypatch.setattr(provider, "_find_file", fake_find)

    local_file = tmp_path / "000.png"
    local_file.write_bytes(b"\x89PNG fake content")
    checksum = hashlib.md5(local_file.read_bytes()).hexdigest()  # noqa: S324

    init_route = respx.post(UPLOAD_URL, params={"uploadType": "resumable"}).mock(
        return_value=httpx.Response(200, headers={"Location": "https://upload.example/session-1"})
    )
    put_route = respx.put("https://upload.example/session-1").mock(
        return_value=httpx.Response(
            200,
            json=_file(
                "new-file-id",
                "000.png",
                size=local_file.stat().st_size,
                checksum=checksum,
            ),
        )
    )

    entry = await provider.upload(
        str(local_file), "03_AVATAR_IDENTITY_FOTOS/lia/v1/head360/000.png"
    )

    assert init_route.called
    assert put_route.called
    assert entry.provider_id == "new-file-id"
    assert entry.size_bytes == local_file.stat().st_size
    assert entry.checksum == checksum


@respx.mock
async def test_resumable_upload_recovers_confirmed_offset_after_transport_loss(
    provider, tmp_path, monkeypatch
) -> None:
    """O Drive confirma o primeiro bloco; o segundo chega ao servidor, mas a resposta
    se perde. A consulta de status informa o novo offset e o cliente envia só o restante."""

    async def fake_resolve(segments, *, create_missing):
        return "parent-id"

    async def fake_find(parent_id, filename):
        return None

    monkeypatch.setattr(provider, "_resolve_path", fake_resolve)
    monkeypatch.setattr(provider, "_find_file", fake_find)
    chunk_size = 256 * 1024
    monkeypatch.setattr(provider._settings, "google_drive_upload_chunk_size_bytes", chunk_size)

    content = bytes(range(256)) * 2400  # 600 KiB -> três blocos
    local_file = tmp_path / "large.bin"
    local_file.write_bytes(content)
    checksum = hashlib.md5(content).hexdigest()  # noqa: S324

    respx.post(UPLOAD_URL, params={"uploadType": "resumable"}).mock(
        return_value=httpx.Response(
            200, headers={"Location": "https://upload.example/session-retry"}
        )
    )
    put_route = respx.put("https://upload.example/session-retry").mock(
        side_effect=[
            httpx.Response(308, headers={"Range": f"bytes=0-{chunk_size - 1}"}),
            httpx.ReadError("resposta perdida"),
            httpx.Response(308, headers={"Range": f"bytes=0-{2 * chunk_size - 1}"}),
            httpx.Response(
                200,
                json=_file(
                    "retried-file-id",
                    "large.bin",
                    size=len(content),
                    checksum=checksum,
                ),
            ),
        ]
    )

    entry = await provider.upload(str(local_file), "03_AVATAR_IDENTITY_FOTOS/large.bin")

    assert put_route.call_count == 4
    assert put_route.calls[0].request.headers["Content-Range"] == (
        f"bytes 0-{chunk_size - 1}/{len(content)}"
    )
    assert put_route.calls[1].request.headers["Content-Range"] == (
        f"bytes {chunk_size}-{len(content) - 1}/{len(content)}"
    )
    assert put_route.calls[2].request.headers["Content-Range"] == f"bytes */{len(content)}"
    assert put_route.calls[2].request.content == b""
    assert put_route.calls[3].request.headers["Content-Range"] == (
        f"bytes {2 * chunk_size}-{len(content) - 1}/{len(content)}"
    )
    assert put_route.calls[3].request.content == content[2 * chunk_size :]
    assert all(
        call.request.headers["Authorization"] == "Bearer fake-access-token"
        for call in put_route.calls
    )
    assert entry.provider_id == "retried-file-id"


@respx.mock
async def test_upload_overwrites_existing_file_via_patch(provider, tmp_path, monkeypatch) -> None:
    async def fake_resolve(segments, *, create_missing):
        return "parent-id"

    async def fake_find(parent_id, filename):
        return _file("existing-id", filename)

    monkeypatch.setattr(provider, "_resolve_path", fake_resolve)
    monkeypatch.setattr(provider, "_find_file", fake_find)

    local_file = tmp_path / "000.png"
    local_file.write_bytes(b"conteudo novo")
    checksum = hashlib.md5(local_file.read_bytes()).hexdigest()  # noqa: S324

    init_route = respx.patch(f"{UPLOAD_URL}/existing-id", params={"uploadType": "resumable"}).mock(
        return_value=httpx.Response(200, headers={"Location": "https://upload.example/session-2"})
    )
    respx.put("https://upload.example/session-2").mock(
        return_value=httpx.Response(
            200,
            json=_file("existing-id", "000.png", size=local_file.stat().st_size, checksum=checksum),
        )
    )

    entry = await provider.upload(str(local_file), "03_AVATAR_IDENTITY_FOTOS/000.png")

    assert init_route.called
    assert entry.provider_id == "existing-id"


@respx.mock
async def test_upload_rejects_checksum_mismatch(provider, tmp_path, monkeypatch) -> None:
    async def fake_resolve(segments, *, create_missing):
        return "parent-id"

    async def fake_find(parent_id, filename):
        return None

    monkeypatch.setattr(provider, "_resolve_path", fake_resolve)
    monkeypatch.setattr(provider, "_find_file", fake_find)
    local_file = tmp_path / "corrupt.bin"
    local_file.write_bytes(b"local")
    respx.post(UPLOAD_URL, params={"uploadType": "resumable"}).mock(
        return_value=httpx.Response(200, headers={"Location": "https://upload.example/bad"})
    )
    respx.put("https://upload.example/bad").mock(
        return_value=httpx.Response(200, json=_file("bad", "corrupt.bin", checksum="0" * 32))
    )

    with pytest.raises(StorageIntegrityError, match="checksum"):
        await provider.upload(str(local_file), "02_SISTEMA_STORAGE/_tmp/corrupt.bin")


# ------------------------------------------------------------------ download / sync safety


async def test_download_failure_preserves_existing_destination(provider, tmp_path, monkeypatch):
    async def fake_resolve(segments, *, create_missing):
        return "parent-id"

    async def fake_find(parent_id, filename):
        return _file("remote-id", filename)

    async def failing_stream(client, token, file_id):
        yield b"conteudo parcial"
        raise httpx.ReadError("conexão interrompida")

    monkeypatch.setattr(provider, "_resolve_path", fake_resolve)
    monkeypatch.setattr(provider, "_find_file", fake_find)
    monkeypatch.setattr("dhf_storage.google_drive.drive_api.download_stream", failing_stream)

    destination = tmp_path / "avatar.png"
    destination.write_bytes(b"versao integra anterior")

    with pytest.raises(RetryExhaustedError):
        await provider.download("03_AVATAR_IDENTITY_FOTOS/avatar.png", str(destination))

    assert destination.read_bytes() == b"versao integra anterior"
    assert list(tmp_path.glob("*.part")) == []


async def test_download_retries_from_zero_and_validates_checksum(provider, tmp_path, monkeypatch):
    content = b"conteudo completo"
    calls = 0

    async def fake_resolve(segments, *, create_missing):
        return "parent-id"

    async def fake_find(parent_id, filename):
        return _file(
            "remote-id",
            filename,
            size=len(content),
            checksum=hashlib.md5(content).hexdigest(),  # noqa: S324
        )

    async def flaky_stream(client, token, file_id):
        nonlocal calls
        calls += 1
        if calls == 1:
            yield b"parcial"
            raise httpx.ReadError("resposta interrompida")
        yield content

    monkeypatch.setattr(provider, "_resolve_path", fake_resolve)
    monkeypatch.setattr(provider, "_find_file", fake_find)
    monkeypatch.setattr("dhf_storage.google_drive.drive_api.download_stream", flaky_stream)
    destination = tmp_path / "arquivo.bin"

    await provider.download("02_SISTEMA_STORAGE/_tmp/arquivo.bin", str(destination))

    assert calls == 2
    assert destination.read_bytes() == content


async def test_sync_rejects_missing_local_directory(provider, tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="não existe"):
        await provider.sync(str(tmp_path / "ausente"), "03_AVATAR_IDENTITY_FOTOS/avatar")


async def test_sync_rejects_local_file(provider, tmp_path) -> None:
    local_file = tmp_path / "nao-e-diretorio.txt"
    local_file.write_text("x")
    with pytest.raises(NotADirectoryError, match="não é um diretório"):
        await provider.sync(str(local_file), "03_AVATAR_IDENTITY_FOTOS/avatar")


@pytest.mark.parametrize(
    "remote_path",
    [
        "02_SISTEMA_STORAGE",
        "PASTA_INVENTADA/arquivo.png",
        "03_AVATAR_IDENTITY_FOTOS/../segredo.txt",
        "03_AVATAR_IDENTITY_FOTOS//arquivo.png",
        "03_AVATAR_IDENTITY_FOTOS/./arquivo.png",
    ],
)
def test_remote_path_rejects_ambiguous_segments(remote_path) -> None:
    from dhf_storage.google_drive import GoogleDriveStorageProvider

    with pytest.raises(ValueError):
        GoogleDriveStorageProvider._split(remote_path)


async def test_list_rejects_ambiguous_prefix(provider) -> None:
    with pytest.raises(ValueError, match="segmento inválido"):
        await provider.list("03_AVATAR_IDENTITY_FOTOS/../segredos")


# ------------------------------------------------------------------ delete (proteção)


async def test_delete_outside_scratch_without_allow_permanent_is_blocked(
    provider, monkeypatch
) -> None:
    async def fake_resolve(segments, *, create_missing):
        return "parent-id"

    async def fake_find(parent_id, filename):
        return _file("some-id", filename)

    monkeypatch.setattr(provider, "_resolve_path", fake_resolve)
    monkeypatch.setattr(provider, "_find_file", fake_find)

    with pytest.raises(StoragePermanentDeleteBlockedError):
        await provider.delete("03_AVATAR_IDENTITY_FOTOS/lia/v1/head360/000.png")


@respx.mock
async def test_delete_inside_scratch_moves_to_trash(provider, monkeypatch) -> None:
    async def fake_resolve(segments, *, create_missing):
        return "scratch-parent-id"

    async def fake_find(parent_id, filename):
        return _file("scratch-file-id", filename)

    monkeypatch.setattr(provider, "_resolve_path", fake_resolve)
    monkeypatch.setattr(provider, "_find_file", fake_find)

    trash_route = respx.patch(f"{FILES_URL}/scratch-file-id").mock(
        return_value=httpx.Response(200, json={})
    )

    await provider.delete("02_SISTEMA_STORAGE/_tmp/teste.bin")

    assert trash_route.called
    assert json.loads(trash_route.calls.last.request.content) == {"trashed": True}


@respx.mock
async def test_delete_with_allow_permanent_deletes_for_real(provider, monkeypatch) -> None:
    async def fake_resolve(segments, *, create_missing):
        return "parent-id"

    async def fake_find(parent_id, filename):
        return _file("permanent-id", filename)

    monkeypatch.setattr(provider, "_resolve_path", fake_resolve)
    monkeypatch.setattr(provider, "_find_file", fake_find)

    delete_route = respx.delete(f"{FILES_URL}/permanent-id").mock(return_value=httpx.Response(204))

    await provider.delete("03_AVATAR_IDENTITY_FOTOS/velho.png", allow_permanent=True)

    assert delete_route.called


async def test_delete_nonexistent_file_raises(provider, monkeypatch) -> None:
    async def fake_resolve(segments, *, create_missing):
        return "parent-id"

    async def fake_find(parent_id, filename):
        return None

    monkeypatch.setattr(provider, "_resolve_path", fake_resolve)
    monkeypatch.setattr(provider, "_find_file", fake_find)

    with pytest.raises(FileNotFoundError):
        await provider.delete("02_SISTEMA_STORAGE/_tmp/nao-existe.bin")


# ------------------------------------------------------------------ list


@respx.mock
async def test_list_excludes_folders_and_maps_entries(provider, monkeypatch) -> None:
    async def fake_resolve(segments, *, create_missing):
        return "parent-id"

    monkeypatch.setattr(provider, "_resolve_path", fake_resolve)

    respx.get(FILES_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "files": [
                    _folder("sub-id", "subpasta"),
                    _file("f1", "a.png"),
                    _file("f2", "b.png"),
                ]
            },
        )
    )

    entries = await provider.list("03_AVATAR_IDENTITY_FOTOS/lia")

    assert {e.remote_path for e in entries} == {
        "03_AVATAR_IDENTITY_FOTOS/lia/a.png",
        "03_AVATAR_IDENTITY_FOTOS/lia/b.png",
    }


async def test_list_missing_prefix_returns_empty(provider, monkeypatch) -> None:
    async def fake_resolve(segments, *, create_missing):
        raise FileNotFoundError("não existe")

    monkeypatch.setattr(provider, "_resolve_path", fake_resolve)
    assert await provider.list("03_AVATAR_IDENTITY_FOTOS/nao-existe") == []


# ------------------------------------------------------------------ copy / move


@respx.mock
async def test_copy_uses_drive_copy_endpoint(provider, monkeypatch) -> None:
    async def fake_resolve(segments, *, create_missing):
        return "source-parent" if segments[-1] == "origem" else "target-parent"

    async def fake_find(parent_id, filename):
        if parent_id == "source-parent":
            return _file("source-id", filename)
        return None

    monkeypatch.setattr(provider, "_resolve_path", fake_resolve)
    monkeypatch.setattr(provider, "_find_file", fake_find)
    route = respx.post(f"{FILES_URL}/source-id/copy").mock(
        return_value=httpx.Response(200, json=_file("copy-id", "copia.bin"))
    )

    await provider.copy(
        "02_SISTEMA_STORAGE/origem/original.bin",
        "02_SISTEMA_STORAGE/destino/copia.bin",
    )

    assert route.called
    assert json.loads(route.calls.last.request.content) == {
        "name": "copia.bin",
        "parents": ["target-parent"],
    }


@respx.mock
async def test_move_renames_within_same_parent_without_parent_mutation(
    provider, monkeypatch
) -> None:
    async def fake_resolve(segments, *, create_missing):
        return "same-parent"

    async def fake_find(parent_id, filename):
        return _file("source-id", filename) if filename == "antes.bin" else None

    monkeypatch.setattr(provider, "_resolve_path", fake_resolve)
    monkeypatch.setattr(provider, "_find_file", fake_find)
    route = respx.patch(f"{FILES_URL}/source-id").mock(
        return_value=httpx.Response(200, json=_file("source-id", "depois.bin"))
    )

    await provider.move(
        "02_SISTEMA_STORAGE/_tmp/antes.bin",
        "02_SISTEMA_STORAGE/_tmp/depois.bin",
    )

    params = route.calls.last.request.url.params
    assert "addParents" not in params
    assert "removeParents" not in params
    assert json.loads(route.calls.last.request.content) == {"name": "depois.bin"}


async def test_copy_and_move_reject_same_path(provider) -> None:
    path = "02_SISTEMA_STORAGE/_tmp/mesmo.bin"
    with pytest.raises(ValueError, match="iguais"):
        await provider.copy(path, path)
    with pytest.raises(ValueError, match="iguais"):
        await provider.move(path, path)
