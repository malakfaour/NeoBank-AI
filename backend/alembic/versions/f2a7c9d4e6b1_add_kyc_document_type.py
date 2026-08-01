"""add document type to KYC records

Revision ID: f2a7c9d4e6b1
Revises: d5e91a4c7f38
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f2a7c9d4e6b1"
down_revision: Union[str, Sequence[str], None] = "d5e91a4c7f38"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("kyc_records")}

    if "document_type" in existing_columns:
        # b3f8a1c2d4e6 (a sibling branch merged into this history) already
        # added this column as NOT NULL - reconcile it to this migration's
        # intent (nullable, since a KYC record has no document type before
        # the applicant picks one) instead of trying to add it again.
        with op.batch_alter_table("kyc_records") as batch_op:
            batch_op.alter_column("document_type", nullable=True, server_default=None)
        return

    if bind.dialect.name == "postgresql":
        document_type_enum = postgresql.ENUM(
            "passport",
            "drivers_license",
            "national_id",
            name="kycdocumenttype",
        )
        document_type_enum.create(bind, checkfirst=True)
        column_type = postgresql.ENUM(
            "passport",
            "drivers_license",
            "national_id",
            name="kycdocumenttype",
            create_type=False,
        )
    else:
        column_type = sa.Enum(
            "passport",
            "drivers_license",
            "national_id",
            name="kycdocumenttype",
        )

    with op.batch_alter_table("kyc_records") as batch_op:
        batch_op.add_column(
            sa.Column("document_type", column_type, nullable=True)
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("kyc_records")}

    if "document_type" in existing_columns:
        with op.batch_alter_table("kyc_records") as batch_op:
            batch_op.drop_column("document_type")

    if bind.dialect.name == "postgresql":
        document_type_enum = postgresql.ENUM(
            "passport",
            "drivers_license",
            "national_id",
            name="kycdocumenttype",
        )
        document_type_enum.drop(bind, checkfirst=True)
