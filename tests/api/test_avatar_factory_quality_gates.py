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
        UploadFullMultiviewSet,
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


# --- P1-6/P1-6b/P1-7/P1-8/P1-9/P2 — hardening antes da auditoria independente ---------------
#
# Os 8 cenários adversariais abaixo são os exigidos explicitamente para este round: cada
# um prova, com Postgres real (nunca mock), que a janela de corrida ou o estado
# "impossível" correspondente NÃO existe mais.


async def test_concurrent_evidence_rejection_and_gate_approval_never_leave_stale_pass(
    client: httpx.AsyncClient,
    advance_to_identity_locked: AdvanceToIdentityLocked,
    upload_and_approve_full_multiview_set: UploadFullMultiviewSet,
    fake_storage_provider: FakeStorageProvider,
) -> None:
    """Cenário adversarial #1 (P1-6 — TOCTOU): evidência 100% satisfeita, mas uma
    rejeição concorrente altera essa evidência exatamente no momento em que o approve do
    gate roda. Antes do P1-6, `service.approve_gate` lia `satisfied=True` FORA da
    transação e confiava nesse booleano pré-computado; hoje a mesma transação que decide
    é a que locka e lê a evidência (`repository.approve_gate_atomic` ->
    `_check_gate_requirements_locked`), e a rejeição concorrente também locka o avatar
    primeiro (mesma ordem universal de lock — ver `repository.py`). Não existe mais
    entrelaçamento parcial possível: ou o approve termina 100% antes da rejeição começar
    (e a rejeição então acha o gate PASS e invalida em cascata — P1-6b), ou a rejeição
    termina primeiro e o approve enxerga a evidência já insuficiente e falha. Em NENHUM
    caso o gate fica permanentemente 'pass' com evidência atual insuficiente."""
    import asyncio

    avatar = await _create_avatar(client, "toctou-corrida-evidencia")
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
    await upload_and_approve_full_multiview_set(client, avatar["id"])

    references = (
        await client.get(f"/avatars/{avatar['id']}/references", params={"category": "head_360"})
    ).json()
    target = next(r for r in references if r["angle"] == 0)

    reject_response, approve_response = await asyncio.gather(
        client.post(
            f"/avatars/{avatar['id']}/references/{target['id']}/reject",
            json={
                "expected_version": target["version"],
                "reason": "identity_drift",
                "reviewed_by": "marcos",
            },
        ),
        client.post(
            f"/avatars/{avatar['id']}/quality-gates/multiview/approve",
            json={"expected_version": in_progress["version"], "actor": "marcos"},
        ),
    )

    assert reject_response.status_code == 200
    assert approve_response.status_code in (200, 409)

    final_gate = next(
        g
        for g in (await client.get(f"/avatars/{avatar['id']}/quality-gates")).json()
        if g["gate_name"] == "multiview"
    )
    # A rejeição é permanente nesse teste (sem recaptura) — não importa a ordem em que as
    # duas operações concorrentes foram serializadas pelo Postgres, o gate nunca pode
    # terminar 'pass' com evidência atual insuficiente.
    assert final_gate["status"] != "pass"

    final_avatar = (await client.get(f"/avatars/{avatar['id']}")).json()
    assert final_avatar["status"] == "multiview_in_progress"


