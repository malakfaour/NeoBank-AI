"""add device credentials

Revision ID: b7a1c9d3e5f6
Revises: 8c1e4f2a9b77
Create Date: 2026-07-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7a1c9d3e5f6"
down_revision: Union[str, Sequence[str], None] = "8c1e4f2a9b77"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "device_credentials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.String(length=255), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "device_id", name="uq_device_credentials_user_device"),
        sa.UniqueConstraint("device_id", name="uq_device_credentials_device_id"),
    )
    op.create_index("ix_device_credentials_user_id", "device_credentials", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_device_credentials_user_id", table_name="device_credentials")
    op.drop_table("device_credentials")
