"""add balance adjustment reversals

Revision ID: b8e3f6a9c142
Revises: a7d2e5f8b031
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8e3f6a9c142"
down_revision: str | Sequence[str] | None = "a7d2e5f8b031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("balance_adjustments") as batch:
        batch.add_column(sa.Column("reversal_of_id", sa.Integer(), nullable=True))
        batch.alter_column(
            "actual_balance", existing_type=sa.DECIMAL(18, 2), nullable=True
        )
        batch.alter_column(
            "reconciled_at", existing_type=sa.DateTime(timezone=True), nullable=True
        )
        batch.create_foreign_key(
            "fk_adjustment_reversal",
            "balance_adjustments",
            ["reversal_of_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_unique_constraint("uq_adjustment_reversal", ["reversal_of_id"])
        batch.create_check_constraint(
            "ck_adjustment_reversal_not_self",
            "reversal_of_id IS NULL OR reversal_of_id != id",
        )
        batch.create_check_constraint(
            "ck_adjustment_reconciliation_fields",
            "(reversal_of_id IS NULL AND actual_balance IS NOT NULL AND reconciled_at IS NOT NULL) OR "
            "(reversal_of_id IS NOT NULL AND actual_balance IS NULL AND reconciled_at IS NULL)",
        )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT COUNT(*) FROM balance_adjustments WHERE reversal_of_id IS NOT NULL"
        )
    ):
        raise ValueError("Cannot downgrade while adjustment reversals exist")
    with op.batch_alter_table("balance_adjustments") as batch:
        batch.drop_constraint("ck_adjustment_reconciliation_fields", type_="check")
        batch.drop_constraint("ck_adjustment_reversal_not_self", type_="check")
        batch.drop_constraint("uq_adjustment_reversal", type_="unique")
        batch.drop_constraint("fk_adjustment_reversal", type_="foreignkey")
        batch.drop_column("reversal_of_id")
        batch.alter_column(
            "actual_balance", existing_type=sa.DECIMAL(18, 2), nullable=False
        )
        batch.alter_column(
            "reconciled_at", existing_type=sa.DateTime(timezone=True), nullable=False
        )
