"""baseline: enable pgcrypto extension (gen_random_uuid for future PKs)

Revision ID: 0001
Revises:
Create Date: 2026-09-10

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Toda entidade futura (Avatar, Voice, Motion, Product, ...) usará UUID como chave
    # primária — habilitamos gen_random_uuid() agora para não repetir isso em cada
    # migration de domínio.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")
