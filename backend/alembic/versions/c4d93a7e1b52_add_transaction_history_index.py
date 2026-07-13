"""add transaction history index

Revision ID: c4d93a7e1b52
Revises: b7a1c9d3e5f6
Create Date: 2026-07-12
"""

from typing import Sequence, Union

from alembic import op


revision: str = "c4d93a7e1b52"
down_revision: Union[str, Sequence[str], None] = "b7a1c9d3e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_transactions_sender_created_at",
        "transactions",
        ["sender_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_sender_created_at", table_name="transactions")
