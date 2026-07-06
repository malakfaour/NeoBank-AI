"""NBL-108/110/111: audit-log append-only trigger, bill_payments, fraud_resolutions

Revision ID: 7f3d9c1a6e28
Revises: 04abe28ff060
Create Date: 2026-07-06 00:00:00.000000

Single migration for the whole NBL-108/110/111 task cluster, per
ENGINEERING_RULES.md §2 ("Exactly ONE new revision per PR").

IMPORTANT: this re-does NBL-108's trigger from scratch. An earlier
attempt at this migration (revision c4b7e91a3f6d) was never actually
committed to develop -- it existed only as a local untracked file on one
contributor's machine. The append-only trigger on transaction_audit_logs
does not exist on develop in any form prior to this migration.

down_revision is 04abe28ff060, the actual current single head on develop
(confirmed via `alembic heads` after the stray untracked file was moved
out of alembic/versions/). If develop has moved again since, re-parent
this before merging -- do not merge heads without telling the team.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '7f3d9c1a6e28'
down_revision: Union[str, Sequence[str], None] = '04abe28ff060'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- NBL-108: append-only enforcement on transaction_audit_logs ---
    # Postgres-only: the test suite migrates a SQLite DB (per
    # conftest.py's DATABASE_URL), which has no equivalent trigger/
    # function syntax -- guarded per ENGINEERING_RULES.md §2.
    if op.get_bind().dialect.name == "postgresql":
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
            """
            CREATE TRIGGER trg_transaction_audit_logs_no_update
            BEFORE UPDATE ON transaction_audit_logs
            FOR EACH ROW EXECUTE FUNCTION prevent_transaction_audit_logs_mutation();
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_transaction_audit_logs_no_delete
            BEFORE DELETE ON transaction_audit_logs
            FOR EACH ROW EXECUTE FUNCTION prevent_transaction_audit_logs_mutation();
            """
        )

    # --- NBL-110: bill_payments table ---
    # currency reuses the existing walletcurrency enum type (confirmed
    # from the wallets table's own migration -- create_type=False),
    # rather than creating a third duplicate currency enum.
    op.create_table(
        'bill_payments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('wallet_id', sa.Integer(), nullable=False),
        sa.Column('bill_type', sa.Enum('ogero', 'edl', 'water', 'mobile_topup', name='billtype'), nullable=False),
        sa.Column('bill_reference', sa.String(length=100), nullable=False),
        sa.Column('amount', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('currency', sa.Enum('USD', 'LBP', 'USDT', name='walletcurrency', create_type=False), nullable=False),
        sa.Column('status', sa.Enum('success', 'failed', name='billpaymentstatus'), nullable=False),
        sa.Column('biller_error', sa.String(length=255), nullable=True),
        sa.Column('transaction_id', sa.Integer(), nullable=True),
        sa.Column('paid_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['wallet_id'], ['wallets.id'], ),
        sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_bill_payments_id'), 'bill_payments', ['id'], unique=False)
    op.create_index(op.f('ix_bill_payments_user_id'), 'bill_payments', ['user_id'], unique=False)
    op.create_index(op.f('ix_bill_payments_wallet_id'), 'bill_payments', ['wallet_id'], unique=False)
    op.create_index(op.f('ix_bill_payments_bill_type'), 'bill_payments', ['bill_type'], unique=False)

    # --- NBL-111: fraud_resolutions table ---
    op.create_table(
        'fraud_resolutions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('transaction_id', sa.Integer(), nullable=False),
        sa.Column('resolution', sa.Enum('legitimate', 'confirmed_fraud', name='fraudresolutiontype'), nullable=False),
        sa.Column('reviewer_id', sa.Integer(), nullable=False),
        sa.Column('reviewer_note', sa.Text(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id'], ),
        sa.ForeignKeyConstraint(['reviewer_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_fraud_resolutions_id'), 'fraud_resolutions', ['id'], unique=False)
    op.create_index(op.f('ix_fraud_resolutions_transaction_id'), 'fraud_resolutions', ['transaction_id'], unique=True)
    op.create_index(op.f('ix_fraud_resolutions_reviewer_id'), 'fraud_resolutions', ['reviewer_id'], unique=False)
    op.create_index(op.f('ix_fraud_resolutions_resolved_at'), 'fraud_resolutions', ['resolved_at'], unique=False)


def downgrade() -> None:
    # --- NBL-111: fraud_resolutions table ---
    op.drop_index(op.f('ix_fraud_resolutions_resolved_at'), table_name='fraud_resolutions')
    op.drop_index(op.f('ix_fraud_resolutions_reviewer_id'), table_name='fraud_resolutions')
    op.drop_index(op.f('ix_fraud_resolutions_transaction_id'), table_name='fraud_resolutions')
    op.drop_index(op.f('ix_fraud_resolutions_id'), table_name='fraud_resolutions')
    op.drop_table('fraud_resolutions')

    fraud_resolution_type_enum = postgresql.ENUM('legitimate', 'confirmed_fraud', name='fraudresolutiontype')
    fraud_resolution_type_enum.drop(op.get_bind(), checkfirst=True)

    # --- NBL-110: bill_payments table ---
    op.drop_index(op.f('ix_bill_payments_bill_type'), table_name='bill_payments')
    op.drop_index(op.f('ix_bill_payments_wallet_id'), table_name='bill_payments')
    op.drop_index(op.f('ix_bill_payments_user_id'), table_name='bill_payments')
    op.drop_index(op.f('ix_bill_payments_id'), table_name='bill_payments')
    op.drop_table('bill_payments')

    bill_payment_status_enum = postgresql.ENUM('success', 'failed', name='billpaymentstatus')
    bill_payment_status_enum.drop(op.get_bind(), checkfirst=True)

    bill_type_enum = postgresql.ENUM('ogero', 'edl', 'water', 'mobile_topup', name='billtype')
    bill_type_enum.drop(op.get_bind(), checkfirst=True)

    # --- NBL-108: append-only enforcement on transaction_audit_logs ---
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_transaction_audit_logs_no_delete ON transaction_audit_logs;")
        op.execute("DROP TRIGGER IF EXISTS trg_transaction_audit_logs_no_update ON transaction_audit_logs;")
        op.execute("DROP FUNCTION IF EXISTS prevent_transaction_audit_logs_mutation();")