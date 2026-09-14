"""create credit cards and bank schedules

Revision ID: d0f3b6c9a142
Revises: c9e2a4b6d830
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d0f3b6c9a142"
down_revision: str | Sequence[str] | None = "c9e2a4b6d830"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "credits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("bank", sa.String(128)),
        sa.Column("amount", sa.DECIMAL(15, 2), nullable=False),
        sa.Column("currency_code", sa.String(16), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("original_amount", sa.DECIMAL(15, 2)),
        sa.Column("annual_rate", sa.DECIMAL(9, 6)),
        sa.Column("monthly_payment", sa.DECIMAL(15, 2)),
        sa.Column("next_payment_date", sa.Date()),
        sa.Column("remaining_months", sa.Integer()),
        sa.Column("due_date", sa.Date()),
        sa.Column("repayment_terms", sa.String(2000)),
        sa.Column("description", sa.String(2000)),
        sa.Column("schedule_as_of_date", sa.Date()),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
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
        sa.ForeignKeyConstraint(
            ["currency_code"],
            ["currencies.code"],
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        sa.CheckConstraint("amount >= 0", name="ck_credit_amount"),
        sa.CheckConstraint("original_amount > 0", name="ck_credit_original_amount"),
        sa.CheckConstraint("annual_rate >= 0", name="ck_credit_annual_rate"),
        sa.CheckConstraint("monthly_payment > 0", name="ck_credit_monthly_payment"),
        sa.CheckConstraint(
            "remaining_months BETWEEN 0 AND 1200", name="ck_credit_months"
        ),
        sa.CheckConstraint("version > 0", name="ck_credit_version"),
    )
    op.create_table(
        "credit_payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("credit_id", sa.Integer(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.DECIMAL(15, 2), nullable=False),
        sa.Column("principal", sa.DECIMAL(15, 2)),
        sa.Column("interest", sa.DECIMAL(15, 2)),
        sa.Column("fees", sa.DECIMAL(15, 2)),
        sa.Column("remaining_amount", sa.DECIMAL(15, 2)),
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
        sa.ForeignKeyConstraint(["credit_id"], ["credits.id"], ondelete="CASCADE"),
        sa.CheckConstraint("amount > 0", name="ck_credit_payment_amount"),
        sa.CheckConstraint("principal >= 0", name="ck_credit_payment_principal"),
        sa.CheckConstraint("interest >= 0", name="ck_credit_payment_interest"),
        sa.CheckConstraint("fees >= 0", name="ck_credit_payment_fees"),
        sa.CheckConstraint("remaining_amount >= 0", name="ck_credit_payment_remaining"),
        sa.CheckConstraint(
            "coalesce(principal, 0) + coalesce(interest, 0) + coalesce(fees, 0) <= amount",
            name="ck_credit_payment_parts",
        ),
    )
    op.create_index("ix_credit_payments_credit_id", "credit_payments", ["credit_id"])


def downgrade() -> None:
    op.drop_table("credit_payments")
    op.drop_table("credits")
