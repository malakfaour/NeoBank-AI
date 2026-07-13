"""DEVATTECH-102 KYC queue hardening and decision audit

Revision ID: c8d4e6f1a2b3
Revises: b7e9d2c4f6a1
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c8d4e6f1a2b3"
down_revision: Union[str, Sequence[str], None] = "b7e9d2c4f6a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "kyc_records",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE kyc_records SET created_at = COALESCE(reviewed_at, CURRENT_TIMESTAMP)"
    )
    with op.batch_alter_table("kyc_records") as batch_op:
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        )

    op.create_table(
        "kyc_audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kyc_record_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["kyc_record_id"], ["kyc_records.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_kyc_audit_logs_id"), "kyc_audit_logs", ["id"])
    op.create_index(
        op.f("ix_kyc_audit_logs_kyc_record_id"),
        "kyc_audit_logs",
        ["kyc_record_id"],
    )
    op.create_index(
        op.f("ix_kyc_audit_logs_actor_id"), "kyc_audit_logs", ["actor_id"]
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION prevent_kyc_audit_logs_mutation()
            RETURNS TRIGGER AS $$
            BEGIN
                RAISE EXCEPTION 'kyc_audit_logs is append-only: % not allowed', TG_OP;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_kyc_audit_logs_no_update
            BEFORE UPDATE ON kyc_audit_logs
            FOR EACH ROW EXECUTE FUNCTION prevent_kyc_audit_logs_mutation();
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_kyc_audit_logs_no_delete
            BEFORE DELETE ON kyc_audit_logs
            FOR EACH ROW EXECUTE FUNCTION prevent_kyc_audit_logs_mutation();
            """
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_kyc_audit_logs_no_delete ON kyc_audit_logs")
        op.execute("DROP TRIGGER IF EXISTS trg_kyc_audit_logs_no_update ON kyc_audit_logs")
        op.execute("DROP FUNCTION IF EXISTS prevent_kyc_audit_logs_mutation()")

    op.drop_index(op.f("ix_kyc_audit_logs_actor_id"), table_name="kyc_audit_logs")
    op.drop_index(op.f("ix_kyc_audit_logs_kyc_record_id"), table_name="kyc_audit_logs")
    op.drop_index(op.f("ix_kyc_audit_logs_id"), table_name="kyc_audit_logs")
    op.drop_table("kyc_audit_logs")
    with op.batch_alter_table("kyc_records") as batch_op:
        batch_op.drop_column("created_at")
