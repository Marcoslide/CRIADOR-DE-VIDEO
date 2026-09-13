"""Acesso a dados do Avatar Factory Control Plane — só SQL/ORM aqui, nenhuma regra de
negócio (isso é `service.py`). Mesmo padrão de `dhf_avatars.repository`: cada função abre
e fecha sua própria sessão via `get_sessionmaker()`, sem depender do request scope do
FastAPI (repositórios também precisam funcionar fora de uma requisição, ex.: workers) —
EXCETO as funções `*_atomic` (P1-4), que deliberadamente fazem várias escritas dentro de
uma ÚNICA sessão/transação porque precisam de tudo-ou-nada: aprovar um gate nunca pode
deixar o gate em PASS com o avatar ainda no status antigo (ou vice-versa)."""

from __future__ import annotations

import uuid
from typing import Any

from dhf_avatars.models import AvatarRecord
from dhf_avatars.repository import AvatarNotFoundError, AvatarVersionConflictError
from dhf_shared.db import get_sessionmaker
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from dhf_avatar_factory.enums import DerivedAssetType, HardwareRequirement, JobContractType
from dhf_avatar_factory.models import (
    AvatarStateTransitionRecord,
    DerivedAssetRecord,
    IdentityLockRecord,
    JobContractRecord,
    QualityGateDecisionRecord,
    QualityGateRecord,
    ReferenceAssetRecord,
)


class IdentityLockNotFoundError(Exception):
    def __init__(self, lock_id: uuid.UUID) -> None:
        self.lock_id = lock_id
        super().__init__(f"identity lock {lock_id} não encontrado")


class IdentityLockVersionConflictError(Exception):
    def __init__(self, lock_id: uuid.UUID, expected_version: int) -> None:
        self.lock_id = lock_id
        self.expected_version = expected_version
        super().__init__(
            f"identity lock {lock_id} foi alterado depois da versão {expected_version}"
        )


class IdentityLockNotDraftError(Exception):
    """Só um lock em DRAFT pode ser editado ou aprovado — um já approved/superseded é
    imutável (seção 5: 'uma vez aprovado, nunca sobrescreve')."""


class NoIdentityLockForAvatarError(Exception):
    """Nenhum IdentityLock (nem draft) foi criado ainda para este avatar."""

    def __init__(self, avatar_id: uuid.UUID) -> None:
        self.avatar_id = avatar_id
        super().__init__(f"nenhum identity lock existe ainda para o avatar {avatar_id}")


class ReferenceAssetNotFoundError(Exception):
    def __init__(self, asset_id: uuid.UUID) -> None:
        self.asset_id = asset_id
        super().__init__(f"reference asset {asset_id} não encontrado")


class ReferenceAssetVersionConflictError(Exception):
    def __init__(self, asset_id: uuid.UUID, expected_version: int) -> None:
        self.asset_id = asset_id
        self.expected_version = expected_version
        super().__init__(
            f"reference asset {asset_id} foi alterado depois da versão {expected_version}"
        )


class QualityGateNotFoundError(Exception):
    def __init__(self, gate_id: uuid.UUID) -> None:
        self.gate_id = gate_id
        super().__init__(f"quality gate {gate_id} não encontrado")


class QualityGateVersionConflictError(Exception):
    def __init__(self, gate_id: uuid.UUID, expected_version: int) -> None:
        self.gate_id = gate_id
        self.expected_version = expected_version
        super().__init__(f"quality gate {gate_id} foi alterado depois da versão {expected_version}")


# --- Identity Lock ----------------------------------------------------------------------


async def get_current_identity_lock(avatar_id: uuid.UUID) -> IdentityLockRecord | None:
    """A linha de maior `identity_version` para este avatar — draft, approved ou
    superseded, o que houver de mais recente."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        return await session.scalar(
            select(IdentityLockRecord)
            .where(IdentityLockRecord.avatar_id == avatar_id)
            .order_by(IdentityLockRecord.identity_version.desc())
            .limit(1)
        )


async def get_latest_approved_identity_lock(avatar_id: uuid.UUID) -> IdentityLockRecord | None:
    """A identidade OFICIAL vigente do avatar (P1-5 — lineage): a versão de maior
    `identity_version` com status='approved'. Um draft mais novo em andamento NÃO muda
    isto até ser aprovado — enquanto isso, capturas/gates continuam contra a geração
    aprovada anterior, nunca contra um rascunho ainda não confirmado."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        return await session.scalar(
            select(IdentityLockRecord)
            .where(
                IdentityLockRecord.avatar_id == avatar_id,
                IdentityLockRecord.status == "approved",
            )
            .order_by(IdentityLockRecord.identity_version.desc())
            .limit(1)
        )


