"""merge email verification and is_active heads

Revision ID: 0b95ac59cea7
Revises: c1a9e4f7d382
Create Date: 2026-08-01 22:52:46.987487

"""
from typing import Sequence, Union



# revision identifiers, used by Alembic.
revision: str = '0b95ac59cea7'
down_revision: Union[str, Sequence[str], None] = 'c1a9e4f7d382'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