async def test_rejecting_evidence_after_multiview_pass_cascades_invalidation(
    client: httpx.AsyncClient,
    advance_to_identity_locked: AdvanceToIdentityLocked,
    complete_full_multiview_and_approve: CompleteFullMultiview,
    fake_storage_provider: FakeStorageProvider,
) -> None:
    """Cenário adversarial #2 (P1-6b — opção B, evidência mutável): um reference asset
    que era evidência de um MULTIVIEW já PASS sendo rejeitado DEPOIS invalida o gate e
    todo downstream, e reposiciona o avatar — nunca sobrevive um estado "gate caiu,
    avatar continua MULTIVIEW_APPROVED"."""
    avatar = await _create_avatar(client, "cascata-multiview-pass")
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
    await complete_full_multiview_and_approve(client, in_progress)

    gates_before = (await client.get(f"/avatars/{avatar['id']}/quality-gates")).json()
    assert next(g for g in gates_before if g["gate_name"] == "multiview")["status"] == "pass"

    references = (
        await client.get(f"/avatars/{avatar['id']}/references", params={"category": "head_360"})
    ).json()
    target = next(r for r in references if r["angle"] == 0)

    rejection = await client.post(
        f"/avatars/{avatar['id']}/references/{target['id']}/reject",
        json={
            "expected_version": target["version"],
            "reason": "identity_drift",
            "reviewed_by": "marcos",
        },
    )
    assert rejection.status_code == 200

    gates_after = (await client.get(f"/avatars/{avatar['id']}/quality-gates")).json()
    multiview_after = next(g for g in gates_after if g["gate_name"] == "multiview")
    assert multiview_after["status"] == "fail"

    reset_avatar = (await client.get(f"/avatars/{avatar['id']}")).json()
    assert reset_avatar["status"] == "multiview_in_progress"

    history = (await client.get(f"/avatars/{avatar['id']}/history")).json()
    cascade_transitions = [t for t in history if "invalidação em cascata" in (t["reason"] or "")]
    assert len(cascade_transitions) == 1
    assert cascade_transitions[0]["from_status"] == "multiview_approved"
    assert cascade_transitions[0]["to_status"] == "multiview_in_progress"
    assert cascade_transitions[0]["quality_gate"] == "multiview"


