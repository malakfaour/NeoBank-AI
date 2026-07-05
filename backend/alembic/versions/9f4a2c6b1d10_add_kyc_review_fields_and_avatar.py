"""add kyc review fields and user avatar support

Revision ID: 9f4a2c6b1d10
Revises: 4d0a736e7bc0
Create Date: 2026-07-05 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9f4a2c6b1d10"
down_revision: Union[str, Sequence[str], None] = "4d0a736e7bc0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'KYC_APPROVED'")
        op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'KYC_FLAGGED'")
        op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'KYC_REJECTED'")

    op.add_column("users", sa.Column("avatar_url", sa.String(length=500), nullable=True))
    op.add_column("kyc_records", sa.Column("liveness_score", sa.Float(), nullable=True))
    op.add_column("kyc_records", sa.Column("rejection_reason", sa.String(length=255), nullable=True))
    op.add_column("kyc_records", sa.Column("reviewed_by", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_kyc_records_reviewed_by_users",
        "kyc_records",
        "users",
        ["reviewed_by"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_kyc_records_reviewed_by_users", "kyc_records", type_="foreignkey")
    op.drop_column("kyc_records", "reviewed_by")
    op.drop_column("kyc_records", "rejection_reason")
    op.drop_column("kyc_records", "liveness_score")
    op.drop_column("users", "avatar_url")
