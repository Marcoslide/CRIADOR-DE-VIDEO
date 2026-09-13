"""Testes de integração dos Quality Gates e do enforcement de status (seções 2-4, 17,
22-25) — a parte mais crítica da missão: nada pode avançar sem evidência real. Postgres
real, sem mocks de banco.

P1-1 (correção obrigatória): nenhum teste aqui usa mais o PATCH genérico para "pular"
para um status gate-protected (isso agora é bloqueado em produção também — ver
`tests/api/test_avatars.py::test_patch_cannot_set_gate_protected_status_even_when_adjacent`).
Todo avanço de status passa pelo fluxo real via as fixtures de `conftest.py`."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import httpx
import pytest

if TYPE_CHECKING:
    from tests.api.conftest import (
        AdvanceToIdentityLocked,
        CompleteFullMultiview,
        FakeStorageProvider,
    )

pytestmark = pytest.mark.requires_services


def _unique_slug(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


async def _create_avatar(client: httpx.AsyncClient, prefix: str) -> dict:
    response = await client.post(
        "/avatars", json={"name": prefix, "slug": _unique_slug(prefix), "metadata": {}}
    )
    assert response.status_code == 201
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
    client: httpx.AsyncClient, advance_to_identity_locked: AdvanceToIdentityLocked
) -> None:
    avatar = await _create_avatar(client, "gate-multiview-vazio")
    identity_locked = await advance_to_identity_locked(client, avatar)
    in_progress = (
        await client.patch(
            f"/avatars/{avatar['id']}",
            json={
                "status": "multiview_in_progress",
                "expected_version": identity_locked["version"],
            },
        )
    ).json()

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
    advance_to_identity_locked: AdvanceToIdentityLocked,
    complete_full_multiview_and_approve: CompleteFullMultiview,
    fake_storage_provider: FakeStorageProvider,
) -> None:
    """Mesh/Rig/Materials/Face/Voice/Motion/Master nunca podem ser aprovados nesta
    missão (seção 39: nada de mesh/textura real ainda) — mesmo alcançando o status
    certo pelo fluxo real (identity + multiview completos), o requisito de DerivedAsset
    GENERATED nunca existe."""
    avatar = await _create_avatar(client, "gate-gpu-bloqueado")
    identity_locked = await advance_to_identity_locked(client, avatar)
    in_progress = (
        await client.patch(
            f"/avatars/{avatar['id']}",
            json={
                "status": "multiview_in_progress",
                "expected_version": identity_locked["version"],
            },
        )
    ).json()
    multiview_approved = await complete_full_multiview_and_approve(client, in_progress)
    mesh_in_progress = (
        await client.patch(
            f"/avatars/{avatar['id']}",
            json={
                "status": "mesh_in_progress",
                "expected_version": multiview_approved["version"],
            },
        )
    ).json()

    response = await client.post(
        f"/avatars/{avatar['id']}/quality-gates/mesh/approve",
        json={"expected_version": mesh_in_progress["version"], "actor": "marcos"},
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


# --- P1-4: atomicidade da transação de aprovação de gate ------------------------------------


async def test_approve_gate_rejects_stale_avatar_version_before_writing_anything(
    client: httpx.AsyncClient,
) -> None:
    """Uma modificação concorrente que bumpa a versão do avatar entre o cliente montar o
    request e o approve rodar precisa abortar a operação inteira sem escrever nada — nem
    o gate muda de status, nem uma decisão ou transição é registrada."""
    avatar = await _create_avatar(client, "gate-atomico-conflito")
    draft = (
        await client.post(f"/avatars/{avatar['id']}/identity-lock", json={"identity_spec": {}})
    ).json()
    await client.post(
        f"/avatars/{avatar['id']}/identity-lock/approve",
        json={"expected_version": draft["version"], "approved_by": "marcos"},
    )

    # Modificação concorrente que bumpa a versão do avatar DEPOIS que o cliente do teste
    # já "decidiu" usar `avatar["version"]` original como expected_version do approve.
    await client.patch(
        f"/avatars/{avatar['id']}",
        json={"metadata": {"concorrente": True}, "expected_version": avatar["version"]},
    )

    response = await client.post(
        f"/avatars/{avatar['id']}/quality-gates/identity/approve",
        json={"expected_version": avatar["version"], "actor": "marcos"},
    )

    assert response.status_code == 409

    gates = (await client.get(f"/avatars/{avatar['id']}/quality-gates")).json()
    identity_gate = next(g for g in gates if g["gate_name"] == "identity")
    assert identity_gate["status"] == "not_tested"
    assert identity_gate["approved_by"] is None

    history = (await client.get(f"/avatars/{avatar['id']}/history")).json()
    assert history == []

    unchanged_avatar = (await client.get(f"/avatars/{avatar['id']}")).json()
    assert unchanged_avatar["status"] == "draft"


async def test_approve_gate_atomic_rolls_back_everything_on_mid_transaction_failure(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fault-injection de verdade (P1-4): injeta uma falha no ÚLTIMO passo da transação
    atômica (`AvatarStateTransitionRecord`, escrito depois do UPDATE do avatar e do
    UPDATE do gate, todos na mesma sessão ainda não commitada) e prova que a falha
    reverte TUDO — o avatar continua DRAFT, o gate continua NOT_TESTED, nenhuma decisão
    foi persistida. Sem isso, um erro nesse ponto deixaria o gate em PASS com o avatar
    ainda em DRAFT (exatamente o estado parcial que P1-4 proíbe)."""
    import dhf_avatar_factory.repository as repo_module

    avatar = await _create_avatar(client, "gate-atomico-fault-injection")
    draft = (
        await client.post(f"/avatars/{avatar['id']}/identity-lock", json={"identity_spec": {}})
    ).json()
    await client.post(
        f"/avatars/{avatar['id']}/identity-lock/approve",
        json={"expected_version": draft["version"], "approved_by": "marcos"},
    )

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("falha injetada de propósito (fault-injection P1-4)")

    monkeypatch.setattr(repo_module, "AvatarStateTransitionRecord", _boom)

    with pytest.raises(RuntimeError, match="falha injetada"):
        await client.post(
            f"/avatars/{avatar['id']}/quality-gates/identity/approve",
            json={"expected_version": avatar["version"], "actor": "marcos"},
        )

    monkeypatch.undo()

    gates = (await client.get(f"/avatars/{avatar['id']}/quality-gates")).json()
    identity_gate = next(g for g in gates if g["gate_name"] == "identity")
    assert identity_gate["status"] == "not_tested"
    assert identity_gate["approved_by"] is None

    history = (await client.get(f"/avatars/{avatar['id']}/history")).json()
    assert history == []

    unchanged_avatar = (await client.get(f"/avatars/{avatar['id']}")).json()
    assert unchanged_avatar["status"] == "draft"
    assert unchanged_avatar["version"] == avatar["version"]