async def test_identity_v2_approval_resets_status_away_from_production_ready(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    advance_to_identity_locked: AdvanceToIdentityLocked,
    complete_full_multiview_and_approve: CompleteFullMultiview,
    fake_storage_provider: FakeStorageProvider,
) -> None:
    """Cenário adversarial #3 (P1-7 + readiness fail-closed): um avatar genuinamente
    PRODUCTION_READY (os 9 gates obrigatórios 'pass' de verdade) não pode sobreviver como
    PRODUCTION_READY depois que uma NOVA identidade é aprovada — nem `AvatarRecord.status`
    nem `readiness.production_ready`. Mesh/rig/materials/face/voice/motion/master nunca
    passam de verdade nesta V1 (seção 39, Zero Mock) — para isolar e testar só o
    MECANISMO de reset (não fingir que a GPU existe), só o booleano de satisfação de
    `check_gpu_dependent_gate` é estubado aqui; toda a transação de aprovação (lock,
    escrita, avanço de status) roda de verdade contra o Postgres."""
    import dhf_avatar_factory.gate_requirements as gate_requirements_module
    from dhf_avatar_factory.schemas import GateRequirementCheck

    avatar = await _create_avatar(client, "producao-reset-identity-v2")
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
    current = await complete_full_multiview_and_approve(client, in_progress)

    def _always_satisfied(gate_name, derived_assets):  # noqa: ANN001, ARG001
        return GateRequirementCheck(gate_name=gate_name, satisfied=True, missing=[])

    monkeypatch.setattr(gate_requirements_module, "check_gpu_dependent_gate", _always_satisfied)

    current = (
        await client.patch(
            f"/avatars/{avatar['id']}",
            json={"status": "mesh_in_progress", "expected_version": current["version"]},
        )
    ).json()
    for gate in ("mesh", "rig", "materials", "face", "voice", "motion", "master", "production"):
        response = await client.post(
            f"/avatars/{avatar['id']}/quality-gates/{gate}/approve",
            json={"expected_version": current["version"], "actor": "marcos"},
        )
        assert response.status_code == 200, response.text
        current = (await client.get(f"/avatars/{avatar['id']}")).json()

    assert current["status"] == "production_ready"
    readiness = (await client.get(f"/avatars/{avatar['id']}/readiness")).json()
    assert readiness["production_ready"] is True

    monkeypatch.undo()  # a aprovação de identidade v2 abaixo não deve depender do estub

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

    reset_avatar = (await client.get(f"/avatars/{avatar['id']}")).json()
    assert reset_avatar["status"] == "draft"

    reset_readiness = (await client.get(f"/avatars/{avatar['id']}/readiness")).json()
    assert reset_readiness["production_ready"] is False
    assert reset_readiness["status"] == "draft"
    assert set(reset_readiness["missing"]) == {
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


async def test_identity_v2_never_silently_reuses_v1_job_contracts(
    client: httpx.AsyncClient, advance_to_identity_locked: AdvanceToIdentityLocked
) -> None:
    """Cenário adversarial #4 (P1-8 — lineage de job contract): trocar de geração de
    identidade nunca reaproveita silenciosamente os job contracts de uma geração
    anterior — um conjunto NOVO é criado para v2, e o conjunto de v1 permanece intacto
    como histórico (nunca apagado, nunca reescrito)."""
    import dhf_avatar_factory.repository as repo_module

    avatar = await _create_avatar(client, "job-contracts-lineage")
    await advance_to_identity_locked(client, avatar)

    contracts_v1 = (await client.get(f"/avatars/{avatar['id']}/job-contracts")).json()
    assert len(contracts_v1) == 8
    assert all(c["avatar_version_group"] == 1 for c in contracts_v1)
    v1_ids = {c["id"] for c in contracts_v1}

    draft_v2 = (
        await client.post(
            f"/avatars/{avatar['id']}/identity-lock", json={"identity_spec": {}, "notes": "v2"}
        )
    ).json()
    approve_v2 = await client.post(
        f"/avatars/{avatar['id']}/identity-lock/approve",
        json={"expected_version": draft_v2["version"], "approved_by": "marcos"},
    )
    assert approve_v2.status_code == 200

    contracts_now = (await client.get(f"/avatars/{avatar['id']}/job-contracts")).json()
    assert len(contracts_now) == 8
    assert all(c["avatar_version_group"] == 2 for c in contracts_now)
    v2_ids = {c["id"] for c in contracts_now}
    assert v1_ids.isdisjoint(v2_ids)  # v2 nunca é a MESMA linha reaproveitada de v1

    stale_v1_records = await repo_module.list_job_contracts(
        uuid.UUID(avatar["id"]), version_group=1
    )
    assert {str(r.id) for r in stale_v1_records} == v1_ids  # v1 continua intacto
    assert all(r.avatar_version_group == 1 for r in stale_v1_records)
    assert all(r.status == "blocked" for r in stale_v1_records)  # nunca reescrito


async def test_concurrent_identity_v2_draft_creation_never_duplicates(
    client: httpx.AsyncClient, advance_to_identity_locked: AdvanceToIdentityLocked
) -> None:
    """Cenário adversarial #5 (P1-9 — concorrência real): duas requisições concorrentes
    criando o primeiro draft de identity_version=2 para o MESMO avatar nunca resultam em
    duas linhas — o lock do avatar serializa a corrida e, mesmo que o lock falhasse por
    algum motivo, a UNIQUE constraint do banco (migration 0006) garante isso de
    qualquer forma. Não confiamos só no código Python: contamos as linhas direto no
    banco."""
    import asyncio

    from dhf_avatar_factory.models import IdentityLockRecord
    from dhf_shared.db import get_sessionmaker
    from sqlalchemy import func, select

    avatar = await _create_avatar(client, "identity-v2-corrida")
    await advance_to_identity_locked(client, avatar)  # v1 approved

    payload = {"identity_spec": {}, "notes": "corrida v2"}
    responses = await asyncio.gather(
        client.post(f"/avatars/{avatar['id']}/identity-lock", json=payload),
        client.post(f"/avatars/{avatar['id']}/identity-lock", json=payload),
    )

    assert all(r.status_code in (201, 409) for r in responses)
    assert any(r.status_code == 201 for r in responses)

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(IdentityLockRecord)
            .where(
                IdentityLockRecord.avatar_id == uuid.UUID(avatar["id"]),
                IdentityLockRecord.identity_version == 2,
            )
        )
    assert count == 1


