"""Requisitos de cada quality gate (seções 17, 22-25) — funções PURAS que decidem se um
gate pode ser aprovado agora, a partir do estado já carregado do avatar. Não fazem I/O;
`service.py` busca os dados via `repository.py` e delega a decisão para cá. Mantém a
regra de negócio testável sem precisar de Postgres."""

from __future__ import annotations

from dhf_avatar_factory.enums import (
    EXPRESSION_CATEGORIES,
    REQUIRED_ANGLES,
    SPECIALIZED_CATEGORIES,
    DerivedAssetStatus,
    IdentityLockStatus,
    QualityGateName,
    ReferenceAssetCategory,
)
from dhf_avatar_factory.models import DerivedAssetRecord, IdentityLockRecord, ReferenceAssetRecord
from dhf_avatar_factory.schemas import (
    AngleSlot,
    CategoryProgress,
    GateRequirementCheck,
    MultiviewCompleteness,
    MultiviewFamilyProgress,
)


def _latest_by_slot(
    assets: list[ReferenceAssetRecord],
) -> dict[tuple[str, int | None], ReferenceAssetRecord]:
    """Para cada (category, angle) mantém só o asset mais recente — uma recaptura supera
    a anterior para fins de completeness sem apagar a linha antiga do banco (histórico)."""
    latest: dict[tuple[str, int | None], ReferenceAssetRecord] = {}
    for asset in assets:
        key = (asset.category, asset.angle)
        current = latest.get(key)
        if current is None or asset.created_at > current.created_at:
            latest[key] = asset
    return latest


def _slot_state(asset: ReferenceAssetRecord | None) -> str:
    if asset is None:
        return "missing"
    return "approved" if asset.approved else asset.upload_state


def compute_multiview_completeness(assets: list[ReferenceAssetRecord]) -> MultiviewCompleteness:
    """Cálculo de progresso (seção 16) — cabeça/meio-corpo/corpo-inteiro em 36 posições
    cada, mais as listas de referências especializadas e expression master set."""
    latest = _latest_by_slot(assets)

    def family_progress(category: ReferenceAssetCategory) -> MultiviewFamilyProgress:
        slots: list[AngleSlot] = []
        done = 0
        for angle in REQUIRED_ANGLES:
            asset = latest.get((category.value, angle))
            slots.append(
                AngleSlot(
                    angle=angle, state=_slot_state(asset), asset_id=asset.id if asset else None
                )
            )
            if asset is not None and asset.approved:
                done += 1
        return MultiviewFamilyProgress(total=len(REQUIRED_ANGLES), done=done, slots=slots)

    def category_progress(categories: frozenset[ReferenceAssetCategory]) -> list[CategoryProgress]:
        progress = []
        for category in sorted(categories, key=lambda c: c.value):
            asset = latest.get((category.value, None))
            progress.append(
                CategoryProgress(
                    category=category,
                    state=_slot_state(asset),
                    asset_id=asset.id if asset else None,
                )
            )
        return progress

    head = family_progress(ReferenceAssetCategory.HEAD_360)
    half = family_progress(ReferenceAssetCategory.HALF_BODY_360)
    full = family_progress(ReferenceAssetCategory.FULL_BODY_360)
    specialized = category_progress(SPECIALIZED_CATEGORIES)
    expression = category_progress(EXPRESSION_CATEGORIES)

    specialized_done = sum(1 for item in specialized if item.state == "approved")
    expression_done = sum(1 for item in expression if item.state == "approved")
    open_rejections = sum(1 for asset in latest.values() if asset.upload_state == "rejected")

    all_required_approved = (
        head.done == head.total
        and half.done == half.total
        and full.done == full.total
        and specialized_done == len(specialized)
        and expression_done == len(expression)
        and open_rejections == 0
    )

    return MultiviewCompleteness(
        head_360=head,
        half_body_360=half,
        full_body_360=full,
        specialized=specialized,
        expression=expression,
        specialized_done=specialized_done,
        specialized_total=len(specialized),
        expression_done=expression_done,
        expression_total=len(expression),
        all_required_approved=all_required_approved,
        open_rejections=open_rejections,
    )


def check_identity_gate(identity_lock: IdentityLockRecord | None) -> GateRequirementCheck:
    missing: list[str] = []
    if identity_lock is None:
        missing.append("nenhum Identity Lock criado para este avatar")
    elif identity_lock.status != IdentityLockStatus.APPROVED:
        missing.append(f"Identity Lock está '{identity_lock.status}', precisa estar 'approved'")
    return GateRequirementCheck(
        gate_name=QualityGateName.IDENTITY, satisfied=not missing, missing=missing
    )


