"""merge sprint 2 heads (fraud, beneficiaries, exchange audit)

Three feature branches were merged into develop, each with a migration
based on 266e7be163e5, leaving three divergent Alembic heads:

- a1b2c3d4e5f6 (transactions/fraud chain, via passcode + user_sessions)
- 67dcf7754cd8 (beneficiaries soft delete)
- 61faf64c5f63 (exchange audit log)

This no-op merge revision unifies them into a single head so
`alembic upgrade head` works again.

Revision ID: c3a9f1e2b4d7
Revises: a1b2c3d4e5f6, 67dcf7754cd8, 61faf64c5f63
Create Date: 2026-07-04 10:45:00.000000

"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = 'c3a9f1e2b4d7'
down_revision: Union[str, Sequence[str], None] = ('a1b2c3d4e5f6', '67dcf7754cd8', '61faf64c5f63')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge point only — no schema changes."""
    pass


def downgrade() -> None:
    """Merge point only — no schema changes."""
    pass
