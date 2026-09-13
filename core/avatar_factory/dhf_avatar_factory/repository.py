"""Acesso a dados do Avatar Factory Control Plane. Mesmo padrão de `dhf_avatars.repository`:
cada função abre e fecha sua própria sessão via `get_sessionmaker()`, sem depender do
request scope do FastAPI — EXCETO as funções `*_atomic` (P1-4/P1-6/P1-7/P1-9), que
deliberadamente fazem várias leituras e escritas dentro de uma ÚNICA sessão/transação.

Duas garantias que só o repository (dono da transação) pode dar, por isso vive aqui em
vez de `service.py`:

- P1-6 (TOCTOU): a evidência que decide se um gate pode ser aprovado é lida com
  `SELECT ... FOR UPDATE` DENTRO da mesma transação que escreve o resultado — nunca uma
  leitura solta antes, seguida de uma escrita que já não reflete mais aquela leitura.
  Por isso este módulo importa `gate_requirements` (funções puras de decisão): só o
  repository controla quando o lock é tomado e quando a decisão é avaliada.
- P1-9 (concorrência real): além do optimistic locking (coluna `version`) já usado em
  todo update pontual, as operações que CRIAM linhas nunca vistas antes (novo Identity
  Lock, placeholders de DerivedAsset/JobContract) tomam um `SELECT ... FOR UPDATE` na
  linha do `AvatarRecord` primeiro — como não há linha própria pra lockar antes dela
  existir, lockar o avatar serializa toda criação relacionada a ele. As UNIQUE
  constraints do banco (migration 0006) são a garantia de último recurso caso algum
  caminho de código esqueça de lockar.
"""

from __future__ import annotations

import uuid
from typing import Any

from dhf_avatars.models import AvatarRecord
from dhf_avatars.repository import AvatarNotFoundError, AvatarVersionConflictError
from dhf_avatars.schemas import ALLOWED_STATUS_TRANSITIONS, AvatarStatus
from dhf_shared.db import get_sessionmaker
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from dhf_avatar_factory import gate_requirements
from dhf_avatar_factory.enums import (
    GATE_TARGET_STATUS,
    DerivedAssetType,
    HardwareRequirement,
    JobContractType,
    QualityGateName,
    downstream_gates_of,
    predecessor_status_of,
)
from dhf_avatar_factory.models import (
    AvatarStateTransitionRecord,
    DerivedAssetRecord,
    IdentityLockRecord,
    JobContractRecord,
    QualityGateDecisionRecord,
    QualityGateRecord,
    ReferenceAssetRecord,
)
from dhf_avatar_factory.schemas import GateRequirementCheck

_STATUS_ORDER: list[AvatarStatus] = list(AvatarStatus)


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


class IdentityLockConcurrentCreationError(Exception):
    """P1-9: duas requisições concorrentes tentaram criar a mesma `identity_version` pela
    primeira vez — a UNIQUE constraint do banco recusou a segunda. Resposta correta do
    cliente é tentar de novo (vai ver o draft que a outra requisição já criou)."""

    def __init__(self, avatar_id: uuid.UUID, identity_version: int) -> None:
        self.avatar_id = avatar_id
        self.identity_version = identity_version
        super().__init__(
            f"outra operação concorrente já criou identity_version={identity_version} "
            f"para o avatar {avatar_id} — tente novamente"
        )


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


class InvalidGateForCurrentStatusError(Exception):
    def __init__(self, gate_name: QualityGateName, current_status: AvatarStatus) -> None:
        self.gate_name = gate_name
        self.current_status = current_status
        super().__init__(f"gate '{gate_name}' não se aplica ao status atual '{current_status}'")


class GateRequirementsNotMetError(Exception):
    def __init__(self, gate_name: QualityGateName, missing: list[str]) -> None:
        self.gate_name = gate_name
        self.missing = missing
        super().__init__(f"requisitos do gate '{gate_name}' não atendidos: {'; '.join(missing)}")


