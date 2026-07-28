"""add document_type to kyc_records

Revision ID: b3f8a1c2d4e6
Revises: 8c1e4f2a9b77
Create Date: 2026-07-28 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b3f8a1c2d4e6"
down_revision: Union[str, Sequence[str], None] = "8c1e4f2a9b77"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

kyc_document_type = sa.Enum(
    "national_id", "passport", "drivers_license", name="kycdocumenttype"
)


def upgrade() -> None:
    bind = op.get_bind()
    kyc_document_type.create(bind, checkfirst=True)
    op.add_column(
        "kyc_records",
        sa.Column(
            "document_type",
            kyc_document_type,
            nullable=False,
            server_default="national_id",
        ),
    )
    op.alter_column("kyc_records", "document_type", server_default=None)


def downgrade() -> None:
    op.drop_column("kyc_records", "document_type")
    kyc_document_type.drop(op.get_bind(), checkfirst=True)
