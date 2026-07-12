"""merge transaction-index and model-metrics-auc heads

Revision ID: 2717cd5e571c
Revises: c4d93a7e1b52, d2f6a8b31c94
Create Date: 2026-07-12
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "2717cd5e571c"
down_revision: Union[str, Sequence[str], None] = ("c4d93a7e1b52", "d2f6a8b31c94")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
