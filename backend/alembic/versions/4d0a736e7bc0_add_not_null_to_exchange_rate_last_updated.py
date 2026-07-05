"""add NOT NULL to exchange_rates.last_updated_at (sprint 3 model alignment)

Revision ID: 4d0a736e7bc0
Revises: c3a9f1e2b4d7
Create Date: 2026-07-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4d0a736e7bc0'
down_revision: Union[str, Sequence[str], None] = 'c3a9f1e2b4d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Sprint 3 model alignment: every other timestamp column in the models
    # is nullable=False; exchange_rates.last_updated_at was the one
    # exception (created nullable in 00ec1be9d686_initial_schema.py,
    # despite having a server_default=now() from the start -- new rows
    # were always populated, but the column itself allowed NULL).
    #
    # Backfill first, in case any row somehow has a NULL value (e.g.
    # inserted via a path that bypassed the ORM default), then enforce
    # NOT NULL. Backfilling is a one-way, non-destructive operation --
    # not reversed in downgrade().
    op.execute(
        "UPDATE exchange_rates SET last_updated_at = now() "
        "WHERE last_updated_at IS NULL"
    )
    op.alter_column(
        'exchange_rates',
        'last_updated_at',
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        existing_server_default=sa.text('now()'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        'exchange_rates',
        'last_updated_at',
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
        existing_server_default=sa.text('now()'),
    )