def check_multiview_gate(
    identity_lock: IdentityLockRecord | None, assets: list[ReferenceAssetRecord]
) -> GateRequirementCheck:
    """MULTIVIEW_APPROVED só acontece quando (seção 17): assets obrigatórios completos,
    QA críticos aprovados, nenhuma rejeição aberta, Identity Lock aprovado — a aprovação
    humana explícita em si é responsabilidade do chamador (o próprio ato de chamar este
    endpoint É a aprovação humana; ver `service.approve_gate`)."""
    missing: list[str] = []
    if not check_identity_gate(identity_lock).satisfied:
        missing.append("Identity Lock precisa estar approved antes do multiview")

    completeness = compute_multiview_completeness(assets)
    for label, family in (
        ("head_360", completeness.head_360),
        ("half_body_360", completeness.half_body_360),
        ("full_body_360", completeness.full_body_360),
    ):
        if family.done < family.total:
            missing.append(f"{label}: {family.done}/{family.total} ângulos aprovados")
    if completeness.specialized_done < completeness.specialized_total:
        missing.append(
            f"referências especializadas: "
            f"{completeness.specialized_done}/{completeness.specialized_total} aprovadas"
        )
    if completeness.expression_done < completeness.expression_total:
        missing.append(
            f"expression master set: "
            f"{completeness.expression_done}/{completeness.expression_total} aprovadas"
        )
    if completeness.open_rejections > 0:
        missing.append(
            f"{completeness.open_rejections} asset(s) rejeitado(s) ainda sem recaptura aprovada"
        )

    return GateRequirementCheck(
        gate_name=QualityGateName.MULTIVIEW, satisfied=not missing, missing=missing
    )


# Gates que dependem de artefato gerado por GPU (seção 39: nada disso é gerado ainda).
# None = depende de subsistema totalmente fora do escopo desta missão (voice/motion/master
# bank), nunca vai ficar satisfeito por este código sozinho.
_DERIVED_ASSET_REQUIREMENT: dict[QualityGateName, str | None] = {
    QualityGateName.MESH: "reconstructed_mesh",
    QualityGateName.RIG: "rig",
    QualityGateName.MATERIALS: "texture_albedo",
    QualityGateName.FACE: "facial_rig",
    QualityGateName.VOICE: None,
    QualityGateName.MOTION: None,
    QualityGateName.MASTER: None,
}


def check_gpu_dependent_gate(
    gate_name: QualityGateName, derived_assets: list[DerivedAssetRecord]
) -> GateRequirementCheck:
    """Mesh/Materials/Face/Voice/Motion/Master dependem de artefatos que só a RTX 4090
    real gera. Honesto por design: fica bloqueado até lá, nunca aprovado silenciosamente
    (seção 32 — Zero Mock)."""
    required_type = _DERIVED_ASSET_REQUIREMENT.get(gate_name)
    if required_type is None:
        return GateRequirementCheck(
            gate_name=gate_name,
            satisfied=False,
            missing=[f"gate '{gate_name}' depende de subsistema fora do escopo desta missão"],
            blocked_reason="PENDENTE_RTX_4090",
        )
    has_generated = any(
        asset.asset_type == required_type and asset.status == DerivedAssetStatus.GENERATED
        for asset in derived_assets
    )
    if not has_generated:
        return GateRequirementCheck(
            gate_name=gate_name,
            satisfied=False,
            missing=[f"nenhum DerivedAsset '{required_type}' com status GENERATED existe ainda"],
            blocked_reason="PENDENTE_RTX_4090",
        )
    return GateRequirementCheck(gate_name=gate_name, satisfied=True, missing=[])


def check_production_gate(other_gate_statuses: dict[QualityGateName, str]) -> GateRequirementCheck:
    """PRODUCTION_READY (seção 25) — enforcement final: reconfirma que todo gate anterior
    está com status PASS antes de liberar produção. Não inventa nenhum critério novo, só
    reverifica os já exigidos por cada etapa anterior."""
    required = [
        QualityGateName.IDENTITY,
        QualityGateName.MULTIVIEW,
        QualityGateName.MESH,
        QualityGateName.RIG,
        QualityGateName.MATERIALS,
        QualityGateName.FACE,
        QualityGateName.VOICE,
        QualityGateName.MOTION,
        QualityGateName.MASTER,
    ]
    missing = [
        f"gate '{gate}' está '{other_gate_statuses.get(gate, 'not_tested')}', precisa estar 'pass'"
        for gate in required
        if other_gate_statuses.get(gate) != "pass"
    ]
    return GateRequirementCheck(
        gate_name=QualityGateName.PRODUCTION, satisfied=not missing, missing=missing
    )
