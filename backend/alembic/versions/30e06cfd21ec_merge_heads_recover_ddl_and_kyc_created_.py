"""merge heads: recover_ddl and kyc_created_at

Revision ID: 30e06cfd21ec
Revises: 465a86435043, b3f8a1c2d4e6
Create Date: 2026-07-28 19:31:01.850716

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '30e06cfd21ec'
down_revision: Union[str, Sequence[str], None] = ('465a86435043', 'b3f8a1c2d4e6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
