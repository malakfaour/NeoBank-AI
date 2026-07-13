"""DEVATTECH-104 wallet lifecycle status and account status audit log

Revision ID: 1e652f5a22fd
Revises: 8c1e4f2a9b77
Create Date: 2026-07-08 12:59:18.034978

Single migration for the DEVATTECH-104 task cluster, per
ENGINEERING_RULES.md Section 2 ("Exactly ONE new revision per PR").

account_status_audit_logs follows the same append-only trigger pattern as
7f3d9c1a6e28 (transaction_audit_logs). transaction_audit_logs.transaction_id
is NOT NULL and cannot hold non-transactional lifecycle events
(freeze/unfreeze/close) -- rather than loosen a shared, trigger-protected
table's constraint, this adds a dedicated table for account-level events,
per team discussion on DEVATTECH-104.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '1e652f5a22fd'
down_revision: Union[str, Sequence[str], None] = 'a9c4f3e2b1d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- wallets.status ---
    op.add_column(
        'wallets',
        sa.Column(
            'status',
            sa.Enum('active', 'frozen', 'closed', name='walletstatus'),
            nullable=False,
            server_default='active',
        ),
    )

    # --- account_status_audit_logs ---
    op.create_table(
        'account_status_audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('wallet_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('actor_id', sa.Integer(), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'), nullable=True),
        sa.ForeignKeyConstraint(['wallet_id'], ['wallets.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_account_status_audit_logs_id'), 'account_status_audit_logs', ['id'], unique=False)
    op.create_index(op.f('ix_account_status_audit_logs_wallet_id'), 'account_status_audit_logs', ['wallet_id'], unique=False)
    op.create_index(op.f('ix_account_status_audit_logs_actor_id'), 'account_status_audit_logs', ['actor_id'], unique=False)

    # Postgres-only: SQLite test DB has no equivalent trigger/function syntax.
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION prevent_account_status_audit_logs_mutation()
            RETURNS TRIGGER AS $$
            BEGIN
                RAISE EXCEPTION 'account_status_audit_logs is append-only: % not allowed', TG_OP;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_account_status_audit_logs_no_update
            BEFORE UPDATE ON account_status_audit_logs
            FOR EACH ROW EXECUTE FUNCTION prevent_account_status_audit_logs_mutation();
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_account_status_audit_logs_no_delete
            BEFORE DELETE ON account_status_audit_logs
            FOR EACH ROW EXECUTE FUNCTION prevent_account_status_audit_logs_mutation();
            """
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_account_status_audit_logs_no_delete ON account_status_audit_logs;")
        op.execute("DROP TRIGGER IF EXISTS trg_account_status_audit_logs_no_update ON account_status_audit_logs;")
        op.execute("DROP FUNCTION IF EXISTS prevent_account_status_audit_logs_mutation();")

    op.drop_index(op.f('ix_account_status_audit_logs_actor_id'), table_name='account_status_audit_logs')
    op.drop_index(op.f('ix_account_status_audit_logs_wallet_id'), table_name='account_status_audit_logs')
    op.drop_index(op.f('ix_account_status_audit_logs_id'), table_name='account_status_audit_logs')
    op.drop_table('account_status_audit_logs')

    op.drop_column('wallets', 'status')

    walletstatus_enum = postgresql.ENUM('active', 'frozen', 'closed', name='walletstatus')
    walletstatus_enum.drop(op.get_bind(), checkfirst=True)