async def create_identity_lock_draft(
    avatar_id: uuid.UUID,
    *,
    identity_version: int,
    identity_spec: dict[str, Any],
    height_cm: float | None,
    notes: str | None,
    source_asset_ids: list[uuid.UUID],
) -> IdentityLockRecord:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        record = IdentityLockRecord(
            avatar_id=avatar_id,
            identity_version=identity_version,
            status="draft",
            identity_spec=identity_spec,
            height_cm=height_cm,
            notes=notes,
            source_asset_ids=source_asset_ids,
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record


async def update_identity_lock_draft(
    lock_id: uuid.UUID,
    *,
    identity_spec: dict[str, Any],
    height_cm: float | None,
    notes: str | None,
    source_asset_ids: list[uuid.UUID],
    expected_version: int,
) -> IdentityLockRecord:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        statement = (
            update(IdentityLockRecord)
            .where(
                IdentityLockRecord.id == lock_id,
                IdentityLockRecord.version == expected_version,
                IdentityLockRecord.status == "draft",
            )
            .values(
                identity_spec=identity_spec,
                height_cm=height_cm,
                notes=notes,
                source_asset_ids=source_asset_ids,
                version=IdentityLockRecord.version + 1,
                updated_at=func.now(),
            )
            .returning(IdentityLockRecord)
        )
        record = (await session.execute(statement)).scalar_one_or_none()
        if record is None:
            existing = await session.get(IdentityLockRecord, lock_id)
            if existing is None:
                raise IdentityLockNotFoundError(lock_id)
            if existing.status != "draft":
                raise IdentityLockNotDraftError
            raise IdentityLockVersionConflictError(lock_id, expected_version)
        await session.commit()
        return record


async def approve_identity_lock(
    lock_id: uuid.UUID, *, approved_by: str, expected_version: int
) -> tuple[IdentityLockRecord, int]:
    """Aprova o lock e, na mesma transação: (1) marca qualquer lock approved anterior
    deste avatar como superseded — nunca existe mais de um lock 'approved' simultâneo, e
    o anterior nunca é apagado nem sobrescrito, só rotulado; (2) se isto abre uma NOVA
    geração de identidade (P1-5), reseta para NOT_TESTED todo QualityGateRecord que ainda
    representava a geração anterior — nenhuma evidência antiga (gate PASS, DerivedAsset
    GENERATED) sobrevive silenciosamente para a nova versão. Devolve o lock e o
    `avatar_version_group` vigente após a operação."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        target = await session.get(IdentityLockRecord, lock_id)
        if target is None:
            raise IdentityLockNotFoundError(lock_id)
        if target.version != expected_version:
            raise IdentityLockVersionConflictError(lock_id, expected_version)
        if target.status != "draft":
            raise IdentityLockNotDraftError

        previous_approved = await session.scalar(
            select(IdentityLockRecord).where(
                IdentityLockRecord.avatar_id == target.avatar_id,
                IdentityLockRecord.status == "approved",
            )
        )
        previous_version_group = previous_approved.identity_version if previous_approved else 1

        await session.execute(
            update(IdentityLockRecord)
            .where(
                IdentityLockRecord.avatar_id == target.avatar_id,
                IdentityLockRecord.status == "approved",
            )
            .values(status="superseded", updated_at=func.now())
        )
        statement = (
            update(IdentityLockRecord)
            .where(IdentityLockRecord.id == lock_id, IdentityLockRecord.version == expected_version)
            .values(
                status="approved",
                approved_by=approved_by,
                approved_at=func.now(),
                version=IdentityLockRecord.version + 1,
                updated_at=func.now(),
            )
            .returning(IdentityLockRecord)
        )
        record = (await session.execute(statement)).scalar_one()
        new_version_group = record.identity_version

        if new_version_group > previous_version_group:
            # Nova geração de identidade: nenhum gate (inclusive 'identity', que precisa
            # ser re-aprovado explicitamente para esta versão) herda PASS da anterior.
            stale_gates = await session.scalars(
                select(QualityGateRecord).where(
                    QualityGateRecord.avatar_id == target.avatar_id,
                    QualityGateRecord.avatar_version_group < new_version_group,
                )
            )
            for gate in stale_gates:
                gate.status = "not_tested"
                gate.avatar_version_group = new_version_group
                gate.reason = None
                gate.evidence = None
                gate.approved_by = None
                gate.approved_at = None
                gate.version = gate.version + 1
                gate.updated_at = func.now()

        await session.commit()
        return record, new_version_group


# --- Reference Assets ---------------------------------------------------------------------


async def create_reference_asset(
    avatar_id: uuid.UUID,
    *,
    id: uuid.UUID,
    capture_version: int,
    category: str,
    angle: int | None,
    capture_type: str | None,
    side: str | None,
    orientation: str | None,
    source: str | None,
    storage_remote_path: str,
    storage_provider_id: str | None,
    checksum: str | None,
    mime_type: str | None,
    size_bytes: int | None,
    resolution_width: int | None,
    resolution_height: int | None,
    qa_status: str,
    qa_detail: dict[str, Any] | None,
) -> ReferenceAssetRecord:
    """`id` é gerado pelo chamador (`service.upload_reference_asset`) ANTES do upload ao
    Storage — P1-3: o path remoto do binário inclui esse mesmo UUID, então o INSERT aqui
    só confirma o vínculo, nunca gera um id novo que pudesse divergir do path já usado."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        record = ReferenceAssetRecord(
            id=id,
            avatar_id=avatar_id,
            capture_version=capture_version,
            category=category,
            angle=angle,
            capture_type=capture_type,
            side=side,
            orientation=orientation,
            source=source,
            storage_remote_path=storage_remote_path,
            storage_provider_id=storage_provider_id,
            checksum=checksum,
            mime_type=mime_type,
            size_bytes=size_bytes,
            resolution_width=resolution_width,
            resolution_height=resolution_height,
            upload_state="qa_pending"
            if qa_status in {"requires_human", "not_checked"}
            else "uploaded",
            qa_status=qa_status,
            qa_detail=qa_detail,
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record


async def list_reference_assets(
    avatar_id: uuid.UUID, *, category: str | None = None
) -> list[ReferenceAssetRecord]:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        statement = select(ReferenceAssetRecord).where(ReferenceAssetRecord.avatar_id == avatar_id)
        if category is not None:
            statement = statement.where(ReferenceAssetRecord.category == category)
        result = await session.scalars(statement.order_by(ReferenceAssetRecord.created_at.asc()))
        return list(result)


async def list_checksums(avatar_id: uuid.UUID) -> frozenset[str]:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        result = await session.scalars(
            select(ReferenceAssetRecord.checksum).where(
                ReferenceAssetRecord.avatar_id == avatar_id,
                ReferenceAssetRecord.checksum.is_not(None),
            )
        )
        return frozenset(result)


async def get_reference_asset(asset_id: uuid.UUID) -> ReferenceAssetRecord:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        record = await session.get(ReferenceAssetRecord, asset_id)
        if record is None:
            raise ReferenceAssetNotFoundError(asset_id)
        return record


async def review_reference_asset(
    asset_id: uuid.UUID,
    *,
    approved: bool,
    rejection_reason: str | None,
    rejection_notes: str | None,
    reviewed_by: str,
    expected_version: int,
) -> ReferenceAssetRecord:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        statement = (
            update(ReferenceAssetRecord)
            .where(
                ReferenceAssetRecord.id == asset_id,
                ReferenceAssetRecord.version == expected_version,
            )
            .values(
                approved=approved,
                upload_state="approved" if approved else "rejected",
                rejection_reason=rejection_reason,
                rejection_notes=rejection_notes,
                reviewed_by=reviewed_by,
                reviewed_at=func.now(),
                version=ReferenceAssetRecord.version + 1,
                updated_at=func.now(),
            )
            .returning(ReferenceAssetRecord)
        )
        record = (await session.execute(statement)).scalar_one_or_none()
        if record is None:
            exists = await session.scalar(
                select(ReferenceAssetRecord.id).where(ReferenceAssetRecord.id == asset_id)
            )
            if exists is None:
                raise ReferenceAssetNotFoundError(asset_id)
            raise ReferenceAssetVersionConflictError(asset_id, expected_version)
        await session.commit()
        return record


# --- Histórico de transição de status (append-only) ----------------------------------------


async def list_state_transitions(avatar_id: uuid.UUID) -> list[AvatarStateTransitionRecord]:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        result = await session.scalars(
            select(AvatarStateTransitionRecord)
            .where(AvatarStateTransitionRecord.avatar_id == avatar_id)
            .order_by(AvatarStateTransitionRecord.created_at.asc())
        )
        return list(result)


# --- Quality Gates -----------------------------------------------------------------------


async def get_gate(avatar_id: uuid.UUID, gate_name: str) -> QualityGateRecord | None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        return await session.scalar(
            select(QualityGateRecord).where(
                QualityGateRecord.avatar_id == avatar_id, QualityGateRecord.gate_name == gate_name
            )
        )


async def get_or_create_gate(
    avatar_id: uuid.UUID, gate_name: str, *, version_group: int, checklist: dict[str, str]
) -> QualityGateRecord:
    existing = await get_gate(avatar_id, gate_name)
    if existing is not None:
        return existing
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        record = QualityGateRecord(
            avatar_id=avatar_id,
            gate_name=gate_name,
            avatar_version_group=version_group,
            status="not_tested",
            checklist=checklist,
        )
        session.add(record)
        try:
            await session.commit()
        except IntegrityError:
            # corrida rara: outra requisição criou o gate entre o SELECT e o INSERT.
            await session.rollback()
            created = await get_gate(avatar_id, gate_name)
            if created is not None:
                return created
            raise
        await session.refresh(record)
        return record


async def list_gates(avatar_id: uuid.UUID) -> list[QualityGateRecord]:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        result = await session.scalars(
            select(QualityGateRecord).where(QualityGateRecord.avatar_id == avatar_id)
        )
        return list(result)


async def update_gate_status(
    gate_id: uuid.UUID,
    *,
    status: str,
    reason: str | None,
    evidence: dict[str, Any] | None,
    approved_by: str | None,
    expected_version: int,
) -> QualityGateRecord:
    """`approved_at` é sempre `func.now()` quando `approved_by` é informado (uma
    aprovação sempre carimba o momento em que aconteceu) e `None` caso contrário —
    nunca um timestamp calculado no lado do app, para não divergir do relógio do banco."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        statement = (
            update(QualityGateRecord)
            .where(QualityGateRecord.id == gate_id, QualityGateRecord.version == expected_version)
            .values(
                status=status,
                reason=reason,
                evidence=evidence,
                approved_by=approved_by,
                approved_at=func.now() if approved_by is not None else None,
                version=QualityGateRecord.version + 1,
                updated_at=func.now(),
            )
            .returning(QualityGateRecord)
        )
        record = (await session.execute(statement)).scalar_one_or_none()
        if record is None:
            exists = await session.scalar(
                select(QualityGateRecord.id).where(QualityGateRecord.id == gate_id)
            )
            if exists is None:
                raise QualityGateNotFoundError(gate_id)
            raise QualityGateVersionConflictError(gate_id, expected_version)
        await session.commit()
        return record


async def create_gate_decision(
    avatar_id: uuid.UUID,
    *,
    gate_name: str,
    action: str,
    previous_status: str,
    new_status: str,
    avatar_version_group: int,
    actor: str | None,
    reason: str | None,
    evidence: dict[str, Any] | None,
) -> QualityGateDecisionRecord:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        record = QualityGateDecisionRecord(
            avatar_id=avatar_id,
            gate_name=gate_name,
            action=action,
            previous_status=previous_status,
            new_status=new_status,
            avatar_version_group=avatar_version_group,
            actor=actor,
            reason=reason,
            evidence=evidence,
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record


# --- Transação atômica de aprovação/rejeição de gate (P1-4) --------------------------------


async def approve_gate_atomic(
    avatar_id: uuid.UUID,
    *,
    gate_name: str,
    current_status: str,
    target_status: str,
    expected_avatar_version: int,
    version_group: int,
    checklist: dict[str, str],
    reason: str | None,
    actor: str,
    evidence: dict[str, Any] | None,
) -> tuple[QualityGateRecord, AvatarStateTransitionRecord, AvatarRecord]:
    """Uma ÚNICA transação para: (1) travar/checar o avatar via optimistic lock e já
    avançar seu status; (2) obter-ou-criar o gate; (3) marcá-lo PASS; (4) registrar a
    decisão; (5) registrar a transição de status; (6) COMMIT único. Qualquer falha antes
    do commit (inclusive o avatar não ter mais a `expected_avatar_version` esperada)
    desfaz TUDO — nunca um gate fica PASS sem o avatar ter avançado, nem o contrário.

    O avatar é atualizado PRIMEIRO (antes de tocar no gate) deliberadamente: se outra
    requisição já mudou o avatar nesse meio-tempo, a transação inteira aborta aqui, antes
    de qualquer escrita em `avatar_quality_gates`/`avatar_quality_gate_decisions` — não
    existe cenário em que o gate seja escrito e o avatar não."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        avatar_statement = (
            update(AvatarRecord)
            .where(AvatarRecord.id == avatar_id, AvatarRecord.version == expected_avatar_version)
            .values(status=target_status, version=AvatarRecord.version + 1, updated_at=func.now())
            .returning(AvatarRecord)
        )
        avatar_record = (await session.execute(avatar_statement)).scalar_one_or_none()
        if avatar_record is None:
            exists = await session.scalar(
                select(AvatarRecord.id).where(AvatarRecord.id == avatar_id)
            )
            if exists is None:
                raise AvatarNotFoundError(avatar_id)
            raise AvatarVersionConflictError(avatar_id, expected_avatar_version)

        gate = await session.scalar(
            select(QualityGateRecord).where(
                QualityGateRecord.avatar_id == avatar_id, QualityGateRecord.gate_name == gate_name
            )
        )
        if gate is None:
            gate = QualityGateRecord(
                avatar_id=avatar_id,
                gate_name=gate_name,
                avatar_version_group=version_group,
                status="not_tested",
                checklist=checklist,
            )
            session.add(gate)
            await session.flush()

        previous_gate_status = gate.status
        gate.status = "pass"
        gate.avatar_version_group = version_group
        gate.reason = reason
        gate.evidence = evidence
        gate.approved_by = actor
        gate.approved_at = func.now()
        gate.version = gate.version + 1
        gate.updated_at = func.now()

        decision = QualityGateDecisionRecord(
            avatar_id=avatar_id,
            gate_name=gate_name,
            action="approve",
            previous_status=previous_gate_status,
            new_status="pass",
            avatar_version_group=version_group,
            actor=actor,
            reason=reason,
            evidence=evidence,
        )
        session.add(decision)

        transition = AvatarStateTransitionRecord(
            avatar_id=avatar_id,
            from_status=current_status,
            to_status=target_status,
            actor=actor,
            reason=reason,
            evidence=evidence,
            quality_gate=gate_name,
            avatar_version=avatar_record.version,
        )
        session.add(transition)

        await session.commit()
        await session.refresh(gate)
        await session.refresh(transition)
        await session.refresh(avatar_record)
        return gate, transition, avatar_record


