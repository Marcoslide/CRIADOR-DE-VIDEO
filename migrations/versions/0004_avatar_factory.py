"""avatar factory control plane: identity locks, reference assets, state transitions,
quality gates (+decisions), derived assets, job contracts

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "avatar_identity_locks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "avatar_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("avatars.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("identity_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column(
            "identity_spec",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("height_cm", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "source_asset_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("reference_manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("checksum", sa.String(length=128), nullable=True),
        sa.Column("approved_by", sa.String(length=200), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("identity_version >= 1", name="ck_identity_locks_version_positive"),
        sa.CheckConstraint(
            "status IN ('draft', 'approved', 'superseded')", name="ck_identity_locks_status_valid"
        ),
        sa.CheckConstraint("version >= 1", name="ck_identity_locks_optimistic_version_positive"),
    )
    op.create_index("ix_avatar_identity_locks_avatar_id", "avatar_identity_locks", ["avatar_id"])

    op.create_table(
        "avatar_reference_assets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "avatar_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("avatars.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("capture_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("angle", sa.Integer(), nullable=True),
        sa.Column("capture_type", sa.String(length=40), nullable=True),
        sa.Column("side", sa.String(length=20), nullable=True),
        sa.Column("orientation", sa.String(length=40), nullable=True),
        sa.Column("source", sa.String(length=200), nullable=True),
        sa.Column("storage_remote_path", sa.String(length=1000), nullable=False),
        sa.Column("storage_provider_id", sa.String(length=200), nullable=True),
        sa.Column("checksum", sa.String(length=128), nullable=True),
        sa.Column("mime_type", sa.String(length=100), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("resolution_width", sa.Integer(), nullable=True),
        sa.Column("resolution_height", sa.Integer(), nullable=True),
        sa.Column("upload_state", sa.String(length=20), nullable=False, server_default="uploaded"),
        sa.Column("qa_status", sa.String(length=20), nullable=False, server_default="not_checked"),
        sa.Column("qa_detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("approved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("rejection_reason", sa.String(length=40), nullable=True),
        sa.Column("rejection_notes", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.String(length=200), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "upload_state IN ('uploaded', 'qa_pending', 'approved', 'rejected')",
            name="ck_reference_assets_upload_state_valid",
        ),
        sa.CheckConstraint(
            "qa_status IN ('pass', 'warn', 'fail', 'not_checked', 'requires_human', "
            "'requires_model')",
            name="ck_reference_assets_qa_status_valid",
        ),
        sa.CheckConstraint(
            "angle IS NULL OR (angle >= 0 AND angle < 360 AND angle % 10 = 0)",
            name="ck_reference_assets_angle_valid",
        ),
        sa.CheckConstraint(
            "capture_version >= 1", name="ck_reference_assets_capture_version_positive"
        ),
        sa.CheckConstraint("version >= 1", name="ck_reference_assets_optimistic_version_positive"),
    )
    op.create_index(
        "ix_avatar_reference_assets_avatar_id", "avatar_reference_assets", ["avatar_id"]
    )
    op.create_index(
        "ix_avatar_reference_assets_category", "avatar_reference_assets", ["avatar_id", "category"]
    )

    op.create_table(
        "avatar_state_transitions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "avatar_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("avatars.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_status", sa.String(length=40), nullable=False),
        sa.Column("to_status", sa.String(length=40), nullable=False),
        sa.Column("actor", sa.String(length=200), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("quality_gate", sa.String(length=20), nullable=True),
        sa.Column("avatar_version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_avatar_state_transitions_avatar_id", "avatar_state_transitions", ["avatar_id"]
    )

    op.create_table(
        "avatar_quality_gates",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "avatar_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("avatars.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("gate_name", sa.String(length=20), nullable=False),
        sa.Column("avatar_version_group", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="not_tested"),
        sa.Column(
            "checklist",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("approved_by", sa.String(length=200), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "gate_name IN ('identity', 'multiview', 'mesh', 'rig', 'materials', 'face', "
            "'voice', 'motion', 'master', 'production')",
            name="ck_quality_gates_name_valid",
        ),
        sa.CheckConstraint(
            "status IN ('not_tested', 'pass', 'warn', 'fail', 'requires_human', 'requires_model')",
            name="ck_quality_gates_status_valid",
        ),
        sa.CheckConstraint("version >= 1", name="ck_quality_gates_optimistic_version_positive"),
        sa.UniqueConstraint("avatar_id", "gate_name", name="uq_quality_gates_avatar_gate"),
    )

    op.create_table(
        "avatar_quality_gate_decisions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "avatar_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("avatars.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("gate_name", sa.String(length=20), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("previous_status", sa.String(length=20), nullable=False),
        sa.Column("new_status", sa.String(length=20), nullable=False),
        sa.Column("actor", sa.String(length=200), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "action IN ('approve', 'reject', 'request_recapture')",
            name="ck_gate_decisions_action_valid",
        ),
    )
    op.create_index(
        "ix_avatar_quality_gate_decisions_avatar_id",
        "avatar_quality_gate_decisions",
        ["avatar_id"],
    )

    op.create_table(
        "avatar_derived_assets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "avatar_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("avatars.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("asset_type", sa.String(length=30), nullable=False),
        sa.Column("avatar_version_group", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="not_generated"),
        sa.Column("storage_remote_path", sa.String(length=1000), nullable=True),
        sa.Column(
            "asset_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "asset_type IN ('reconstructed_mesh', 'retopology_mesh', 'texture_albedo', "
            "'texture_normal', 'texture_roughness', 'groom', 'metahuman_asset', 'rig', "
            "'facial_rig', 'lod', 'thumbnail', 'preview_render')",
            name="ck_derived_assets_type_valid",
        ),
        sa.CheckConstraint(
            "status IN ('not_generated', 'queued', 'generating', 'generated', 'failed')",
            name="ck_derived_assets_status_valid",
        ),
        sa.CheckConstraint("version >= 1", name="ck_derived_assets_optimistic_version_positive"),
    )
    op.create_index("ix_avatar_derived_assets_avatar_id", "avatar_derived_assets", ["avatar_id"])

    op.create_table(
        "avatar_job_contracts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "avatar_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("avatars.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("job_type", sa.String(length=30), nullable=False),
        sa.Column("input_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "required_assets",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "output_contract",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("hardware_requirement", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "job_type IN ('multiview_reconstruction', 'mesh_refinement', "
            "'texture_generation', 'metahuman_conversion', 'facial_rig', 'groom_build', "
            "'material_build', 'quality_render')",
            name="ck_job_contracts_type_valid",
        ),
        sa.CheckConstraint(
            "hardware_requirement IN ('cpu', 'gpu_any', 'rtx_class', 'rtx_4090', 'ai_heavy')",
            name="ck_job_contracts_hardware_valid",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'ready', 'blocked', 'running', 'completed', 'failed', "
            "'cancelled')",
            name="ck_job_contracts_status_valid",
        ),
        sa.CheckConstraint("attempt >= 0", name="ck_job_contracts_attempt_non_negative"),
        sa.CheckConstraint("version >= 1", name="ck_job_contracts_optimistic_version_positive"),
    )
    op.create_index("ix_avatar_job_contracts_avatar_id", "avatar_job_contracts", ["avatar_id"])


def downgrade() -> None:
    op.drop_index("ix_avatar_job_contracts_avatar_id", table_name="avatar_job_contracts")
    op.drop_table("avatar_job_contracts")

    op.drop_index("ix_avatar_derived_assets_avatar_id", table_name="avatar_derived_assets")
    op.drop_table("avatar_derived_assets")

    op.drop_index(
        "ix_avatar_quality_gate_decisions_avatar_id", table_name="avatar_quality_gate_decisions"
    )
    op.drop_table("avatar_quality_gate_decisions")

    op.drop_table("avatar_quality_gates")

    op.drop_index("ix_avatar_state_transitions_avatar_id", table_name="avatar_state_transitions")
    op.drop_table("avatar_state_transitions")

    op.drop_index("ix_avatar_reference_assets_category", table_name="avatar_reference_assets")
    op.drop_index("ix_avatar_reference_assets_avatar_id", table_name="avatar_reference_assets")
    op.drop_table("avatar_reference_assets")

    op.drop_index("ix_avatar_identity_locks_avatar_id", table_name="avatar_identity_locks")
    op.drop_table("avatar_identity_locks")