async def _lock_avatar_or_raise(session, avatar_id: uuid.UUID) -> None:
    """P1-9: `SELECT ... FOR UPDATE` na linha do avatar — serializa qualquer outra
    transação que também tente lockar este avatar (inclusive esta mesma função chamada
    de outra requisição concorrente), mesmo quando o dado que estamos prestes a criar
    ainda não existe (então não há linha própria seria seria possível lockar antes)."""
    exists = await session.scalar(
        select(AvatarRecord.id).where(AvatarRecord.id == avatar_id).with_for_update()
    )
    if exists is None:
        raise AvatarNotFoundError(avatar_id)


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


async def upsert_identity_lock_draft_atomic(
    avatar_id: uuid.UUID,
    *,
    identity_spec: dict[str, Any],
    height_cm: float | None,
    notes: str | None,
    source_asset_ids: list[uuid.UUID],
) -> IdentityLockRecord:
    """P1-9: lockar o AVATAR primeiro serializa toda criação/edição de draft — duas
    requisições concorrentes tentando criar `identity_version=N` pela primeira vez nunca
    resultam em duas linhas: a segunda espera a primeira liberar o lock do avatar, e só
    então enxerga (via a query abaixo, já depois do lock) que a linha já foi criada."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await _lock_avatar_or_raise(session, avatar_id)

        current = await session.scalar(
            select(IdentityLockRecord)
            .where(IdentityLockRecord.avatar_id == avatar_id)
            .order_by(IdentityLockRecord.identity_version.desc())
            .limit(1)
        )
        if current is None or current.status in ("superseded", "approved"):
            next_version = (current.identity_version + 1) if current else 1
            record = IdentityLockRecord(
                avatar_id=avatar_id,
                identity_version=next_version,
                status="draft",
                identity_spec=identity_spec,
                height_cm=height_cm,
                notes=notes,
                source_asset_ids=source_asset_ids,
            )
            session.add(record)
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise IdentityLockConcurrentCreationError(avatar_id, next_version) from exc
            await session.refresh(record)
            return record

        # status == draft: edita a MESMA linha (o lock do avatar já protege isto).
        current.identity_spec = identity_spec
        current.height_cm = height_cm
        current.notes = notes
        current.source_asset_ids = source_asset_ids
        current.version = current.version + 1
        current.updated_at = func.now()
        await session.commit()
        await session.refresh(current)
        return current


async def approve_identity_lock(
    lock_id: uuid.UUID, *, approved_by: str, expected_version: int
) -> tuple[IdentityLockRecord, int]:
    """Aprova o lock e, na mesma transação: (1) marca qualquer lock approved anterior
    deste avatar como superseded; (2) se isto abre uma NOVA geração de identidade
    (P1-5), reseta para NOT_TESTED todo QualityGateRecord que ainda representava a
    geração anterior; (3) P1-7 — reinicia o lifecycle: reposiciona `AvatarRecord.status`
    para DRAFT, já que nenhum status de uma geração anterior pode sobreviver a uma nova
    identidade (o Identity Gate desta nova geração ainda precisa ser aprovado
    explicitamente, exatamente como na primeira vez). Devolve o lock e o
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

        # P1-9: lock do avatar — serializa contra outra aprovação concorrente e contra
        # qualquer approve_gate_atomic que esteja lendo o identity lock aprovado atual.
        avatar_record = await session.scalar(
            select(AvatarRecord).where(AvatarRecord.id == target.avatar_id).with_for_update()
        )
        if avatar_record is None:
            raise AvatarNotFoundError(target.avatar_id)

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

            # P1-7: reinicia o lifecycle — nenhum status de uma geração anterior
            # sobrevive à aprovação de uma nova identidade.
            if avatar_record.status != AvatarStatus.DRAFT.value:
                old_status = avatar_record.status
                avatar_record.status = AvatarStatus.DRAFT.value
                avatar_record.version = avatar_record.version + 1
                avatar_record.updated_at = func.now()
                session.add(
                    AvatarStateTransitionRecord(
                        avatar_id=target.avatar_id,
                        from_status=old_status,
                        to_status=AvatarStatus.DRAFT.value,
                        actor=approved_by,
                        reason=(
                            f"nova identidade v{new_version_group} aprovada — lifecycle reiniciado"
                        ),
                        evidence=None,
                        quality_gate=None,
                        avatar_version=avatar_record.version,
                    )
                )

        await session.commit()
        await session.refresh(record)
        return record, new_version_group


