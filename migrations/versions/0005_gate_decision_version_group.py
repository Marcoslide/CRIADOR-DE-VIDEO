"""avatar_quality_gate_decisions.avatar_version_group (P1-5 — version lineage)

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "avatar_quality_gate_decisions",
        sa.Column("avatar_version_group", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("avatar_quality_gate_decisions", "avatar_version_group")
