"""add ledger_direction to transactions

Revision ID: b3f8e21c9a47
Revises: 9a2f4c7b1e05
Create Date: 2026-07-14 00:00:00.000000

Ledger fix, issues 2 and 3 of 3 (DEVATTECH-92 prerequisite, per admin/
lead guidance):

  - Issue 2: fraud reversals credit money back via lock_and_credit_wallet
    but wrote no compensating Transaction row for the credit-back event
    -- only the original transaction's status flipped to "reversed".
  - Issue 3: admin manual adjustments store credit/debit direction only
    in audit-log JSON metadata, not as typed Transaction data.

This migration adds a single nullable column, ledger_direction, so
application code (app/api/v1/endpoints/admin.py, changed separately) can
mark both a reversal's compensating Transaction row (always credit) and
an Adjustment row (credit or debit) with an explicit, typed direction --
readable directly from Transaction data, with no JSON parsing and no
reliance on a separate audit-log join.

Hand-written, not raw `alembic revision --autogenerate` output, per
ENGINEERING_RULES.md section 2. Touches only the `transactions` table --
no other table is created, altered, or dropped. Per approved scope,
related_transaction_id is intentionally NOT added -- linkage between a
compensating Reversal row and its original transaction lives only in
audit-log metadata (compensating_transaction_id / related_transaction_id
fields on the two respective audit entries), not as a schema column.

SQLite compatibility (ENGINEERING_RULES.md section 2: "the test suite
migrates a SQLite DB"), same corrected pattern already used in
9a2f4c7b1e05:
  - upgrade(): wrapped in op.batch_alter_table(...), the documented-safe
    pattern for schema changes on SQLite.
  - downgrade(): the enum-type drop is guarded with
    `if op.get_bind().dialect.name == "postgresql":` -- SQLite has no
    user-defined types (sa.Enum compiles to VARCHAR + CHECK there), so
    there is nothing to drop on that dialect.

Historical Reversal/Adjustment rows created before this migration keep
ledger_direction=NULL -- not backfilled, per instruction.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b3f8e21c9a47"
down_revision: Union[str, Sequence[str], None] = "9a2f4c7b1e05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        ledger_direction_enum = postgresql.ENUM(
            "debit",
            "credit",
            name="ledgerdirection",
        )
        ledger_direction_enum.create(op.get_bind(), checkfirst=True)

        ledger_direction_column_type = postgresql.ENUM(
            "debit",
            "credit",
            name="ledgerdirection",
            create_type=False,
        )
    else:
        ledger_direction_column_type = sa.Enum(
            "debit",
            "credit",
            name="ledgerdirection",
        )

    with op.batch_alter_table("transactions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "ledger_direction",
                ledger_direction_column_type,
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_column("ledger_direction")

    if op.get_bind().dialect.name == "postgresql":
        ledger_direction_enum = postgresql.ENUM("debit", "credit", name="ledgerdirection")
        ledger_direction_enum.drop(op.get_bind(), checkfirst=True)
