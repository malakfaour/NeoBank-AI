"""add push subscriptions table

Revision ID: a9c4f3e2b1d0
Revises: d2f6a8b31c94
Create Date: 2026-07-11 15:00:00.000000

DEVATTECH-109: stores FCM web push registration tokens per user.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a9c4f3e2b1d0"
down_revision: Union[str, Sequence[str], None] = "d2f6a8b31c94"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token", name="uq_push_subscriptions_token"),
    )
    op.create_index(
        op.f("ix_push_subscriptions_id"),
        "push_subscriptions",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_push_subscriptions_user_id"),
        "push_subscriptions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_push_subscriptions_token"),
        "push_subscriptions",
        ["token"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_push_subscriptions_token"),
        table_name="push_subscriptions",
    )
    op.drop_index(
        op.f("ix_push_subscriptions_user_id"),
        table_name="push_subscriptions",
    )
    op.drop_index(
        op.f("ix_push_subscriptions_id"),
        table_name="push_subscriptions",
    )
    op.drop_table("push_subscriptions")
