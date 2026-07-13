"""merge kyc4 and devattech-102 heads

Revision ID: 520373d2992b
Revises: 4f7f4bc1745d, c8d4e6f1a2b3
Create Date: 2026-07-13 20:15:21.469239

"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = '520373d2992b'
down_revision: Union[str, Sequence[str], None] = ('4f7f4bc1745d', 'c8d4e6f1a2b3')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
