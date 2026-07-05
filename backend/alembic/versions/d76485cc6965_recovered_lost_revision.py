"""recover lost revision applied to shared Neon but never committed

Revision ID: d76485cc6965
Revises: fef1258ad3aa
Create Date: 2026-07-05 00:00:00.000000

Reconstructs a migration that was present on the shared/recovery Neon branch
but missing from repo history, based on a schema audit performed on 2026-07-05.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "d76485cc6965"
down_revision: Union[str, Sequence[str], None] = "fef1258ad3aa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        currencyenum = postgresql.ENUM("USD", "LBP", "USDT", name="currencyenum")
        currencyenum.create(bind, checkfirst=True)

    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "messages",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_sessions_user_id", "chat_sessions", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_chat_sessions_user_id", table_name="chat_sessions")
    op.drop_table("chat_sessions")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        currencyenum = postgresql.ENUM("USD", "LBP", "USDT", name="currencyenum")
        currencyenum.drop(bind, checkfirst=True)
