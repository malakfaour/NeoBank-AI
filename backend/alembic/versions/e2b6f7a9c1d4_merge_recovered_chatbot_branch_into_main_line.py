"""merge recovered chatbot branch into main line

Revision ID: e2b6f7a9c1d4
Revises: 9f4a2c6b1d10, d76485cc6965
Create Date: 2026-07-05 00:00:01.000000

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "e2b6f7a9c1d4"
down_revision: Union[str, Sequence[str], None] = ("9f4a2c6b1d10", "d76485cc6965")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
