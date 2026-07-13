"""add notification preferences and tx notification types

Revision ID: b7e9d2c4f6a1
Revises: 1e652f5a22fd
Create Date: 2026-07-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b7e9d2c4f6a1"
down_revision: Union[str, None] = "1e652f5a22fd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_NOTIFICATION_PREFERENCES = '{"email": true, "push": true, "sms": true}'


def upgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'TX_SENT'")
        op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'TX_RECEIVED'")
        op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'TX_FLAGGED'")

    op.add_column(
        "users",
        sa.Column(
            "notification_preferences",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=False,
            server_default=sa.text(f"'{DEFAULT_NOTIFICATION_PREFERENCES}'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "notification_preferences")

    # PostgreSQL enum values cannot be safely removed without recreating the
    # enum and rewriting dependent columns, so TX_* enum values are left in place.
