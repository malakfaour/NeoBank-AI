from typing import Sequence, Union

from alembic import op

revision: str = "d5e91a4c7f38"
down_revision: Union[str, Sequence[str], None] = "b3f8e21c9a47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_transactions_receiver_created_at",
        "transactions",
        ["receiver_id", "created_at"],
    )
    op.create_index(
        "ix_transactions_status",
        "transactions",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_status", table_name="transactions")
    op.drop_index(
        "ix_transactions_receiver_created_at",
        table_name="transactions",
    )