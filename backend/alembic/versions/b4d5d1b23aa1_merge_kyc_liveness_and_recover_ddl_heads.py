"""merge kyc liveness and recover_ddl heads

Revision ID: b4d5d1b23aa1
Revises: 30e06cfd21ec, 7a3c1f2e9b40
Create Date: 2026-07-28 20:05:03.963878

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = 'b4d5d1b23aa1'
down_revision: Union[str, Sequence[str], None] = ('30e06cfd21ec', '7a3c1f2e9b40')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass