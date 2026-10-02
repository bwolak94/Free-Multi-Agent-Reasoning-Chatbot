"""create threads table

Revision ID: 0001
Revises:
Create Date: 2026-10-02 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "threads",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("idle", "running", "waiting_hitl", "error", name="thread_status"),
            nullable=False,
        ),
        sa.Column("hitl_config", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("threads")
    op.execute("DROP TYPE IF EXISTS thread_status")
