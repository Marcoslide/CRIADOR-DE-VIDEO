"""Testes unitários do GoogleDriveStorageProvider — toda chamada de rede é mockada via
respx (intercepta o httpx de verdade, não é um stub à parte). Nenhum destes testes prova a
integração real com o Google Drive — isso é `test_google_drive_integration.py`.
"""

import json

import httpx
import pytest
import respx
from dhf_schemas.storage import (
    StorageConnectionStatus,
    StorageNotConfiguredError,
    StoragePermanentDeleteBlockedError,
)
from dhf_storage.drive_api import FILES_URL, UPLOAD_URL
from dhf_storage.tree import OFFICIAL_TOP_LEVEL_FOLDERS


def _folder(folder_id: str, name: str) -> dict:
    return {
        "id": folder_id,
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "modifiedTime": "2026-09-10T12:00:00.000Z",
    }


def _file(file_id: str, name: str, *, size: int = 1024) -> dict:
    return {
        "id": file_id,
        "name": name,
        "mimeType": "image/png",
        "size": str(size),
        "md5Checksum": "d41d8cd98f00b204e9800998ecf8427e",
        "modifiedTime": "2026-09-10T12:00:00.000Z",
        "webViewLink": f"https://drive.google.com/file/d/{file_id}/view",
    }


# ------------------------------------------------------------------ get_status


async def test_get_status_not_configured_without_credentials(unconfigured_provider) -> None:
    status = await unconfigured_provider.get_status(force_refresh=True)
    assert status.status == StorageConnectionStatus.NOT_CONFIGURED
    assert status.tree is None


@respx.mock
async def test_get_status_connected_when_all_folders_present(provider) -> None:
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


@respx.mock
async def test_get_status_degraded_when_folder_missing(provider) -> None:
    incomplete = OFFICIAL_TOP_LEVEL_FOLDERS[:-1]
    respx.get(FILES_URL).mock(
        return_value=httpx.Response(
            200, json={"files": [_folder(f"id-{i}", n) for i, n in enumerate(incomplete)]}
        )
    )
    status = await provider.get_status(force_refresh=True)
    assert status.status == StorageConnectionStatus.DEGRADED
    assert status.tree.missing == [OFFICIAL_TOP_LEVEL_FOLDERS[-1]]


@respx.mock
async def test_get_status_error_when_api_fails(provider) -> None:
    respx.get(FILES_URL).mock(return_value=httpx.Response(500, json={"error": "boom"}))
    status = await provider.get_status(force_refresh=True)
    assert status.status == StorageConnectionStatus.ERROR
    assert status.detail is not None


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
    with pytest.raises(ValueError, match="não é uma das 18 pastas oficiais"):
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

    init_route = respx.post(UPLOAD_URL, params={"uploadType": "resumable"}).mock(
        return_value=httpx.Response(200, headers={"Location": "https://upload.example/session-1"})
    )
    put_route = respx.put("https://upload.example/session-1").mock(
        return_value=httpx.Response(
            200, json=_file("new-file-id", "000.png", size=local_file.stat().st_size)
        )
    )

    entry = await provider.upload(
        str(local_file), "03_AVATAR_IDENTITY_FOTOS/lia/v1/head360/000.png"
    )

    assert init_route.called
    assert put_route.called
    assert entry.provider_id == "new-file-id"
    assert entry.size_bytes == local_file.stat().st_size
    assert entry.checksum == "d41d8cd98f00b204e9800998ecf8427e"


@respx.mock
async def test_upload_retry_resends_complete_file_after_stream_consumed(
    provider, tmp_path, monkeypatch
) -> None:
    """Regressão: um AsyncIterator já consumido (mesmo que parcialmente) não pode ser
    reaproveitado numa nova tentativa — precisa reabrir o arquivo do byte 0. Sem o fix,
    a 2a chamada ao PUT receberia um corpo vazio/truncado (o generator já esgotado),
    silenciosamente corrompendo o upload em vez de reenviar o arquivo inteiro."""

    async def fake_resolve(segments, *, create_missing):
        return "parent-id"

    async def fake_find(parent_id, filename):
        return None

    monkeypatch.setattr(provider, "_resolve_path", fake_resolve)
    monkeypatch.setattr(provider, "_find_file", fake_find)
    # chunk pequeno de propósito: força múltiplos chunks por tentativa, exercitando o
    # generator de verdade em vez de um único read() que mascararia o bug.
    monkeypatch.setattr(provider._settings, "google_drive_upload_chunk_size_bytes", 16)

    content = bytes(range(256)) * 4  # 1024 bytes -> 64 chunks de 16 bytes por tentativa
    local_file = tmp_path / "large.bin"
    local_file.write_bytes(content)

    respx.post(UPLOAD_URL, params={"uploadType": "resumable"}).mock(
        return_value=httpx.Response(
            200, headers={"Location": "https://upload.example/session-retry"}
        )
    )
    put_route = respx.put("https://upload.example/session-retry").mock(
        side_effect=[
            httpx.Response(500, json={"error": "instabilidade simulada"}),
            httpx.Response(200, json=_file("retried-file-id", "large.bin", size=len(content))),
        ]
    )

    entry = await provider.upload(str(local_file), "03_AVATAR_IDENTITY_FOTOS/large.bin")

    assert put_route.call_count == 2
    first_attempt_body = put_route.calls[0].request.content
    second_attempt_body = put_route.calls[1].request.content

    # a tentativa que falhou já tinha recebido o arquivo inteiro (não é isso que estava
    # quebrado) — o que importa é que o RETRY também recebeu o arquivo inteiro, não um
    # corpo vazio/truncado por reaproveitar um generator já esgotado.
    assert first_attempt_body == content
    assert second_attempt_body == content
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

    init_route = respx.patch(f"{UPLOAD_URL}/existing-id", params={"uploadType": "resumable"}).mock(
        return_value=httpx.Response(200, headers={"Location": "https://upload.example/session-2"})
    )
    respx.put("https://upload.example/session-2").mock(
        return_value=httpx.Response(200, json=_file("existing-id", "000.png"))
    )

    entry = await provider.upload(str(local_file), "03_AVATAR_IDENTITY_FOTOS/000.png")

    assert init_route.called
    assert entry.provider_id == "existing-id"


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
