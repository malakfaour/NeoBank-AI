"""add email verification to users

Revision ID: 6a4d2f8c1b90
Revises: f2a7c9d4e6b1
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "6a4d2f8c1b90"
down_revision: str | Sequence[str] | None = "f2a7c9d4e6b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Accounts created before email verification existed retain access.
    # New registrations explicitly start with NULL until OTP verification.
    op.execute(
        "UPDATE users SET email_verified_at = CURRENT_TIMESTAMP "
        "WHERE email_verified_at IS NULL"
    )


def downgrade() -> None:
    op.drop_column("users", "email_verified_at")
