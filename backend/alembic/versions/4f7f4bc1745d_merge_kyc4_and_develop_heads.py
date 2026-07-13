"""merge kyc4 and develop heads

Revision ID: 4f7f4bc1745d
Revises: 2717cd5e571c, b7e9d2c4f6a1
Create Date: 2026-07-13 19:35:59.761255

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = '4f7f4bc1745d'
down_revision: Union[str, Sequence[str], None] = ('2717cd5e571c', 'b7e9d2c4f6a1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
