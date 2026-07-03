"""DEVATTECH-54 add passcode_hash to users

Revision ID: 40b1be87dbfe
Revises: 266e7be163e5
Create Date: 2026-07-02 14:14:18.874860

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '40b1be87dbfe'
down_revision: Union[str, Sequence[str], None] = '266e7be163e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("passcode_hash", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "passcode_hash")
