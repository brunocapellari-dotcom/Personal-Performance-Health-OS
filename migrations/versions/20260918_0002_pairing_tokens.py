from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260918_0002"
down_revision: str | None = "20260915_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pairing_tokens",
        sa.Column("token_hash", sa.String(length=64), primary_key=True),
        sa.Column("issued_by_device_id", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["issued_by_device_id"], ["devices.device_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_pairing_tokens_expires", "pairing_tokens", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_pairing_tokens_expires", table_name="pairing_tokens")
    op.drop_table("pairing_tokens")