async def test_concurrent_derived_asset_placeholder_creation_never_duplicates(
    client: httpx.AsyncClient,
) -> None:
    """Cenário adversarial #6 (P1-9): duas requisições concorrentes pedindo os
    placeholders de DerivedAsset da mesma geração pela primeira vez nunca duplicam —
    deve existir exatamente 1 linha por (avatar, geração, tipo), nunca 2, confirmado
    direto no banco (não só pela resposta da API)."""
    import asyncio

    from dhf_avatar_factory.models import DerivedAssetRecord
    from dhf_shared.db import get_sessionmaker
    from sqlalchemy import func, select

    avatar = await _create_avatar(client, "derived-assets-corrida")

    responses = await asyncio.gather(
        client.get(f"/avatars/{avatar['id']}/derived-assets"),
        client.get(f"/avatars/{avatar['id']}/derived-assets"),
    )
    for response in responses:
        assert response.status_code == 200
        assert len(response.json()) == 12  # um por DerivedAssetType

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(DerivedAssetRecord)
            .where(
                DerivedAssetRecord.avatar_id == uuid.UUID(avatar["id"]),
                DerivedAssetRecord.avatar_version_group == 1,
            )
        )
    assert count == 12


async def test_concurrent_job_contract_placeholder_creation_never_duplicates(
    client: httpx.AsyncClient,
) -> None:
    """Cenário adversarial #7 (P1-9): mesma garantia do teste anterior, agora para
    JobContract — duas requisições concorrentes pedindo os contratos padrão da mesma
    geração pela primeira vez nunca duplicam."""
    import asyncio

    from dhf_avatar_factory.models import JobContractRecord
    from dhf_shared.db import get_sessionmaker
    from sqlalchemy import func, select

    avatar = await _create_avatar(client, "job-contracts-corrida")

    responses = await asyncio.gather(
        client.get(f"/avatars/{avatar['id']}/job-contracts"),
        client.get(f"/avatars/{avatar['id']}/job-contracts"),
    )
    for response in responses:
        assert response.status_code == 200
        assert len(response.json()) == 8  # um por JobContractType

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(JobContractRecord)
            .where(
                JobContractRecord.avatar_id == uuid.UUID(avatar["id"]),
                JobContractRecord.avatar_version_group == 1,
            )
        )
    assert count == 8


async def test_reference_content_proxy_cleans_up_tempfile_on_storage_download_failure(
    client: httpx.AsyncClient,
    fake_storage_provider: FakeStorageProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cenário adversarial #8 (P2 — cleanup de tempfile): se o download do Storage
    falhar, o tempfile já criado por `tempfile.mkstemp` não pode vazar — o content proxy
    é chamado a cada carregamento do viewer 360, e um Storage instável (timeout, 5xx,
    credencial expirada) não pode ir enchendo o disco a cada tentativa."""
    import io
    from pathlib import Path

    from PIL import Image

    avatar = await _create_avatar(client, "content-proxy-cleanup")
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), color=(120, 120, 120)).save(buffer, format="PNG")
    uploaded = (
        await client.post(
            f"/avatars/{avatar['id']}/references",
            data={"category": "face_front_neutral"},
            files={"file": ("ref.png", buffer.getvalue(), "image/png")},
        )
    ).json()

    created_paths: list[str] = []

    async def _boom_download(remote_path: str, local_path: str) -> None:
        created_paths.append(local_path)
        raise RuntimeError("falha simulada de download do Storage")

    monkeypatch.setattr(fake_storage_provider, "download", _boom_download)

    with pytest.raises(RuntimeError, match="falha simulada"):
        await client.get(f"/avatars/{avatar['id']}/references/{uploaded['id']}/content")

    assert len(created_paths) == 1
    assert not Path(created_paths[0]).exists()
