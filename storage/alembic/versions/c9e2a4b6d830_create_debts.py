"""create debt register

Revision ID: c9e2a4b6d830
Revises: f8b0d3e5a721
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9e2a4b6d830"
down_revision: str | Sequence[str] | None = "f8b0d3e5a721"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "debts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("amount", sa.DECIMAL(15, 2), nullable=False),
        sa.Column("currency_code", sa.String(16), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("priority", sa.Integer(), server_default="3", nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("counterparty", sa.String(128), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("description", sa.String(512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["currency_code"],
            ["currencies.code"],
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("amount >= 0", name="ck_debt_amount_nonnegative"),
        sa.CheckConstraint("priority BETWEEN 1 AND 5", name="ck_debt_priority"),
        sa.CheckConstraint(
            "direction IN ('PAYABLE', 'RECEIVABLE')", name="debt_direction"
        ),
    )


def downgrade() -> None:
    op.drop_table("debts")
