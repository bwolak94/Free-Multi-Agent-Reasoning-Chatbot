"""add deleted status to thread_status enum

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-13
"""
from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite does not support ALTER TYPE; Postgres needs explicit enum update
    with op.get_context().autocommit_block():
        try:
            op.execute("ALTER TYPE thread_status ADD VALUE IF NOT EXISTS 'deleted'")
        except Exception:
            # SQLite / already exists — skip
            pass


def downgrade() -> None:
    # Postgres does not support removing enum values easily; no-op
    pass