async def reject_gate_atomic(
    avatar_id: uuid.UUID,
    *,
    gate_name: str,
    version_group: int,
    checklist: dict[str, str],
    reason: str | None,
    actor: str,
    evidence: dict[str, Any] | None,
) -> QualityGateRecord:
    """Mesma filosofia atômica do approve (P1-4) para a operação correlacionada de
    rejeitar: update do gate + insert da decisão num commit só."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        gate = await session.scalar(
            select(QualityGateRecord).where(
                QualityGateRecord.avatar_id == avatar_id, QualityGateRecord.gate_name == gate_name
            )
        )
        if gate is None:
            gate = QualityGateRecord(
                avatar_id=avatar_id,
                gate_name=gate_name,
                avatar_version_group=version_group,
                status="not_tested",
                checklist=checklist,
            )
            session.add(gate)
            await session.flush()

        previous_gate_status = gate.status
        gate.status = "fail"
        gate.reason = reason
        gate.evidence = evidence
        gate.approved_by = None
        gate.approved_at = None
        gate.version = gate.version + 1
        gate.updated_at = func.now()

        decision = QualityGateDecisionRecord(
            avatar_id=avatar_id,
            gate_name=gate_name,
            action="reject",
            previous_status=previous_gate_status,
            new_status="fail",
            avatar_version_group=gate.avatar_version_group,
            actor=actor,
            reason=reason,
            evidence=evidence,
        )
        session.add(decision)

        await session.commit()
        await session.refresh(gate)
        return gate


# --- Derived Assets / Job Contracts (placeholders, seções 19-21) ---------------------------


async def list_derived_assets(
    avatar_id: uuid.UUID, *, version_group: int | None = None
) -> list[DerivedAssetRecord]:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        statement = select(DerivedAssetRecord).where(DerivedAssetRecord.avatar_id == avatar_id)
        if version_group is not None:
            statement = statement.where(DerivedAssetRecord.avatar_version_group == version_group)
        result = await session.scalars(statement)
        return list(result)


async def ensure_derived_asset_placeholders(
    avatar_id: uuid.UUID, *, avatar_version_group: int
) -> list[DerivedAssetRecord]:
    """Garante uma linha NOT_GENERATED por tipo PARA A GERAÇÃO ATUAL (seção 19, P1-5) —
    idempotente por version_group; nunca apaga nem reaproveita linhas de uma geração
    anterior (essas continuam existindo como histórico, mas não contam para o gate atual,
    já que `check_gpu_dependent_gate` só recebe as do `avatar_version_group` vigente)."""
    existing = await list_derived_assets(avatar_id, version_group=avatar_version_group)
    if existing:
        return existing
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        records = [
            DerivedAssetRecord(
                avatar_id=avatar_id,
                asset_type=asset_type.value,
                avatar_version_group=avatar_version_group,
                status="not_generated",
            )
            for asset_type in DerivedAssetType
        ]
        session.add_all(records)
        await session.commit()
        for record in records:
            await session.refresh(record)
        return records


_JOB_HARDWARE: dict[JobContractType, HardwareRequirement] = {
    JobContractType.MULTIVIEW_RECONSTRUCTION: HardwareRequirement.RTX_4090,
    JobContractType.MESH_REFINEMENT: HardwareRequirement.RTX_4090,
    JobContractType.TEXTURE_GENERATION: HardwareRequirement.RTX_4090,
    JobContractType.METAHUMAN_CONVERSION: HardwareRequirement.RTX_4090,
    JobContractType.FACIAL_RIG: HardwareRequirement.RTX_4090,
    JobContractType.GROOM_BUILD: HardwareRequirement.RTX_CLASS,
    JobContractType.MATERIAL_BUILD: HardwareRequirement.RTX_CLASS,
    JobContractType.QUALITY_RENDER: HardwareRequirement.RTX_4090,
}


async def list_job_contracts(avatar_id: uuid.UUID) -> list[JobContractRecord]:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        result = await session.scalars(
            select(JobContractRecord).where(JobContractRecord.avatar_id == avatar_id)
        )
        return list(result)


async def ensure_default_job_contracts(
    avatar_id: uuid.UUID, *, input_version: int
) -> list[JobContractRecord]:
    """Garante um contrato por tipo de job (seção 20) — `status='blocked'` porque nenhum
    executor real existe sem a RTX 4090 (seção 21: contrato, nunca execução)."""
    existing = await list_job_contracts(avatar_id)
    if existing:
        return existing
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        records = [
            JobContractRecord(
                avatar_id=avatar_id,
                job_type=job_type.value,
                input_version=input_version,
                required_assets=[],
                output_contract={},
                hardware_requirement=hardware.value,
                status="blocked",
                error="bloqueado: nenhum executor de GPU disponível (V1 é só contrato)",
            )
            for job_type, hardware in _JOB_HARDWARE.items()
        ]
        session.add_all(records)
        await session.commit()
        for record in records:
            await session.refresh(record)
        return records
