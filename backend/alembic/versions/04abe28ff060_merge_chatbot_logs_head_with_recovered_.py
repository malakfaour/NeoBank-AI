"""merge chatbot logs head with recovered migration line

Revision ID: 04abe28ff060
Revises: 985993be8d0d, e2b6f7a9c1d4
Create Date: 2026-07-05 21:22:52.222232

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '04abe28ff060'
down_revision: Union[str, Sequence[str], None] = ('985993be8d0d', 'e2b6f7a9c1d4')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
