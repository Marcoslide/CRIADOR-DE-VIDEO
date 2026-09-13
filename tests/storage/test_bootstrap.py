"""Bootstrap idempotente da root e árvore gerenciadas pelo aplicativo."""

from datetime import UTC, datetime

import httpx
import pytest
from dhf_schemas.storage import (
    StorageAuthMode,
    StorageConnectionStatus,
    StorageStatus,
    TreeValidationResult,
)
from dhf_storage import drive_api
from dhf_storage.google_drive import ROOT_APP_PROPERTIES, GoogleDriveStorageProvider
from dhf_storage.state import RootState, RootStateError, load_root_state, save_root_state
from dhf_storage.tree import OFFICIAL_TOP_LEVEL_FOLDERS


def _folder(folder_id: str, name: str, *, managed_root: bool = False) -> dict:
    result = {
        "id": folder_id,
        "name": name,
        "mimeType": drive_api.FOLDER_MIME_TYPE,
        "modifiedTime": "2026-09-12T12:00:00.000Z",
    }
    if managed_root:
        result["appProperties"] = ROOT_APP_PROPERTIES
    return result


def _connected_status(root_id: str) -> StorageStatus:
    return StorageStatus(
        status=StorageConnectionStatus.CONNECTED,
        root_folder_id=root_id,
        auth_mode=StorageAuthMode.OAUTH_USER,
        tree=TreeValidationResult(
            expected=OFFICIAL_TOP_LEVEL_FOLDERS,
            found=OFFICIAL_TOP_LEVEL_FOLDERS,
            missing=[],
            unexpected=[],
            valid=True,
        ),
        checked_at=datetime.now(UTC),
    )


async def test_bootstrap_creates_marked_root_tree_and_persists_id(
    unit_settings, tmp_path, monkeypatch
) -> None:
    state_path = tmp_path / "state" / "drive-root.json"
    settings = unit_settings.model_copy(
        update={
            "google_drive_root_folder_id": "",
            "google_drive_root_state_file": str(state_path),
        }
    )
    provider = GoogleDriveStorageProvider(settings)
    created: list[tuple[str, str, dict[str, str] | None]] = []
    list_calls = 0

    async def fake_token():
        return "token"

    async def fake_list(client, token, parent_id, **kwargs):
        nonlocal list_calls
        list_calls += 1
        if parent_id == "root":
            assert kwargs["name"] == "CRIADOR DE VIDEO — STORAGE"
            if list_calls == 1:
                assert kwargs["app_properties"] == ROOT_APP_PROPERTIES
            else:
                assert "app_properties" not in kwargs
            return []
        assert parent_id == "managed-root-id"
        return [_folder("existing-0", OFFICIAL_TOP_LEVEL_FOLDERS[0])]

    async def fake_create(client, token, parent_id, name, **kwargs):
        app_properties = kwargs.pop("app_properties", None)
        created.append((parent_id, name, app_properties))
        if parent_id == "root":
            return _folder("managed-root-id", name, managed_root=True)
        return _folder(f"id-{name}", name)

    async def fake_status(*, force_refresh):
        return _connected_status("managed-root-id")

    monkeypatch.setattr(provider, "_get_token", fake_token)
    monkeypatch.setattr(provider, "get_status", fake_status)
    monkeypatch.setattr(drive_api, "list_children", fake_list)
    monkeypatch.setattr(drive_api, "create_folder", fake_create)

    status = await provider.bootstrap()

    assert status.status == StorageConnectionStatus.CONNECTED
    assert list_calls == 3
    assert created[0] == ("root", "CRIADOR DE VIDEO — STORAGE", ROOT_APP_PROPERTIES)
    assert {name for parent, name, _ in created if parent == "managed-root-id"} == set(
        OFFICIAL_TOP_LEVEL_FOLDERS[1:]
    )
    persisted = load_root_state(state_path)
    assert persisted is not None
    assert persisted.root_folder_id == "managed-root-id"
    await provider.aclose()