# --- P1-5: version lineage — evidência antiga nunca satisfaz a geração nova -----------------


async def test_new_identity_version_invalidates_stale_multiview_gate(
    client: httpx.AsyncClient, advance_to_identity_locked: AdvanceToIdentityLocked
) -> None:
    """Aprovar uma NOVA versão de identidade reseta gates que já estavam além de
    NOT_TESTED para a geração anterior — nenhuma evidência antiga (aqui, um multiview
    gate manualmente marcado PASS) sobrevive silenciosamente para a v2."""
    avatar = await _create_avatar(client, "lineage-multiview-stale")
    identity_locked = await advance_to_identity_locked(client, avatar)

    # Simula multiview já aprovado na geração 1 (rejeitamos para deixar status != not_tested
    # sem precisar completar 159 uploads apenas para este teste de lineage).
    reject_v1 = await client.post(
        f"/avatars/{avatar['id']}/quality-gates/multiview/reject",
        json={
            "expected_version": identity_locked["version"],
            "actor": "marcos",
            "reason": "teste de lineage",
        },
    )
    assert reject_v1.status_code == 200
    assert reject_v1.json()["avatar_version_group"] == 1

    # Nova versão de identidade: cria draft v2 e aprova.
    draft_v2 = (
        await client.post(
            f"/avatars/{avatar['id']}/identity-lock", json={"identity_spec": {}, "notes": "v2"}
        )
    ).json()
    assert draft_v2["identity_version"] == 2
    approve_v2 = await client.post(
        f"/avatars/{avatar['id']}/identity-lock/approve",
        json={"expected_version": draft_v2["version"], "approved_by": "marcos"},
    )
    assert approve_v2.status_code == 200

    gates_after = (await client.get(f"/avatars/{avatar['id']}/quality-gates")).json()
    multiview_gate = next(g for g in gates_after if g["gate_name"] == "multiview")
    assert multiview_gate["status"] == "not_tested"
    assert multiview_gate["avatar_version_group"] == 2


async def test_new_identity_version_does_not_touch_gates_on_first_approval(
    client: httpx.AsyncClient,
) -> None:
    """A primeira aprovação de identidade (v1, sem nenhum lock aprovado antes) nunca
    deve resetar nada — não há geração anterior para invalidar."""
    avatar = await _create_avatar(client, "lineage-primeira-aprovacao")
    draft = (
        await client.post(f"/avatars/{avatar['id']}/identity-lock", json={"identity_spec": {}})
    ).json()

    response = await client.post(
        f"/avatars/{avatar['id']}/identity-lock/approve",
        json={"expected_version": draft["version"], "approved_by": "marcos"},
    )

    assert response.status_code == 200
    # Nenhum gate foi tocado ainda — a lista fica vazia até o primeiro approve/list.
    gates = (await client.get(f"/avatars/{avatar['id']}/quality-gates")).json()
    assert all(g["avatar_version_group"] == 1 for g in gates)
