from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260915_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "devices",
        sa.Column("device_id", sa.String(length=128), primary_key=True),
        sa.Column("public_key_pem", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "auth_challenges",
        sa.Column("challenge_id", sa.String(length=64), primary_key=True),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("nonce", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["devices.device_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_auth_challenges_device_expires", "auth_challenges", ["device_id", "expires_at"])

    op.create_table(
        "entity_records",
        sa.Column("entity_type", sa.String(length=64), primary_key=True),
        sa.Column("entity_id", sa.String(length=128), primary_key=True),
        sa.Column("logical_clock", sa.Integer(), nullable=False),
        sa.Column("origin_device_id", sa.String(length=128), nullable=False),
        sa.Column("deleted", sa.Boolean(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_entity_records_type_updated", "entity_records", ["entity_type", "updated_at"])

    op.create_table(
        "change_log",
        sa.Column("server_seq", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("change_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=False),
        sa.Column("logical_clock", sa.Integer(), nullable=False),
        sa.Column("origin_device_id", sa.String(length=128), nullable=False),
        sa.Column("deleted", sa.Boolean(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_change_log_seq", "change_log", ["server_seq"])
    op.create_index("ix_change_log_entity", "change_log", ["entity_type", "entity_id"])

    op.create_table(
        "audit_log",
        sa.Column("audit_seq", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("actor_device_id", sa.String(length=128), nullable=True),
        sa.Column("action", sa.String(length=96), nullable=False),
        sa.Column("target", sa.String(length=256), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("prev_hash", sa.String(length=64), nullable=False),
        sa.Column("entry_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_log_created", "audit_log", ["created_at"])

    op.create_table(
        "plan_snapshots",
        sa.Column("snapshot_id", sa.String(length=64), primary_key=True),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("plan_json", sa.JSON(), nullable=False),
        sa.Column("audit_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("device_id", "request_hash", name="uq_plan_snapshot_device_request"),
    )
    op.create_index("ix_plan_snapshots_device_created", "plan_snapshots", ["device_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_plan_snapshots_device_created", table_name="plan_snapshots")
    op.drop_table("plan_snapshots")
    op.drop_index("ix_audit_log_created", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index("ix_change_log_entity", table_name="change_log")
    op.drop_index("ix_change_log_seq", table_name="change_log")
    op.drop_table("change_log")
    op.drop_index("ix_entity_records_type_updated", table_name="entity_records")
    op.drop_table("entity_records")
    op.drop_index("ix_auth_challenges_device_expires", table_name="auth_challenges")
    op.drop_table("auth_challenges")
    op.drop_table("devices")
