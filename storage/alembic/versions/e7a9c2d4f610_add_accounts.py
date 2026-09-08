"""add accounts and optional transaction links

Revision ID: e7a9c2d4f610
Revises: b6d8e1f3a420
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7a9c2d4f610"
down_revision: str | Sequence[str] | None = "b6d8e1f3a420"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TRANSACTION_TABLES = ("expense_transactions", "incoming_transactions")


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "currency_code",
            sa.String(16),
            sa.ForeignKey("currencies.code", ondelete="RESTRICT", onupdate="CASCADE"),
            nullable=False,
        ),
        sa.Column("opening_balance", sa.DECIMAL(18, 2), nullable=False),
        sa.Column("opening_balance_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")
        ),
        sa.Column(
            "is_default", sa.Boolean(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "NOT is_default OR is_active", name="ck_account_default_active"
        ),
    )
    op.create_index(
        "uq_account_default",
        "accounts",
        ["is_default"],
        unique=True,
        sqlite_where=sa.text("is_default = 1"),
    )
    for table_name in _TRANSACTION_TABLES:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(sa.Column("account_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                f"fk_{table_name}_account",
                "accounts",
                ["account_id"],
                ["id"],
                ondelete="RESTRICT",
            )
            batch_op.create_index(
                f"ix_{table_name}_account_occurred_at", ["account_id", "occurred_at"]
            )


def downgrade() -> None:
    for table_name in reversed(_TRANSACTION_TABLES):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_index(f"ix_{table_name}_account_occurred_at")
            batch_op.drop_constraint(f"fk_{table_name}_account", type_="foreignkey")
            batch_op.drop_column("account_id")
    op.drop_index("uq_account_default", table_name="accounts")
    op.drop_table("accounts")
