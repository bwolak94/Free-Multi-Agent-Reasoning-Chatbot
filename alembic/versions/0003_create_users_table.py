"""create users table and add user_id to threads

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-13 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("username", sa.String(128), nullable=False),
        sa.Column("hashed_password", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.add_column("threads", sa.Column("user_id", sa.String(), nullable=True))
    op.add_column("threads", sa.Column("title", sa.String(120), nullable=True))
    op.create_foreign_key(
        "fk_threads_user_id",
        "threads",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_threads_user_id", "threads", type_="foreignkey")
    op.drop_column("threads", "title")
    op.drop_column("threads", "user_id")
    op.drop_table("users")