# --- Reference Assets (P1-2, P1-3, P1-6b) ---------------------------------------------------


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
    só confirma o vínculo, nunca gera um id novo que pudesse divergir do path já usado.
    Cada upload é sempre uma linha NOVA (nunca colide com outra), então não precisa de
    lock especial de concorrência."""
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


async def review_reference_asset_atomic(
    avatar_id: uuid.UUID,
    asset_id: uuid.UUID,
    *,
    approved: bool,
    rejection_reason: str | None,
    rejection_notes: str | None,
    reviewed_by: str,
    expected_version: int,
) -> ReferenceAssetRecord:
    """P1-6b (opção B — evidência mutável, invalidação em cascata): se este asset estava
    contando como evidência de um MULTIVIEW gate já PASS e a rejeição faz o gate deixar
    de estar satisfeito, o gate (e qualquer downstream que dependesse dele) é invalidado
    nesta MESMA transação, e o avatar é reposicionado para o estágio ainda válido. Um
    approve nunca precisa dessa checagem — só reduz a chance de algo estar incompleto,
    nunca invalida um gate já aprovado.

    P1-9: lock do avatar SEMPRE primeiro, mesmo no caminho de approve que nunca vai
    precisar dele — mesma ordem universal de `approve_gate_atomic`/`reject_gate_atomic`
    (avatar antes de qualquer gate ou reference asset). Sem isso, esta função e
    `approve_gate_atomic` podiam lockar (asset, avatar) em ordens opostas e formar um
    deadlock real: esta aqui segurando o asset e esperando o avatar, enquanto uma
    aprovação de MULTIVIEW em paralelo segura o avatar e espera o mesmo asset (via
    `_check_gate_requirements_locked`)."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await _lock_avatar_or_raise(session, avatar_id)

        statement = (
            update(ReferenceAssetRecord)
            .where(
                ReferenceAssetRecord.id == asset_id,
                ReferenceAssetRecord.avatar_id == avatar_id,
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
                select(ReferenceAssetRecord.id).where(
                    ReferenceAssetRecord.id == asset_id,
                    ReferenceAssetRecord.avatar_id == avatar_id,
                )
            )
            if exists is None:
                raise ReferenceAssetNotFoundError(asset_id)
            raise ReferenceAssetVersionConflictError(asset_id, expected_version)

        if not approved:
            multiview_gate = await session.scalar(
                select(QualityGateRecord)
                .where(
                    QualityGateRecord.avatar_id == record.avatar_id,
                    QualityGateRecord.gate_name == QualityGateName.MULTIVIEW.value,
                    QualityGateRecord.avatar_version_group == record.capture_version,
                )
                .with_for_update()
            )
            if multiview_gate is not None and multiview_gate.status == "pass":
                lock = await session.scalar(
                    select(IdentityLockRecord)
                    .where(
                        IdentityLockRecord.avatar_id == record.avatar_id,
                        IdentityLockRecord.status == "approved",
                    )
                    .order_by(IdentityLockRecord.identity_version.desc())
                    .limit(1)
                )
                current_assets = (
                    await session.scalars(
                        select(ReferenceAssetRecord)
                        .where(
                            ReferenceAssetRecord.avatar_id == record.avatar_id,
                            ReferenceAssetRecord.capture_version == record.capture_version,
                        )
                        .with_for_update()
                    )
                ).all()
                check = gate_requirements.check_multiview_gate(
                    lock, list(current_assets), capture_version=record.capture_version
                )
                if not check.satisfied:
                    cascade_reason = (
                        f"evidência alterada: reference asset {asset_id} rejeitado "
                        f"({rejection_reason})"
                    )
                    previous_status, decision = _mark_gate_failed(
                        multiview_gate,
                        reason=cascade_reason,
                        actor=reviewed_by,
                        version_group=record.capture_version,
                    )
                    session.add(decision)
                    await _invalidate_downstream_gates(
                        session,
                        record.avatar_id,
                        from_gate=QualityGateName.MULTIVIEW,
                        version_group=record.capture_version,
                        reason=cascade_reason,
                        actor=reviewed_by,
                    )
                    await _reposition_avatar_for_invalidated_gate(
                        session,
                        record.avatar_id,
                        gate_name=QualityGateName.MULTIVIEW,
                        reason=cascade_reason,
                        actor=reviewed_by,
                    )

        await session.commit()
        await session.refresh(record)
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


# --- Quality Gates (leitura simples) ---------------------------------------------------------


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
    """Só para LISTAGEM/visualização (`service.list_quality_gates`) — não decide nada
    crítico, então não precisa da atomicidade pesada de `approve_gate_atomic`."""
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


# --- Transação atômica de aprovação/rejeição de gate (P1-4, P1-6, P1-6b) -------------------


def _mark_gate_failed(
    gate: QualityGateRecord, *, reason: str | None, actor: str | None, version_group: int
) -> tuple[str, QualityGateDecisionRecord]:
    """Muda `gate` (já carregado e lockado pelo chamador) para FAIL — não adiciona a
    decisão à sessão nem comita, o chamador decide isso. Devolve o status anterior (para
    a decisão) e o próprio registro de decisão, já pronto para `session.add()`."""
    previous_status = gate.status
    gate.status = "fail"
    gate.approved_by = None
    gate.approved_at = None
    gate.reason = reason
    gate.version = gate.version + 1
    gate.updated_at = func.now()
    decision = QualityGateDecisionRecord(
        avatar_id=gate.avatar_id,
        gate_name=gate.gate_name,
        action="reject",
        previous_status=previous_status,
        new_status="fail",
        avatar_version_group=version_group,
        actor=actor,
        reason=reason,
        evidence=None,
    )
    return previous_status, decision


async def _invalidate_downstream_gates(
    session,
    avatar_id: uuid.UUID,
    *,
    from_gate: QualityGateName,
    version_group: int,
    reason: str,
    actor: str | None,
) -> None:
    """P1-6b: marca FAIL todo gate downstream de `from_gate` (na ordem do pipeline) que
    esteja atualmente PASS — nunca deixa um gate posterior continuar aprovado quando o
    que ele dependia deixou de valer. Hoje isto quase nunca encontra nada para fazer
    (mesh/rig/materials/face/... nunca chegam a PASS sem GPU real), mas a estrutura fica
    correta para quando esses gates puderem, de fato, estar PASS."""
    downstream = downstream_gates_of(from_gate)
    if not downstream:
        return
    gates = (
        await session.scalars(
            select(QualityGateRecord)
            .where(
                QualityGateRecord.avatar_id == avatar_id,
                QualityGateRecord.gate_name.in_([g.value for g in downstream]),
                QualityGateRecord.avatar_version_group == version_group,
            )
            .with_for_update()
        )
    ).all()
    for gate in gates:
        if gate.status != "pass":
            continue
        _previous_status, decision = _mark_gate_failed(
            gate, reason=reason, actor=actor, version_group=version_group
        )
        session.add(decision)


async def _reposition_avatar_for_invalidated_gate(
    session, avatar_id: uuid.UUID, *, gate_name: QualityGateName, reason: str, actor: str | None
) -> None:
    """P1-6b/P1-7: reposiciona `AvatarRecord.status` para o predecessor do alvo de
    `gate_name`, SE o status atual estiver no ou além desse alvo — nunca deixa
    sobreviver um status "impossível" (gate caído, avatar ainda avançado além dele).
    Não faz nada se o avatar já estiver "antes" do alvo (nada a reposicionar)."""
    avatar_record = await session.scalar(
        select(AvatarRecord).where(AvatarRecord.id == avatar_id).with_for_update()
    )
    if avatar_record is None:
        return
    target = GATE_TARGET_STATUS[gate_name]
    current_status = AvatarStatus(avatar_record.status)
    if _STATUS_ORDER.index(current_status) < _STATUS_ORDER.index(target):
        return
    new_status = predecessor_status_of(gate_name)
    if current_status == new_status:
        return
    old_status = avatar_record.status
    avatar_record.status = new_status.value
    avatar_record.version = avatar_record.version + 1
    avatar_record.updated_at = func.now()
    session.add(
        AvatarStateTransitionRecord(
            avatar_id=avatar_id,
            from_status=old_status,
            to_status=new_status.value,
            actor=actor,
            reason=f"invalidação em cascata: {reason}",
            evidence=None,
            quality_gate=gate_name.value,
            avatar_version=avatar_record.version,
        )
    )


async def _check_gate_requirements_locked(
    session,
    avatar_id: uuid.UUID,
    gate_name: QualityGateName,
    *,
    identity_lock: IdentityLockRecord | None,
    version_group: int,
) -> GateRequirementCheck:
    """P1-6: busca a evidência de `gate_name` com `SELECT ... FOR UPDATE`, DENTRO da
    transação que vai (talvez) escrever o resultado — elimina a janela TOCTOU que existia
    entre uma leitura solta em `service.py` e a escrita em uma transação separada."""
    if gate_name == QualityGateName.IDENTITY:
        return gate_requirements.check_identity_gate(identity_lock)
    if gate_name == QualityGateName.MULTIVIEW:
        assets = (
            await session.scalars(
                select(ReferenceAssetRecord)
                .where(
                    ReferenceAssetRecord.avatar_id == avatar_id,
                    ReferenceAssetRecord.capture_version == version_group,
                )
                .with_for_update()
            )
        ).all()
        return gate_requirements.check_multiview_gate(
            identity_lock, list(assets), capture_version=version_group
        )
    if gate_name == QualityGateName.PRODUCTION:
        gates = (
            await session.scalars(
                select(QualityGateRecord)
                .where(
                    QualityGateRecord.avatar_id == avatar_id,
                    QualityGateRecord.avatar_version_group == version_group,
                )
                .with_for_update()
            )
        ).all()
        statuses = {QualityGateName(g.gate_name): g.status for g in gates}
        return gate_requirements.check_production_gate(statuses)
    derived = (
        await session.scalars(
            select(DerivedAssetRecord)
            .where(
                DerivedAssetRecord.avatar_id == avatar_id,
                DerivedAssetRecord.avatar_version_group == version_group,
            )
            .with_for_update()
        )
    ).all()
    return gate_requirements.check_gpu_dependent_gate(gate_name, list(derived))


async def approve_gate_atomic(
    avatar_id: uuid.UUID,
    *,
    gate_name: QualityGateName,
    expected_avatar_version: int,
    checklist: dict[str, str],
    reason: str | None,
    actor: str,
    evidence: dict[str, Any] | None,
) -> tuple[QualityGateRecord, AvatarStateTransitionRecord, AvatarRecord]:
    """Uma ÚNICA transação para: (1) travar/checar o avatar; (2) resolver a version
    lineage atual (com lock no identity lock aprovado); (3) carregar e validar a
    evidência do gate COM LOCK (P1-6 — nunca uma decisão baseada em leitura stale); (4)
    obter-ou-criar o gate; (5) marcá-lo PASS; (6) avançar o avatar; (7) registrar a
    decisão e a transição; (8) COMMIT único. Qualquer falha antes do commit desfaz TUDO."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        avatar_record = await session.scalar(
            select(AvatarRecord).where(AvatarRecord.id == avatar_id).with_for_update()
        )
        if avatar_record is None:
            raise AvatarNotFoundError(avatar_id)
        if avatar_record.version != expected_avatar_version:
            raise AvatarVersionConflictError(avatar_id, expected_avatar_version)

        current_status = AvatarStatus(avatar_record.status)
        target_status = GATE_TARGET_STATUS[gate_name]
        if target_status not in ALLOWED_STATUS_TRANSITIONS.get(current_status, set()):
            raise InvalidGateForCurrentStatusError(gate_name, current_status)

        # P1-9: lock também no identity lock aprovado atual — impede que uma aprovação
        # concorrente de uma NOVA identidade mude a version lineage no meio desta
        # transação (ela ficaria bloqueada até esta aqui terminar).
        latest_approved_lock = await session.scalar(
            select(IdentityLockRecord)
            .where(
                IdentityLockRecord.avatar_id == avatar_id, IdentityLockRecord.status == "approved"
            )
            .order_by(IdentityLockRecord.identity_version.desc())
            .limit(1)
            .with_for_update()
        )
        version_group = latest_approved_lock.identity_version if latest_approved_lock else 1

        requirement_check = await _check_gate_requirements_locked(
            session,
            avatar_id,
            gate_name,
            identity_lock=latest_approved_lock,
            version_group=version_group,
        )
        if not requirement_check.satisfied:
            raise GateRequirementsNotMetError(gate_name, requirement_check.missing)

        gate = await session.scalar(
            select(QualityGateRecord)
            .where(
                QualityGateRecord.avatar_id == avatar_id,
                QualityGateRecord.gate_name == gate_name.value,
            )
            .with_for_update()
        )
        if gate is None:
            gate = QualityGateRecord(
                avatar_id=avatar_id,
                gate_name=gate_name.value,
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

        session.add(
            QualityGateDecisionRecord(
                avatar_id=avatar_id,
                gate_name=gate_name.value,
                action="approve",
                previous_status=previous_gate_status,
                new_status="pass",
                avatar_version_group=version_group,
                actor=actor,
                reason=reason,
                evidence=evidence,
            )
        )

        avatar_record.status = target_status.value
        avatar_record.version = avatar_record.version + 1
        avatar_record.updated_at = func.now()

        transition = AvatarStateTransitionRecord(
            avatar_id=avatar_id,
            from_status=current_status.value,
            to_status=target_status.value,
            actor=actor,
            reason=reason,
            evidence=evidence,
            quality_gate=gate_name.value,
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
    gate_name: QualityGateName,
    expected_avatar_version: int,
    checklist: dict[str, str],
    reason: str | None,
    actor: str,
    evidence: dict[str, Any] | None,
) -> QualityGateRecord:
    """Mesma filosofia atômica do approve para a operação correlacionada de rejeitar — lock
    do avatar PRIMEIRO e checagem de `expected_avatar_version`, na MESMA ordem de
    `approve_gate_atomic` (avatar antes de gate): duas transações concorrentes que
    lockassem nessa ordem invertida uma da outra poderiam formar um deadlock real (P1-9).
    P1-6b: se o gate estava PASS antes desta rejeição explícita, invalida downstream e
    reposiciona o avatar na mesma transação (nenhum estado "gate caiu, avatar continua
    adiantado" sobrevive)."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        avatar_record = await session.scalar(
            select(AvatarRecord).where(AvatarRecord.id == avatar_id).with_for_update()
        )
        if avatar_record is None:
            raise AvatarNotFoundError(avatar_id)
        if avatar_record.version != expected_avatar_version:
            raise AvatarVersionConflictError(avatar_id, expected_avatar_version)

        latest_approved_lock = await session.scalar(
            select(IdentityLockRecord)
            .where(
                IdentityLockRecord.avatar_id == avatar_id, IdentityLockRecord.status == "approved"
            )
            .order_by(IdentityLockRecord.identity_version.desc())
            .limit(1)
            .with_for_update()
        )
        version_group = latest_approved_lock.identity_version if latest_approved_lock else 1

        gate = await session.scalar(
            select(QualityGateRecord)
            .where(
                QualityGateRecord.avatar_id == avatar_id,
                QualityGateRecord.gate_name == gate_name.value,
            )
            .with_for_update()
        )
        if gate is None:
            gate = QualityGateRecord(
                avatar_id=avatar_id,
                gate_name=gate_name.value,
                avatar_version_group=version_group,
                status="not_tested",
                checklist=checklist,
            )
            session.add(gate)
            await session.flush()

        was_pass = gate.status == "pass"
        effective_reason = reason or f"gate '{gate_name}' rejeitado"
        _previous_status, decision = _mark_gate_failed(
            gate, reason=reason, actor=actor, version_group=gate.avatar_version_group
        )
        session.add(decision)

        if was_pass:
            await _invalidate_downstream_gates(
                session,
                avatar_id,
                from_gate=gate_name,
                version_group=gate.avatar_version_group,
                reason=effective_reason,
                actor=actor,
            )
            await _reposition_avatar_for_invalidated_gate(
                session, avatar_id, gate_name=gate_name, reason=effective_reason, actor=actor
            )

        await session.commit()
        await session.refresh(gate)
        return gate


# --- Derived Assets / Job Contracts (placeholders, seções 19-21, P1-8, P1-9) ----------------


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
    anterior. P1-9: lock do avatar serializa duas chamadas concorrentes — a UNIQUE
    constraint (migration 0006) é a garantia de banco por trás disso."""
    existing = await list_derived_assets(avatar_id, version_group=avatar_version_group)
    if existing:
        return existing
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await _lock_avatar_or_raise(session, avatar_id)
        already = (
            await session.scalars(
                select(DerivedAssetRecord).where(
                    DerivedAssetRecord.avatar_id == avatar_id,
                    DerivedAssetRecord.avatar_version_group == avatar_version_group,
                )
            )
        ).all()
        if already:
            return list(already)
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
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return await list_derived_assets(avatar_id, version_group=avatar_version_group)
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


async def list_job_contracts(
    avatar_id: uuid.UUID, *, version_group: int | None = None
) -> list[JobContractRecord]:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        statement = select(JobContractRecord).where(JobContractRecord.avatar_id == avatar_id)
        if version_group is not None:
            statement = statement.where(JobContractRecord.avatar_version_group == version_group)
        result = await session.scalars(statement)
        return list(result)


async def ensure_default_job_contracts(
    avatar_id: uuid.UUID, *, avatar_version_group: int
) -> list[JobContractRecord]:
    """Garante um contrato por tipo de job PARA A GERAÇÃO ATUAL (seção 20, P1-8) —
    `status='blocked'` porque nenhum executor real existe sem a RTX 4090 (seção 21:
    contrato, nunca execução). Uma nova geração de identidade nunca reaproveita
    silenciosamente os contratos de uma geração anterior — um novo conjunto é criado,
    os antigos permanecem como histórico. P1-9: mesmo lock-do-avatar + UNIQUE constraint
    usados em `ensure_derived_asset_placeholders`."""
    existing = await list_job_contracts(avatar_id, version_group=avatar_version_group)
    if existing:
        return existing
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        await _lock_avatar_or_raise(session, avatar_id)
        already = (
            await session.scalars(
                select(JobContractRecord).where(
                    JobContractRecord.avatar_id == avatar_id,
                    JobContractRecord.avatar_version_group == avatar_version_group,
                )
            )
        ).all()
        if already:
            return list(already)
        records = [
            JobContractRecord(
                avatar_id=avatar_id,
                job_type=job_type.value,
                avatar_version_group=avatar_version_group,
                input_version=avatar_version_group,
                required_assets=[],
                output_contract={},
                hardware_requirement=hardware.value,
                status="blocked",
                error="bloqueado: nenhum executor de GPU disponível (V1 é só contrato)",
            )
            for job_type, hardware in _JOB_HARDWARE.items()
        ]
        session.add_all(records)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return await list_job_contracts(avatar_id, version_group=avatar_version_group)
        for record in records:
            await session.refresh(record)
        return records
