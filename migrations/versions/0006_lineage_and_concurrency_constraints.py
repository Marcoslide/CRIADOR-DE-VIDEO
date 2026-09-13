"""job_contracts.avatar_version_group (P1-8) + constraints de unicidade reais para
identity_locks/derived_assets/job_contracts (P1-9 — concurrency)

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # P1-8: job_contracts passa a pertencer a uma geração/lineage explícita.
    op.add_column(
        "avatar_job_contracts",
        sa.Column("avatar_version_group", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_unique_constraint(
        "uq_job_contracts_avatar_version_type",
        "avatar_job_contracts",
        ["avatar_id", "avatar_version_group", "job_type"],
    )

    # P1-9: duas requisições concorrentes nunca criam a mesma (avatar, identity_version)
    # duas vezes, nem mais de um lock 'approved' simultâneo para o mesmo avatar.
    op.create_unique_constraint(
        "uq_identity_locks_avatar_version",
        "avatar_identity_locks",
        ["avatar_id", "identity_version"],
    )
    op.create_index(
        "uq_identity_locks_one_approved_per_avatar",
        "avatar_identity_locks",
        ["avatar_id"],
        unique=True,
        postgresql_where=sa.text("status = 'approved'"),
    )

    # P1-9: duas chamadas concorrentes de ensure_derived_asset_placeholders nunca
    # duplicam a mesma (avatar, geração, tipo).
    op.create_unique_constraint(
        "uq_derived_assets_avatar_version_type",
        "avatar_derived_assets",
        ["avatar_id", "avatar_version_group", "asset_type"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_derived_assets_avatar_version_type", "avatar_derived_assets", type_="unique"
    )
    op.drop_index(
        "uq_identity_locks_one_approved_per_avatar",
        table_name="avatar_identity_locks",
        postgresql_where=sa.text("status = 'approved'"),
    )
    op.drop_constraint("uq_identity_locks_avatar_version", "avatar_identity_locks", type_="unique")
    op.drop_constraint(
        "uq_job_contracts_avatar_version_type", "avatar_job_contracts", type_="unique"
    )
    op.drop_column("avatar_job_contracts", "avatar_version_group")
