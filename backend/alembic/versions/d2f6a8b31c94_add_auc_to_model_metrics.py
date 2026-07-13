"""add auc to model_metrics and relax mae to nullable

Revision ID: d2f6a8b31c94
Revises: 8c1e4f2a9b77
Create Date: 2026-07-08 13:00:00.000000

DEVATTECH-89: model_metrics needs to support classification models
(XGBoost fraud -- AUC) alongside the existing regression model
(LightGBM exchange forecast -- MAE). model_metrics is a generic,
multi-model table -- app/api/v1/endpoints/admin.py's
get_latest_model_metrics endpoint already groups by model_name across
models, so this is an additive/compatible schema change, not an
exclusive-ownership violation.

Only model_metrics is modified. No other table (including
exchange_audit_logs, touched by the parent revision) is touched here.

Hand-written, not raw `alembic revision --autogenerate` output, per
ENGINEERING_RULES.md section 2.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d2f6a8b31c94"
down_revision: Union[str, Sequence[str], None] = "8c1e4f2a9b77"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("model_metrics") as batch_op:
        batch_op.add_column(sa.Column("auc", sa.Float(), nullable=True))
        batch_op.alter_column("mae", existing_type=sa.Float(), nullable=True)


def downgrade() -> None:
    # NOTE: reverting mae to NOT NULL will fail if any row has mae=NULL
    # (e.g. an xgboost row logged after this migration's upgrade()) --
    # such rows must be cleaned up or backfilled before this downgrade
    # can run.
    with op.batch_alter_table("model_metrics") as batch_op:
        batch_op.alter_column("mae", existing_type=sa.Float(), nullable=False)
        batch_op.drop_column("auc")
