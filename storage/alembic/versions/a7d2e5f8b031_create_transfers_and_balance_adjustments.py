"""create transfers and balance adjustments

Revision ID: a7d2e5f8b031
Revises: d0f3b6c9a142
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7d2e5f8b031"
down_revision: str | Sequence[str] | None = "d0f3b6c9a142"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "transfer_transactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_account_id", sa.Integer(), nullable=False),
        sa.Column("destination_account_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.DECIMAL(18, 2), nullable=False),
        sa.Column("currency_code", sa.String(16), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
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
            ["source_account_id"], ["accounts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["destination_account_id"], ["accounts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["currency_code"],
            ["currencies.code"],
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        sa.CheckConstraint("amount > 0", name="ck_transfer_amount_positive"),
        sa.CheckConstraint(
            "source_account_id != destination_account_id", name="ck_transfer_accounts"
        ),
    )
    op.create_index(
        "ix_transfer_source_occurred_at",
        "transfer_transactions",
        ["source_account_id", "occurred_at"],
    )
    op.create_index(
        "ix_transfer_destination_occurred_at",
        "transfer_transactions",
        ["destination_account_id", "occurred_at"],
    )
    op.create_table(
        "balance_adjustments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("currency_code", sa.String(16), nullable=False),
        sa.Column("amount", sa.DECIMAL(18, 2), nullable=False),
        sa.Column("calculated_balance", sa.DECIMAL(18, 2), nullable=False),
        sa.Column("actual_balance", sa.DECIMAL(18, 2), nullable=False),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("description", sa.String(512), nullable=False),
        sa.Column("confirmation_id", sa.String(36), nullable=False),
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
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["currency_code"],
            ["currencies.code"],
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        sa.UniqueConstraint("confirmation_id"),
        sa.CheckConstraint("amount != 0", name="ck_adjustment_amount_nonzero"),
    )
    op.create_index(
        "ix_adjustment_account_occurred_at",
        "balance_adjustments",
        ["account_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_table("balance_adjustments")
    op.drop_table("transfer_transactions")
