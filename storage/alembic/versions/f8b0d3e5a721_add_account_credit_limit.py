"""add account types and credit limits

Revision ID: f8b0d3e5a721
Revises: e7a9c2d4f610
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f8b0d3e5a721"
down_revision: str | Sequence[str] | None = "e7a9c2d4f610"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column(
            "account_type",
            sa.String(8),
            sa.CheckConstraint(
                "account_type IN ('STANDARD', 'CREDIT')", name="account_type"
            ),
            nullable=False,
            server_default="STANDARD",
        ),
    )
    op.add_column(
        "accounts",
        sa.Column(
            "credit_limit",
            sa.DECIMAL(18, 2),
            sa.CheckConstraint(
                "(account_type = 'STANDARD' AND credit_limit IS NULL) OR "
                "(account_type = 'CREDIT' AND credit_limit IS NOT NULL AND credit_limit >= 0)",
                name="ck_account_credit_limit",
            ),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE accounts DROP COLUMN credit_limit"))
    op.execute(sa.text("ALTER TABLE accounts DROP COLUMN account_type"))
