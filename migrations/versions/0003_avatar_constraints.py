"""avatar constraints: status enum domain and positive optimistic-lock version

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-12
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint("ck_avatars_version_positive", "avatars", "version >= 1")
    op.create_check_constraint(
        "ck_avatars_status_valid",
        "avatars",
        "status IN ('draft', 'identity_locked', 'multiview_in_progress', "
        "'multiview_approved', 'mesh_in_progress', 'mesh_approved', 'rigged', "
        "'materials_approved', 'face_approved', 'voice_approved', 'motion_approved', "
        "'master_approved', 'production_ready')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_avatars_status_valid", "avatars", type_="check")
    op.drop_constraint("ck_avatars_version_positive", "avatars", type_="check")
