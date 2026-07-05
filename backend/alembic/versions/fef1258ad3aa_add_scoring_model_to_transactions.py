"""add scoring_model to transactions

Revision ID: fef1258ad3aa
Revises: 835198f3ffae
Create Date: 2026-07-02 19:43:53.594501

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'fef1258ad3aa'
down_revision: Union[str, Sequence[str], None] = '835198f3ffae'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # NOTE: autogenerate also detected 'removed table user_sessions' and
    # 'removed column users.passcode_hash' -- both false positives caused
    # by feature/auth's migrations already being applied to this shared DB
    # while feature/auth's model code isn't merged into this branch yet.
    # This migration ONLY adds scoring_model -- it does not touch
    # user_sessions or passcode_hash, which belong to feature/auth.
    op.add_column('transactions', sa.Column('scoring_model', sa.String(length=50), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('transactions', 'scoring_model')
