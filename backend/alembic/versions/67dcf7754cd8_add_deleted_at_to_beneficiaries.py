"""add deleted_at to beneficiaries

Revision ID: 67dcf7754cd8
Revises: 266e7be163e5
Create Date: 2026-07-02 23:53:49.230580

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '67dcf7754cd8'
down_revision: Union[str, Sequence[str], None] = '266e7be163e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "beneficiaries",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("beneficiaries", "deleted_at")