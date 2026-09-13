"""Testes de integração dos Quality Gates e do enforcement de status (seções 2-4, 17,
22-25) — a parte mais crítica da missão: nada pode avançar sem evidência real. Postgres
real, sem mocks de banco."""

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


async def _force_status(client: httpx.AsyncClient, avatar: dict, status: str) -> dict:
    """Usa o PATCH genérico já existente de `dhf_avatars` (não-gateado, nunca alterado
    por esta missão) só para preparar o estado inicial do teste — o que está sob teste é
    sempre o comportamento dos NOVOS endpoints de gate, não este atalho de setup."""
    response = await client.patch(
        f"/avatars/{avatar['id']}", json={"status": status, "expected_version": avatar["version"]}
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_approve_identity_gate_blocked_without_approved_lock(
    client: httpx.AsyncClient,
) -> None:
    avatar = await _create_avatar(client, "gate-identity-bloqueado")

    response = await client.post(
        f"/avatars/{avatar['id']}/quality-gates/identity/approve",
        json={"expected_version": avatar["version"], "actor": "marcos"},
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "não atendidos" in detail["message"]
    assert any("identity lock" in item.lower() for item in detail["missing"])


async def test_approve_identity_gate_advances_status_and_records_history(
    client: httpx.AsyncClient,
) -> None:
    avatar = await _create_avatar(client, "gate-identity-ok")
    draft = (
        await client.post(f"/avatars/{avatar['id']}/identity-lock", json={"identity_spec": {}})
    ).json()
    await client.post(
        f"/avatars/{avatar['id']}/identity-lock/approve",
        json={"expected_version": draft["version"], "approved_by": "marcos"},
    )

    response = await client.post(
        f"/avatars/{avatar['id']}/quality-gates/identity/approve",
        json={
            "expected_version": avatar["version"],
            "actor": "marcos",
            "reason": "identidade completa",
        },
    )

    assert response.status_code == 200
    gate = response.json()
    assert gate["status"] == "pass"
    assert gate["approved_by"] == "marcos"

    updated_avatar = (await client.get(f"/avatars/{avatar['id']}")).json()
    assert updated_avatar["status"] == "identity_locked"
    assert updated_avatar["version"] == avatar["version"] + 1

    history = (await client.get(f"/avatars/{avatar['id']}/history")).json()
    assert len(history) == 1
    assert history[0]["from_status"] == "draft"
    assert history[0]["to_status"] == "identity_locked"
    assert history[0]["quality_gate"] == "identity"
    assert history[0]["actor"] == "marcos"


async def test_approve_gate_with_stale_avatar_version_returns_409(
    client: httpx.AsyncClient,
) -> None:
    avatar = await _create_avatar(client, "gate-versao-obsoleta")

    response = await client.post(
        f"/avatars/{avatar['id']}/quality-gates/identity/approve",
        json={"expected_version": avatar["version"] + 7, "actor": "marcos"},
    )

    assert response.status_code == 409


async def test_approve_gate_invalid_for_current_status_returns_409(
    client: httpx.AsyncClient,
) -> None:
    """MESH só pode ser aprovado a partir de MESH_IN_PROGRESS — tentar direto do DRAFT
    precisa falhar por adjacência, não silenciosamente pular etapas (seção 4)."""
    avatar = await _create_avatar(client, "gate-status-invalido")

    response = await client.post(
        f"/avatars/{avatar['id']}/quality-gates/mesh/approve",
        json={"expected_version": avatar["version"], "actor": "marcos"},
    )

    assert response.status_code == 409


async def test_multiview_gate_blocked_with_no_references_uploaded(
    client: httpx.AsyncClient,
) -> None:
    avatar = await _create_avatar(client, "gate-multiview-vazio")
    draft = (
        await client.post(f"/avatars/{avatar['id']}/identity-lock", json={"identity_spec": {}})
    ).json()
    await client.post(
        f"/avatars/{avatar['id']}/identity-lock/approve",
        json={"expected_version": draft["version"], "approved_by": "marcos"},
    )
    identity_locked = await _force_status(client, avatar, "identity_locked")
    in_progress = await _force_status(client, identity_locked, "multiview_in_progress")

    response = await client.post(
        f"/avatars/{avatar['id']}/quality-gates/multiview/approve",
        json={"expected_version": in_progress["version"], "actor": "marcos"},
    )

    assert response.status_code == 409
    missing = response.json()["detail"]["missing"]
    assert any("head_360" in item for item in missing)
    assert any("half_body_360" in item for item in missing)
    assert any("full_body_360" in item for item in missing)


async def test_gpu_dependent_gate_is_always_blocked_pending_rtx_4090(
    client: httpx.AsyncClient,
) -> None:
    """Mesh/Rig/Materials/Face/Voice/Motion/Master nunca podem ser aprovados nesta
    missão (seção 39: nada de mesh/textura real ainda) — mesmo alcançando o status
    certo, o requisito de DerivedAsset GENERATED nunca existe."""
    avatar = await _create_avatar(client, "gate-gpu-bloqueado")
    draft = (
        await client.post(f"/avatars/{avatar['id']}/identity-lock", json={"identity_spec": {}})
    ).json()
    await client.post(
        f"/avatars/{avatar['id']}/identity-lock/approve",
        json={"expected_version": draft["version"], "approved_by": "marcos"},
    )
    avatar = await _force_status(client, avatar, "identity_locked")
    avatar = await _force_status(client, avatar, "multiview_in_progress")
    avatar = await _force_status(client, avatar, "multiview_approved")
    avatar = await _force_status(client, avatar, "mesh_in_progress")

    response = await client.post(
        f"/avatars/{avatar['id']}/quality-gates/mesh/approve",
        json={"expected_version": avatar["version"], "actor": "marcos"},
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "DerivedAsset" in detail["missing"][0]


async def test_reject_gate_records_decision_without_advancing_status(
    client: httpx.AsyncClient,
) -> None:
    avatar = await _create_avatar(client, "gate-rejeitado")

    response = await client.post(
        f"/avatars/{avatar['id']}/quality-gates/identity/reject",
        json={"expected_version": avatar["version"], "actor": "marcos", "reason": "faltam dados"},
    )

    assert response.status_code == 200
    gate = response.json()
    assert gate["status"] == "fail"
    assert gate["reason"] == "faltam dados"

    unchanged_avatar = (await client.get(f"/avatars/{avatar['id']}")).json()
    assert unchanged_avatar["status"] == "draft"
    assert unchanged_avatar["version"] == avatar["version"]  # avatar em si não mudou

    history = (await client.get(f"/avatars/{avatar['id']}/history")).json()
    assert history == []  # rejeição não é uma transição de status


async def test_readiness_reports_missing_gates_and_never_fakes_production_ready(
    client: httpx.AsyncClient,
) -> None:
    avatar = await _create_avatar(client, "readiness-inicial")

    response = await client.get(f"/avatars/{avatar['id']}/readiness")

    assert response.status_code == 200
    body = response.json()
    assert body["production_ready"] is False
    assert body["status"] == "draft"
    assert set(body["missing"]) == {
        "identity",
        "multiview",
        "mesh",
        "rig",
        "materials",
        "face",
        "voice",
        "motion",
        "master",
    }


async def test_factory_view_aggregates_everything_in_one_call(client: httpx.AsyncClient) -> None:
    avatar = await _create_avatar(client, "factory-view")

    response = await client.get(f"/avatars/{avatar['id']}/factory")

    assert response.status_code == 200
    body = response.json()
    assert body["avatar_id"] == avatar["id"]
    assert body["identity_lock"] is None
    assert len(body["quality_gates"]) == 10
    assert len(body["derived_assets"]) == 12  # um por DerivedAssetType (seção 19)
    assert len(body["job_contracts"]) == 8  # um por JobContractType (seção 20)
    assert all(asset["status"] == "not_generated" for asset in body["derived_assets"])
    assert all(job["status"] == "blocked" for job in body["job_contracts"])
    assert body["readiness"]["production_ready"] is False
