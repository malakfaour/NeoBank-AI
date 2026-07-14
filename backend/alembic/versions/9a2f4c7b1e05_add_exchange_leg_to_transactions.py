"""add exchange_leg to transactions

Revision ID: 9a2f4c7b1e05
Revises: 520373d2992b
Create Date: 2026-07-14 00:00:00.000000

Ledger fix, issue 1 of 3 (DEVATTECH-92 prerequisite, per admin/lead
guidance): currency exchange currently records only the source-currency
leg of the movement in `transactions` -- the target-currency credit has
no row at all, making historical balance reconstruction impossible for
any user who has exchanged currency.

This migration adds a single nullable column, exchange_leg, so the
application code (app/api/v1/endpoints/exchange.py, changed separately)
can write BOTH legs of a future exchange as distinct, identifiable
Transaction rows.

Hand-written, not raw `alembic revision --autogenerate` output, per
ENGINEERING_RULES.md section 2. Touches only the `transactions` table.

SQLite compatibility (ENGINEERING_RULES.md section 2: "the test suite
migrates a SQLite DB"):
  - upgrade(): wrapped in op.batch_alter_table(...), the documented-safe
    pattern for schema changes on SQLite (whose ALTER TABLE support is
    limited enough that Alembic recommends batch mode for anything
    beyond the simplest cases). This compiles to the identical plain
    ALTER TABLE on Postgres -- no behavior change there, purely
    additional safety on SQLite.
  - downgrade(): the enum-type drop is guarded with
    `if op.get_bind().dialect.name == "postgresql":`, matching the exact
    guard pattern ENGINEERING_RULES.md section 2 requires for
    Postgres-only DDL. SQLite has no user-defined types at all (sa.Enum
    compiles to VARCHAR + CHECK there) -- there is nothing to drop, and
    calling postgresql.ENUM(...).drop() against a SQLite bind would be
    unguarded Postgres-specific DDL.

Historical exchange rows (written before this migration) are left with
exchange_leg=NULL -- not backfilled, per instruction.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "9a2f4c7b1e05"
down_revision: Union[str, Sequence[str], None] = "520373d2992b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "exchange_leg",
                sa.Enum("debit", "credit", name="exchangelegtype"),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_column("exchange_leg")

    if op.get_bind().dialect.name == "postgresql":
        exchange_leg_type_enum = postgresql.ENUM("debit", "credit", name="exchangelegtype")
        exchange_leg_type_enum.drop(op.get_bind(), checkfirst=True)
