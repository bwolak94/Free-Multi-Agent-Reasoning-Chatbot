"""create user_tool_prefs table

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-13
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_tool_prefs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("tool_name", sa.String(128), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "tool_name", name="uq_user_tool"),
    )
    op.create_index("ix_user_tool_prefs_user_id", "user_tool_prefs", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_tool_prefs_user_id", table_name="user_tool_prefs")
    op.drop_table("user_tool_prefs")
