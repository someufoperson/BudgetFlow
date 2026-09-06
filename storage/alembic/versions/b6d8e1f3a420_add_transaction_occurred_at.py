"""add transaction occurrence time

Revision ID: b6d8e1f3a420
Revises: a3e5c7b9d210
Create Date: 2026-08-31 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b6d8e1f3a420"
down_revision: str | Sequence[str] | None = "a3e5c7b9d210"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TRANSACTION_TABLES = ("expense_transactions", "incoming_transactions")


def upgrade() -> None:
    for table_name in _TRANSACTION_TABLES:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "occurred_at",
                    sa.DateTime(timezone=True),
                    server_default=sa.func.now(),
                    nullable=True,
                )
            )

        op.execute(sa.text(f"UPDATE {table_name} SET occurred_at = created_at"))

        with op.batch_alter_table(table_name) as batch_op:
            batch_op.alter_column(
                "occurred_at",
                existing_type=sa.DateTime(timezone=True),
                existing_server_default=sa.func.now(),
                nullable=False,
            )
            batch_op.create_index(
                f"ix_{table_name}_occurred_at",
                ["occurred_at"],
                unique=False,
            )


def downgrade() -> None:
    for table_name in reversed(_TRANSACTION_TABLES):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_index(f"ix_{table_name}_occurred_at")
            batch_op.drop_column("occurred_at")
