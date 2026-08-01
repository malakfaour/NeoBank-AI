"""Recover NBL-108/110/111 DDL: 7f3d9c1a6e28 was stamped applied without
its DDL executing.

Revision ID: 465a86435043
Revises: 6a4d2f8c1b90
Create Date: 2026-07-27

Confirmed by direct inspection of the shared Neon DB: no trigger exists
on transaction_audit_logs, and neither bill_payments nor
fraud_resolutions exist as tables, despite alembic_version showing
7f3d9c1a6e28 as applied.

Root cause (best understanding, from re-running 7f3d9c1a6e28 against a
clean reproduction of the pre-migration state): its bill_payments table
declares `currency` as `sa.Enum(..., name='walletcurrency',
create_type=False)`, intending to REUSE the walletcurrency type created
by an earlier migration. In practice this issues CREATE TYPE
walletcurrency regardless of create_type=False, which fails with
"type already exists" since that earlier migration already created it.
That failure rolled back 7f3d9c1a6e28's entire transaction -- the
trigger creation included, since it ran first in the same upgrade() --
but alembic_version was still stamped as if the migration succeeded
(most likely a manual `alembic stamp` applied as a workaround at the
time, consistent with the team's existing notes on this).

This migration does NOT touch 7f3d9c1a6e28 (never edit a merged
migration -- ENGINEERING_RULES.md #1). It re-creates the exact same
three things that migration was supposed to create -- the append-only
trigger, bill_payments, fraud_resolutions -- using raw op.execute() DDL
for bill_payments.currency specifically (referencing the existing
walletcurrency type directly in CREATE TABLE, never going through
SQLAlchemy's Enum(create_type=False) column compiler) to avoid the
exact failure above. Every statement is idempotent (CREATE ... IF NOT
EXISTS / checkfirst / DROP ... IF EXISTS before CREATE), so this is
safe to re-run even against an environment where some of these pieces
already exist from an earlier partial manual fix.

Verified against a from-scratch reproduction of the exact broken state
(full migration chain applied normally, 7f3d9c1a6e28 stamped without
running its DDL, chain continued normally to 6a4d2f8c1b90 -- the
current single head at the time this was written) before being applied
anywhere real: this migration brings that reproduction's schema to
match what 7f3d9c1a6e28 should have produced, and a second run
(simulating a retry) is a clean no-op.
"""
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "465a86435043"
down_revision = "6a4d2f8c1b90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Postgres-only, same guard as 7f3d9c1a6e28 -- the test suite
    # migrates a SQLite DB, which has none of this syntax.
    if op.get_bind().dialect.name != "postgresql":
        return

    # --- NBL-108: append-only trigger on transaction_audit_logs ---
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_transaction_audit_logs_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'transaction_audit_logs is append-only: % not allowed', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_transaction_audit_logs_no_update ON transaction_audit_logs;"
    )
    op.execute(
        """
        CREATE TRIGGER trg_transaction_audit_logs_no_update
        BEFORE UPDATE ON transaction_audit_logs
        FOR EACH ROW EXECUTE FUNCTION prevent_transaction_audit_logs_mutation();
        """
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_transaction_audit_logs_no_delete ON transaction_audit_logs;"
    )
    op.execute(
        """
        CREATE TRIGGER trg_transaction_audit_logs_no_delete
        BEFORE DELETE ON transaction_audit_logs
        FOR EACH ROW EXECUTE FUNCTION prevent_transaction_audit_logs_mutation();
        """
    )

    # --- NBL-110: bill_payments table ---
    # billtype and billpaymentstatus are new types that don't exist yet,
    # so the ordinary SQLAlchemy Enum type helper (checkfirst=True) is
    # fine for those -- it's specifically REUSING the existing
    # walletcurrency type that triggered the original failure, which is
    # why that one column is raw DDL below instead.
    postgresql.ENUM(
        "ogero", "edl", "water", "mobile_topup", name="billtype"
    ).create(op.get_bind(), checkfirst=True)
    postgresql.ENUM(
        "success", "failed", name="billpaymentstatus"
    ).create(op.get_bind(), checkfirst=True)

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS bill_payments (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            wallet_id INTEGER NOT NULL REFERENCES wallets(id),
            bill_type billtype NOT NULL,
            bill_reference VARCHAR(100) NOT NULL,
            amount NUMERIC(18, 4) NOT NULL,
            currency walletcurrency NOT NULL,
            status billpaymentstatus NOT NULL,
            biller_error VARCHAR(255),
            transaction_id INTEGER REFERENCES transactions(id),
            paid_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_bill_payments_id ON bill_payments (id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_bill_payments_user_id ON bill_payments (user_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_bill_payments_wallet_id ON bill_payments (wallet_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_bill_payments_bill_type ON bill_payments (bill_type);")

    # --- NBL-111: fraud_resolutions table ---
    postgresql.ENUM(
        "legitimate", "confirmed_fraud", name="fraudresolutiontype"
    ).create(op.get_bind(), checkfirst=True)

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fraud_resolutions (
            id SERIAL PRIMARY KEY,
            transaction_id INTEGER NOT NULL REFERENCES transactions(id),
            resolution fraudresolutiontype NOT NULL,
            reviewer_id INTEGER NOT NULL REFERENCES users(id),
            reviewer_note TEXT,
            resolved_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_fraud_resolutions_id ON fraud_resolutions (id);")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_fraud_resolutions_transaction_id "
        "ON fraud_resolutions (transaction_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fraud_resolutions_reviewer_id ON fraud_resolutions (reviewer_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_fraud_resolutions_resolved_at ON fraud_resolutions (resolved_at);"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("DROP TABLE IF EXISTS fraud_resolutions;")
    op.execute("DROP TYPE IF EXISTS fraudresolutiontype;")

    op.execute("DROP TABLE IF EXISTS bill_payments;")
    op.execute("DROP TYPE IF EXISTS billpaymentstatus;")
    op.execute("DROP TYPE IF EXISTS billtype;")

    op.execute(
        "DROP TRIGGER IF EXISTS trg_transaction_audit_logs_no_delete ON transaction_audit_logs;"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_transaction_audit_logs_no_update ON transaction_audit_logs;"
    )
    op.execute("DROP FUNCTION IF EXISTS prevent_transaction_audit_logs_mutation();")