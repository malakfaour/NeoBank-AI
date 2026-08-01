"""add resumable KYC profile fields

Revision ID: 7a3c1f2e9b40
Revises: 465a86435043
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "7a3c1f2e9b40"
down_revision = "465a86435043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("kyc_records", sa.Column("back_id_photo_url", sa.String(500)))
    op.add_column(
        "kyc_records",
        sa.Column(
            "profile_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "kyc_records",
        sa.Column("current_step", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "kyc_records",
        sa.Column("is_submitted", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "kyc_records",
        sa.Column("terms_accepted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "kyc_records",
        sa.Column("information_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "kyc_records",
        sa.Column("privacy_consent", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("kyc_records", sa.Column("submitted_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    for column in (
        "submitted_at",
        "privacy_consent",
        "information_confirmed",
        "terms_accepted",
        "is_submitted",
        "current_step",
        "profile_data",
        "back_id_photo_url",
    ):
        op.drop_column("kyc_records", column)
