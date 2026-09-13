"""Testes unitários dos requisitos de quality gate (seções 17, 22-25) — sem DB: os
registros ORM são construídos em memória (nunca adicionados a uma sessão), só para
exercitar os atributos que `gate_requirements.py` lê. Cobre exatamente as fronteiras que
a correção original pedia: nada é aprovado sem evidência real."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from dhf_avatar_factory.enums import (
    EXPRESSION_CATEGORIES,
    REQUIRED_ANGLES,
    SPECIALIZED_CATEGORIES,
    IdentityLockStatus,
    QualityGateName,
    QualityGateStatus,
    ReferenceAssetCategory,
)
from dhf_avatar_factory.gate_requirements import (
    check_gpu_dependent_gate,
    check_identity_gate,
    check_multiview_gate,
    check_production_gate,
    compute_multiview_completeness,
)
from dhf_avatar_factory.models import DerivedAssetRecord, IdentityLockRecord, ReferenceAssetRecord


def _asset(
    category: ReferenceAssetCategory,
    *,
    angle: int | None = None,
    approved: bool = True,
    upload_state: str = "approved",
    created_at: datetime | None = None,
) -> ReferenceAssetRecord:
    return ReferenceAssetRecord(
        id=uuid.uuid4(),
        avatar_id=uuid.uuid4(),
        capture_version=1,
        category=category.value,
        angle=angle,
        approved=approved,
        upload_state=upload_state,
        created_at=created_at or datetime.now(UTC),
    )


def _identity_lock(status: IdentityLockStatus) -> IdentityLockRecord:
    return IdentityLockRecord(
        id=uuid.uuid4(), avatar_id=uuid.uuid4(), identity_version=1, status=status.value
    )


def _full_multiview_assets() -> list[ReferenceAssetRecord]:
    assets = []
    for category in (
        ReferenceAssetCategory.HEAD_360,
        ReferenceAssetCategory.HALF_BODY_360,
        ReferenceAssetCategory.FULL_BODY_360,
    ):
        for angle in REQUIRED_ANGLES:
            assets.append(_asset(category, angle=angle))
    for category in SPECIALIZED_CATEGORIES:
        assets.append(_asset(category))
    for category in EXPRESSION_CATEGORIES:
        assets.append(_asset(category))
    return assets


class TestMultiviewCompleteness:
    def test_empty_assets_reports_everything_missing(self) -> None:
        completeness = compute_multiview_completeness([])

        assert completeness.head_360.total == 36
        assert completeness.head_360.done == 0
        assert all(slot.state == "missing" for slot in completeness.head_360.slots)
        assert completeness.specialized_total == len(SPECIALIZED_CATEGORIES)
        assert completeness.expression_total == len(EXPRESSION_CATEGORIES)
        assert completeness.all_required_approved is False

    def test_fully_approved_set_marks_all_required_approved(self) -> None:
        completeness = compute_multiview_completeness(_full_multiview_assets())

        assert completeness.head_360.done == 36
        assert completeness.half_body_360.done == 36
        assert completeness.full_body_360.done == 36
        assert completeness.specialized_done == completeness.specialized_total
        assert completeness.expression_done == completeness.expression_total
        assert completeness.open_rejections == 0
        assert completeness.all_required_approved is True

    def test_one_rejected_asset_blocks_completeness_and_is_counted(self) -> None:
        assets = _full_multiview_assets()
        assets[0] = _asset(
            ReferenceAssetCategory.HEAD_360, angle=0, approved=False, upload_state="rejected"
        )

        completeness = compute_multiview_completeness(assets)

        assert completeness.open_rejections == 1
        assert completeness.all_required_approved is False

    def test_recapture_supersedes_older_asset_at_same_slot(self) -> None:
        old = _asset(
            ReferenceAssetCategory.HEAD_360,
            angle=0,
            approved=False,
            upload_state="rejected",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        new = _asset(
            ReferenceAssetCategory.HEAD_360,
            angle=0,
            approved=True,
            upload_state="approved",
            created_at=datetime(2026, 1, 2, tzinfo=UTC),
        )

        completeness = compute_multiview_completeness([old, new])

        assert completeness.open_rejections == 0  # a rejeição antiga não conta mais
        head_slot_zero = next(slot for slot in completeness.head_360.slots if slot.angle == 0)
        assert head_slot_zero.state == "approved"
        assert head_slot_zero.asset_id == new.id


class TestIdentityGate:
    def test_no_lock_is_not_satisfied(self) -> None:
        result = check_identity_gate(None)
        assert result.satisfied is False
        assert result.gate_name == QualityGateName.IDENTITY

    def test_draft_lock_is_not_satisfied(self) -> None:
        result = check_identity_gate(_identity_lock(IdentityLockStatus.DRAFT))
        assert result.satisfied is False

    def test_approved_lock_is_satisfied(self) -> None:
        result = check_identity_gate(_identity_lock(IdentityLockStatus.APPROVED))
        assert result.satisfied is True
        assert result.missing == []


class TestMultiviewGate:
    def test_blocked_without_identity_lock(self) -> None:
        result = check_multiview_gate(None, _full_multiview_assets())
        assert result.satisfied is False
        assert any("Identity Lock" in reason for reason in result.missing)

    def test_blocked_with_incomplete_assets(self) -> None:
        lock = _identity_lock(IdentityLockStatus.APPROVED)
        result = check_multiview_gate(lock, [])
        assert result.satisfied is False
        assert len(result.missing) >= 5  # head/half/full/specialized/expression todos faltando

    def test_satisfied_with_approved_identity_and_complete_assets(self) -> None:
        lock = _identity_lock(IdentityLockStatus.APPROVED)
        result = check_multiview_gate(lock, _full_multiview_assets())
        assert result.satisfied is True
        assert result.missing == []


class TestGpuDependentGates:
    def test_mesh_gate_blocked_without_any_derived_asset(self) -> None:
        result = check_gpu_dependent_gate(QualityGateName.MESH, [])
        assert result.satisfied is False
        assert result.blocked_reason == "PENDENTE_RTX_4090"

    def test_mesh_gate_blocked_while_derived_asset_not_generated(self) -> None:
        derived = DerivedAssetRecord(
            id=uuid.uuid4(),
            avatar_id=uuid.uuid4(),
            asset_type="reconstructed_mesh",
            status="queued",
        )
        result = check_gpu_dependent_gate(QualityGateName.MESH, [derived])
        assert result.satisfied is False

    def test_mesh_gate_satisfied_once_derived_asset_is_generated(self) -> None:
        derived = DerivedAssetRecord(
            id=uuid.uuid4(),
            avatar_id=uuid.uuid4(),
            asset_type="reconstructed_mesh",
            status="generated",
        )
        result = check_gpu_dependent_gate(QualityGateName.MESH, [derived])
        assert result.satisfied is True

    def test_voice_and_motion_gates_are_always_blocked_out_of_scope(self) -> None:
        for gate_name in (QualityGateName.VOICE, QualityGateName.MOTION, QualityGateName.MASTER):
            result = check_gpu_dependent_gate(gate_name, [])
            assert result.satisfied is False
            assert result.blocked_reason == "PENDENTE_RTX_4090"


class TestProductionGate:
    def test_blocked_unless_every_other_gate_passed(self) -> None:
        statuses = {
            name: QualityGateStatus.PASS
            for name in QualityGateName
            if name != QualityGateName.MASTER
        }
        statuses[QualityGateName.MASTER] = QualityGateStatus.NOT_TESTED

        result = check_production_gate(statuses)

        assert result.satisfied is False
        assert any("master" in reason for reason in result.missing)

    def test_satisfied_once_every_gate_passed(self) -> None:
        statuses = dict.fromkeys(QualityGateName, QualityGateStatus.PASS)

        result = check_production_gate(statuses)

        assert result.satisfied is True
        assert result.missing == []
