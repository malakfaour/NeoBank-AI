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
    if op.get_bind().dialect.name == "postgresql":
        document_type_enum = postgresql.ENUM(
            "passport",
            "drivers_license",
            "national_id",
            name="kycdocumenttype",
        )
        document_type_enum.create(op.get_bind(), checkfirst=True)
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
    with op.batch_alter_table("kyc_records") as batch_op:
        batch_op.drop_column("document_type")

    if op.get_bind().dialect.name == "postgresql":
        document_type_enum = postgresql.ENUM(
            "passport",
            "drivers_license",
            "national_id",
            name="kycdocumenttype",
        )
        document_type_enum.drop(op.get_bind(), checkfirst=True)
