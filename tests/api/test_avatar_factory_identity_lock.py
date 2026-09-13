"""Testes de integração do Identity Lock (seção 5) — Postgres real, sem mocks de banco.
Mesmo padrão de `tests/api/test_avatars.py`."""

from __future__ import annotations

import uuid

import httpx
import pytest

pytestmark = pytest.mark.requires_services


def _unique_slug(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def _create_avatar(client: httpx.AsyncClient, prefix: str) -> dict:
    response = await client.post(
        "/avatars", json={"name": prefix, "slug": _unique_slug(prefix), "metadata": {}}
    )
    assert response.status_code == 201
    return response.json()


async def test_upsert_creates_draft_lock_version_one(client: httpx.AsyncClient) -> None:
    avatar = await _create_avatar(client, "lock-criacao")

    response = await client.post(
        f"/avatars/{avatar['id']}/identity-lock",
        json={"identity_spec": {"face": {"face_shape": "oval"}}, "height_cm": 170.5},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "draft"
    assert body["identity_version"] == 1
    assert body["height_cm"] == 170.5
    assert body["identity_spec"]["face"]["face_shape"] == "oval"


async def test_upsert_again_edits_same_draft_in_place(client: httpx.AsyncClient) -> None:
    avatar = await _create_avatar(client, "lock-edicao")
    first = (
        await client.post(
            f"/avatars/{avatar['id']}/identity-lock", json={"identity_spec": {}, "notes": "v1"}
        )
    ).json()

    second = (
        await client.post(
            f"/avatars/{avatar['id']}/identity-lock", json={"identity_spec": {}, "notes": "v2"}
        )
    ).json()

    assert second["id"] == first["id"]
    assert second["identity_version"] == 1
    assert second["notes"] == "v2"
    assert second["version"] == first["version"] + 1


async def test_get_identity_lock_before_creation_returns_404(client: httpx.AsyncClient) -> None:
    avatar = await _create_avatar(client, "lock-inexistente")

    response = await client.get(f"/avatars/{avatar['id']}/identity-lock")

    assert response.status_code == 404


async def test_approve_locks_and_stamps_approver(client: httpx.AsyncClient) -> None:
    avatar = await _create_avatar(client, "lock-aprovacao")
    draft = (
        await client.post(f"/avatars/{avatar['id']}/identity-lock", json={"identity_spec": {}})
    ).json()

    response = await client.post(
        f"/avatars/{avatar['id']}/identity-lock/approve",
        json={"expected_version": draft["version"], "approved_by": "marcos"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["approved_by"] == "marcos"
    assert body["approved_at"] is not None


async def test_approve_twice_is_rejected_lock_is_immutable(client: httpx.AsyncClient) -> None:
    avatar = await _create_avatar(client, "lock-imutavel")
    draft = (
        await client.post(f"/avatars/{avatar['id']}/identity-lock", json={"identity_spec": {}})
    ).json()
    approved = (
        await client.post(
            f"/avatars/{avatar['id']}/identity-lock/approve",
            json={"expected_version": draft["version"], "approved_by": "marcos"},
        )
    ).json()

    response = await client.post(
        f"/avatars/{avatar['id']}/identity-lock/approve",
        json={"expected_version": approved["version"], "approved_by": "marcos"},
    )

    assert response.status_code == 409


async def test_stale_approve_version_returns_409(client: httpx.AsyncClient) -> None:
    avatar = await _create_avatar(client, "lock-versao-obsoleta")
    draft = (
        await client.post(f"/avatars/{avatar['id']}/identity-lock", json={"identity_spec": {}})
    ).json()

    response = await client.post(
        f"/avatars/{avatar['id']}/identity-lock/approve",
        json={"expected_version": draft["version"] + 99, "approved_by": "marcos"},
    )

    assert response.status_code == 409


async def test_relocking_after_approval_creates_new_version_without_touching_old(
    client: httpx.AsyncClient,
) -> None:
    """Seção 18: alterar identidade nunca sobrescreve a versão anterior."""
    avatar = await _create_avatar(client, "lock-nova-versao")
    draft_v1 = (
        await client.post(
            f"/avatars/{avatar['id']}/identity-lock", json={"identity_spec": {}, "notes": "v1"}
        )
    ).json()
    approved_v1 = (
        await client.post(
            f"/avatars/{avatar['id']}/identity-lock/approve",
            json={"expected_version": draft_v1["version"], "approved_by": "marcos"},
        )
    ).json()
    assert approved_v1["identity_version"] == 1

    draft_v2 = (
        await client.post(
            f"/avatars/{avatar['id']}/identity-lock", json={"identity_spec": {}, "notes": "v2"}
        )
    ).json()

    assert draft_v2["identity_version"] == 2
    assert draft_v2["status"] == "draft"
    assert draft_v2["id"] != approved_v1["id"]
    # GET sempre devolve a linha mais recente (a v2 em draft), sem apagar a v1 aprovada.
    current = (await client.get(f"/avatars/{avatar['id']}/identity-lock")).json()
    assert current["id"] == draft_v2["id"]

    approved_v2 = (
        await client.post(
            f"/avatars/{avatar['id']}/identity-lock/approve",
            json={"expected_version": draft_v2["version"], "approved_by": "marcos"},
        )
    ).json()
    assert approved_v2["identity_version"] == 2
    assert approved_v2["status"] == "approved"