async def test_bootstrap_reuses_persisted_id_without_discovery_or_creation(
    unit_settings, tmp_path, monkeypatch
) -> None:
    state_path = tmp_path / "drive-root.json"
    save_root_state(
        state_path,
        RootState("managed-root-id", "CRIADOR DE VIDEO — STORAGE"),
    )
    settings = unit_settings.model_copy(
        update={
            "google_drive_root_folder_id": "",
            "google_drive_root_state_file": str(state_path),
        }
    )
    provider = GoogleDriveStorageProvider(settings)

    async def fake_token():
        return "token"

    async def fake_metadata(client, token, file_id, **kwargs):
        assert file_id == "managed-root-id"
        return _folder(file_id, "CRIADOR DE VIDEO — STORAGE", managed_root=True)

    async def fake_list(client, token, parent_id, **kwargs):
        assert parent_id == "managed-root-id"
        assert "app_properties" not in kwargs
        return [_folder(f"id-{i}", name) for i, name in enumerate(OFFICIAL_TOP_LEVEL_FOLDERS)]

    async def must_not_create(*args, **kwargs):
        raise AssertionError("bootstrap idempotente não deve criar outra pasta")

    async def fake_status(*, force_refresh):
        return _connected_status("managed-root-id")

    monkeypatch.setattr(provider, "_get_token", fake_token)
    monkeypatch.setattr(provider, "get_status", fake_status)
    monkeypatch.setattr(drive_api, "get_file_metadata", fake_metadata)
    monkeypatch.setattr(drive_api, "list_children", fake_list)
    monkeypatch.setattr(drive_api, "create_folder", must_not_create)

    await provider.bootstrap()
    assert provider._root_folder_id == "managed-root-id"
    await provider.aclose()


async def test_bootstrap_refuses_multiple_marked_roots(
    unit_settings, tmp_path, monkeypatch
) -> None:
    settings = unit_settings.model_copy(
        update={
            "google_drive_root_folder_id": "",
            "google_drive_root_state_file": str(tmp_path / "state.json"),
        }
    )
    provider = GoogleDriveStorageProvider(settings)

    async def fake_token():
        return "token"

    async def fake_list(client, token, parent_id, **kwargs):
        return [
            _folder("one", "CRIADOR DE VIDEO — STORAGE", managed_root=True),
            _folder("two", "CRIADOR DE VIDEO — STORAGE", managed_root=True),
        ]

    monkeypatch.setattr(provider, "_get_token", fake_token)
    monkeypatch.setattr(drive_api, "list_children", fake_list)

    with pytest.raises(RootStateError, match="mais de uma root"):
        await provider.bootstrap()
    await provider.aclose()


async def test_bootstrap_refuses_visible_unmarked_name_collision(
    unit_settings, tmp_path, monkeypatch
) -> None:
    settings = unit_settings.model_copy(
        update={
            "google_drive_root_folder_id": "",
            "google_drive_root_state_file": str(tmp_path / "state.json"),
        }
    )
    provider = GoogleDriveStorageProvider(settings)
    calls = 0

    async def fake_token():
        return "token"

    async def fake_list(client, token, parent_id, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return []
        return [_folder("collision", "CRIADOR DE VIDEO — STORAGE")]

    async def must_not_create(*args, **kwargs):
        raise AssertionError("colisão de nome não pode criar outra root")

    monkeypatch.setattr(provider, "_get_token", fake_token)
    monkeypatch.setattr(drive_api, "list_children", fake_list)
    monkeypatch.setattr(drive_api, "create_folder", must_not_create)

    with pytest.raises(RootStateError, match="nenhuma nova root"):
        await provider.bootstrap()
    await provider.aclose()


@pytest.mark.asyncio
async def test_root_discovery_query_includes_private_marker(respx_mock) -> None:
    route = respx_mock.get(drive_api.FILES_URL).mock(
        return_value=httpx.Response(200, json={"files": []})
    )
    async with httpx.AsyncClient() as client:
        await drive_api.list_children(
            client,
            "token",
            "root",
            name="CRIADOR DE VIDEO — STORAGE",
            folders_only=True,
            app_properties=ROOT_APP_PROPERTIES,
            max_retries=0,
            base_delay_s=0,
        )
    query = route.calls.last.request.url.params["q"]
    assert "appProperties has" in query
    assert "dhf_storage_root" in query
    assert "value = 'v1'" in query


def test_http_404_detection_is_precise() -> None:
    request = httpx.Request("GET", "https://example.invalid/root")
    response = httpx.Response(404, request=request)
    exc = httpx.HTTPStatusError("missing", request=request, response=response)
    assert GoogleDriveStorageProvider._is_not_found(exc)
