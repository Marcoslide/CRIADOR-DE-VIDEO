"""Testes de integração do Reference Asset Manifest (seções 7-12, 15-16) — Postgres real
+ um dublê de Storage (`fake_storage_provider`, ver conftest.py) no lugar do Google Drive
de verdade, já que o upload em si não é o que este pacote testa (isso é
`tests/storage/`)."""

from __future__ import annotations

import io
import uuid
from typing import TYPE_CHECKING

import httpx
import pytest
from PIL import Image

if TYPE_CHECKING:
    from tests.api.conftest import FakeStorageProvider

pytestmark = pytest.mark.requires_services


def _unique_slug(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def _create_avatar(client: httpx.AsyncClient, prefix: str) -> dict:
    response = await client.post(
        "/avatars", json={"name": prefix, "slug": _unique_slug(prefix), "metadata": {}}
    )
    assert response.status_code == 201
    return response.json()


def _photo_bytes(seed: int = 0) -> bytes:
    """Ruído por pixel (não cor sólida) — passa nos checks determinísticos de verdade,
    inclusive o heurístico de blur (ver tests/avatar_factory/test_qa_checks.py)."""
    import random

    rng = random.Random(seed)
    image = Image.new("RGB", (640, 640))
    pixels = image.load()
    for x in range(640):
        for y in range(640):
            value = rng.randint(20, 235)
            pixels[x, y] = (value, value, value)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


async def _upload(
    client: httpx.AsyncClient,
    avatar_id: str,
    *,
    category: str,
    angle: int | None = None,
    seed: int = 0,
) -> httpx.Response:
    data = {"category": category}
    if angle is not None:
        data["angle"] = str(angle)
    files = {"file": ("ref.png", _photo_bytes(seed), "image/png")}
    return await client.post(f"/avatars/{avatar_id}/references", data=data, files=files)


async def test_upload_angle_category_requires_angle(
    client: httpx.AsyncClient, fake_storage_provider: FakeStorageProvider
) -> None:
    avatar = await _create_avatar(client, "ref-angulo-obrigatorio")

    response = await _upload(client, avatar["id"], category="head_360", angle=None)

    assert response.status_code == 422


async def test_upload_non_angle_category_rejects_angle(
    client: httpx.AsyncClient, fake_storage_provider: FakeStorageProvider
) -> None:
    avatar = await _create_avatar(client, "ref-angulo-indevido")

    response = await _upload(client, avatar["id"], category="face_front_neutral", angle=10)

    assert response.status_code == 422


async def test_upload_rejects_angle_not_multiple_of_ten(
    client: httpx.AsyncClient, fake_storage_provider: FakeStorageProvider
) -> None:
    avatar = await _create_avatar(client, "ref-angulo-invalido")

    response = await _upload(client, avatar["id"], category="head_360", angle=15)

    assert response.status_code == 422


async def test_upload_head_360_stores_metadata_and_uploads_to_storage(
    client: httpx.AsyncClient, fake_storage_provider: FakeStorageProvider
) -> None:
    avatar = await _create_avatar(client, "ref-head360")

    response = await _upload(client, avatar["id"], category="head_360", angle=0, seed=1)

    assert response.status_code == 201
    body = response.json()
    assert body["category"] == "head_360"
    assert body["angle"] == 0
    assert body["qa_status"] in ("pass", "warn")
    assert body["resolution_width"] == 640
    assert body["resolution_height"] == 640
    assert body["upload_state"] == "uploaded"
    assert avatar["slug"] in body["storage_remote_path"]
    assert "03_AVATAR_IDENTITY_FOTOS" in body["storage_remote_path"]
    assert body["storage_remote_path"] in fake_storage_provider.uploaded


async def test_reference_content_proxies_the_original_bytes(
    client: httpx.AsyncClient, fake_storage_provider: FakeStorageProvider
) -> None:
    avatar = await _create_avatar(client, "ref-conteudo")
    original = _photo_bytes(seed=99)
    uploaded = (
        await client.post(
            f"/avatars/{avatar['id']}/references",
            data={"category": "head_360", "angle": "0"},
            files={"file": ("ref.png", original, "image/png")},
        )
    ).json()

    response = await client.get(f"/avatars/{avatar['id']}/references/{uploaded['id']}/content")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == original


async def test_duplicate_upload_fails_qa_with_duplicate_checksum(
    client: httpx.AsyncClient, fake_storage_provider: FakeStorageProvider
) -> None:
    avatar = await _create_avatar(client, "ref-duplicata")
    await _upload(client, avatar["id"], category="face_front_neutral", seed=7)

    second = await _upload(client, avatar["id"], category="face_left_profile", seed=7)

    assert second.status_code == 201
    body = second.json()
    assert body["qa_status"] == "fail"
    assert body["qa_detail"]["duplicate_file"]["status"] == "fail"


async def test_approve_and_reject_reference_flow(
    client: httpx.AsyncClient, fake_storage_provider: FakeStorageProvider
) -> None:
    avatar = await _create_avatar(client, "ref-revisao")
    uploaded = (await _upload(client, avatar["id"], category="face_front_neutral", seed=3)).json()

    approved = await client.post(
        f"/avatars/{avatar['id']}/references/{uploaded['id']}/approve",
        json={"expected_version": uploaded["version"], "reviewed_by": "marcos"},
    )
    assert approved.status_code == 200
    assert approved.json()["approved"] is True
    assert approved.json()["upload_state"] == "approved"

    second_upload = (
        await _upload(client, avatar["id"], category="face_left_profile", seed=4)
    ).json()
    rejected = await client.post(
        f"/avatars/{avatar['id']}/references/{second_upload['id']}/reject",
        json={
            "expected_version": second_upload["version"],
            "reason": "blur",
            "notes": "fora de foco",
            "reviewed_by": "marcos",
        },
    )
    assert rejected.status_code == 200
    body = rejected.json()
    assert body["approved"] is False
    assert body["upload_state"] == "rejected"
    assert body["rejection_reason"] == "blur"
    assert body["rejection_notes"] == "fora de foco"


async def test_reject_stale_version_returns_409(
    client: httpx.AsyncClient, fake_storage_provider: FakeStorageProvider
) -> None:
    avatar = await _create_avatar(client, "ref-versao-obsoleta")
    uploaded = (await _upload(client, avatar["id"], category="mouth_closed", seed=9)).json()

    response = await client.post(
        f"/avatars/{avatar['id']}/references/{uploaded['id']}/reject",
        json={
            "expected_version": uploaded["version"] + 5,
            "reason": "other",
            "reviewed_by": "marcos",
        },
    )

    assert response.status_code == 409


async def test_multiview_endpoint_reflects_uploaded_and_approved_assets(
    client: httpx.AsyncClient, fake_storage_provider: FakeStorageProvider
) -> None:
    avatar = await _create_avatar(client, "ref-multiview")
    uploaded = (await _upload(client, avatar["id"], category="head_360", angle=0, seed=11)).json()
    await client.post(
        f"/avatars/{avatar['id']}/references/{uploaded['id']}/approve",
        json={"expected_version": uploaded["version"], "reviewed_by": "marcos"},
    )

    response = await client.get(f"/avatars/{avatar['id']}/multiview")

    assert response.status_code == 200
    body = response.json()
    assert body["head_360"]["done"] == 1
    assert body["head_360"]["total"] == 36
    zero_slot = next(slot for slot in body["head_360"]["slots"] if slot["angle"] == 0)
    assert zero_slot["state"] == "approved"
    assert body["all_required_approved"] is False


async def test_list_references_filters_by_category(
    client: httpx.AsyncClient, fake_storage_provider: FakeStorageProvider
) -> None:
    avatar = await _create_avatar(client, "ref-filtro")
    await _upload(client, avatar["id"], category="head_360", angle=0, seed=21)
    await _upload(client, avatar["id"], category="ear_left", seed=22)

    response = await client.get(
        f"/avatars/{avatar['id']}/references", params={"category": "ear_left"}
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["category"] == "ear_left"


# --- P1-2: um avatar nunca acessa reference asset de outro ----------------------------------


async def test_approve_reference_from_another_avatar_returns_404(
    client: httpx.AsyncClient, fake_storage_provider: FakeStorageProvider
) -> None:
    avatar_a = await _create_avatar(client, "cross-a-approve")
    avatar_b = await _create_avatar(client, "cross-b-approve")
    asset_b = (
        await _upload(client, avatar_b["id"], category="face_front_neutral", seed=201)
    ).json()

    response = await client.post(
        f"/avatars/{avatar_a['id']}/references/{asset_b['id']}/approve",
        json={"expected_version": asset_b["version"], "reviewed_by": "marcos"},
    )

    assert response.status_code == 404
    # o asset em si não foi tocado — continua não aprovado no avatar dono real.
    still_unapproved = (await client.get(f"/avatars/{avatar_b['id']}/references")).json()
    assert still_unapproved[0]["approved"] is False


async def test_reject_reference_from_another_avatar_returns_404(
    client: httpx.AsyncClient, fake_storage_provider: FakeStorageProvider
) -> None:
    avatar_a = await _create_avatar(client, "cross-a-reject")
    avatar_b = await _create_avatar(client, "cross-b-reject")
    asset_b = (
        await _upload(client, avatar_b["id"], category="face_front_neutral", seed=202)
    ).json()

    response = await client.post(
        f"/avatars/{avatar_a['id']}/references/{asset_b['id']}/reject",
        json={"expected_version": asset_b["version"], "reason": "other", "reviewed_by": "marcos"},
    )

    assert response.status_code == 404


async def test_reference_content_from_another_avatar_returns_404(
    client: httpx.AsyncClient, fake_storage_provider: FakeStorageProvider
) -> None:
    avatar_a = await _create_avatar(client, "cross-a-content")
    avatar_b = await _create_avatar(client, "cross-b-content")
    asset_b = (
        await _upload(client, avatar_b["id"], category="face_front_neutral", seed=203)
    ).json()

    response = await client.get(f"/avatars/{avatar_a['id']}/references/{asset_b['id']}/content")

    assert response.status_code == 404


async def test_approve_reference_from_correct_avatar_still_works(
    client: httpx.AsyncClient, fake_storage_provider: FakeStorageProvider
) -> None:
    """Garante que a checagem de P1-2 não é overly-strict: o dono de verdade continua
    conseguindo aprovar seus próprios assets."""
    avatar = await _create_avatar(client, "cross-dono-legitimo")
    asset = (await _upload(client, avatar["id"], category="face_front_neutral", seed=204)).json()

    response = await client.post(
        f"/avatars/{avatar['id']}/references/{asset['id']}/approve",
        json={"expected_version": asset["version"], "reviewed_by": "marcos"},
    )

    assert response.status_code == 200
    assert response.json()["approved"] is True


# --- P1-3: recaptura nunca sobrescreve o binário anterior ------------------------------------


async def test_recapture_same_slot_produces_two_distinct_immutable_paths(
    client: httpx.AsyncClient, fake_storage_provider: FakeStorageProvider
) -> None:
    avatar = await _create_avatar(client, "recapture-imutavel")
    image_a = _photo_bytes(seed=301)
    image_b = _photo_bytes(seed=302)
    assert image_a != image_b

    first = (
        await client.post(
            f"/avatars/{avatar['id']}/references",
            data={"category": "head_360", "angle": "0"},
            files={"file": ("a.png", image_a, "image/png")},
        )
    ).json()
    second = (
        await client.post(
            f"/avatars/{avatar['id']}/references",
            data={"category": "head_360", "angle": "0"},
            files={"file": ("b.png", image_b, "image/png")},
        )
    ).json()

    assert first["id"] != second["id"]
    assert first["storage_remote_path"] != second["storage_remote_path"]
    assert str(first["id"]) in first["storage_remote_path"]
    assert str(second["id"]) in second["storage_remote_path"]
    assert first["checksum"] != second["checksum"]

    # os DOIS binários continuam recuperáveis no Storage — a recaptura nunca sobrescreveu
    # o objeto remoto da captura anterior.
    assert fake_storage_provider.uploaded[first["storage_remote_path"]] == image_a
    assert fake_storage_provider.uploaded[second["storage_remote_path"]] == image_b

    content_a = await client.get(f"/avatars/{avatar['id']}/references/{first['id']}/content")
    content_b = await client.get(f"/avatars/{avatar['id']}/references/{second['id']}/content")
    assert content_a.content == image_a
    assert content_b.content == image_b


async def test_capture_version_is_not_hardcoded_and_follows_identity_generation(
    client: httpx.AsyncClient, fake_storage_provider: FakeStorageProvider
) -> None:
    """P1-3/P1-5: `capture_version` acompanha a geração de identidade OFICIAL (aprovada)
    do avatar — nunca fica preso em 1."""
    avatar = await _create_avatar(client, "capture-version-real")
    draft_v1 = (
        await client.post(f"/avatars/{avatar['id']}/identity-lock", json={"identity_spec": {}})
    ).json()
    await client.post(
        f"/avatars/{avatar['id']}/identity-lock/approve",
        json={"expected_version": draft_v1["version"], "approved_by": "marcos"},
    )
    first = (await _upload(client, avatar["id"], category="face_front_neutral", seed=311)).json()
    assert first["capture_version"] == 1

    draft_v2 = (
        await client.post(
            f"/avatars/{avatar['id']}/identity-lock", json={"identity_spec": {}, "notes": "v2"}
        )
    ).json()
    await client.post(
        f"/avatars/{avatar['id']}/identity-lock/approve",
        json={"expected_version": draft_v2["version"], "approved_by": "marcos"},
    )
    second = (await _upload(client, avatar["id"], category="face_front_neutral", seed=312)).json()
    assert second["capture_version"] == 2
