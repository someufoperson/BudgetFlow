"""create savings goals

Revision ID: e1a4c7f0b293
Revises: b8e3f6a9c142
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e1a4c7f0b293"
down_revision: str | Sequence[str] | None = "b8e3f6a9c142"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "savings_goals",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("target_amount_minor", sa.BigInteger(), nullable=False),
        sa.Column(
            "currency_code",
            sa.String(16),
            sa.ForeignKey("currencies.code", ondelete="RESTRICT", onupdate="CASCADE"),
            nullable=False,
        ),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("priority", sa.Integer(), server_default="3", nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE",
                "PAUSED",
                "ACHIEVED",
                name="savings_goal_status",
                native_enum=False,
                create_constraint=True,
            ),
            server_default="ACTIVE",
            nullable=False,
        ),
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
        sa.CheckConstraint(
            "typeof(target_amount_minor) = 'integer' AND "
            "target_amount_minor BETWEEN 1 AND 999999999999999999",
            name="ck_savings_goal_target_amount",
        ),
        sa.CheckConstraint("priority BETWEEN 1 AND 5", name="ck_savings_goal_priority"),
    )
    op.create_table(
        "savings_goal_allocations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "goal_id",
            sa.Integer(),
            sa.ForeignKey("savings_goals.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
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
        sa.CheckConstraint(
            "typeof(amount_minor) = 'integer' AND amount_minor != 0 AND "
            "amount_minor BETWEEN -999999999999999999 AND 999999999999999999",
            name="ck_savings_goal_allocation_amount",
        ),
    )
    op.create_index(
        "ix_savings_goal_allocation_goal_account",
        "savings_goal_allocations",
        ["goal_id", "account_id"],
    )
    op.create_index(
        "ix_savings_goal_allocation_account", "savings_goal_allocations", ["account_id"]
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT COUNT(*) FROM savings_goals")
    ) or op.get_bind().scalar(sa.text("SELECT COUNT(*) FROM savings_goal_allocations")):
        raise ValueError("Cannot downgrade while savings goals or allocations exist")
    op.drop_table("savings_goal_allocations")
    op.drop_table("savings_goals")
