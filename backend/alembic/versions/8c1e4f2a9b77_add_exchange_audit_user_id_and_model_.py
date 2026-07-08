"""add exchange audit user_id and model_metrics

Revision ID: 8c1e4f2a9b77
Revises: 7f3d9c1a6e28
Create Date: 2026-07-08 12:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8c1e4f2a9b77"
down_revision: Union[str, Sequence[str], None] = "7f3d9c1a6e28"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("exchange_audit_logs") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f("ix_exchange_audit_logs_user_id"), ["user_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_exchange_audit_logs_user_id_users",
            "users",
            ["user_id"],
            ["id"],
        )

    op.create_table(
        "model_metrics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("mae", sa.Float(), nullable=False),
        sa.Column("trained_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_model_metrics_id"), "model_metrics", ["id"], unique=False)
    op.create_index(op.f("ix_model_metrics_model_name"), "model_metrics", ["model_name"], unique=False)
    op.create_index(op.f("ix_model_metrics_trained_at"), "model_metrics", ["trained_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_model_metrics_trained_at"), table_name="model_metrics")
    op.drop_index(op.f("ix_model_metrics_model_name"), table_name="model_metrics")
    op.drop_index(op.f("ix_model_metrics_id"), table_name="model_metrics")
    op.drop_table("model_metrics")

    with op.batch_alter_table("exchange_audit_logs") as batch_op:
        batch_op.drop_constraint("fk_exchange_audit_logs_user_id_users", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_exchange_audit_logs_user_id"))
        batch_op.drop_column("user_id")
