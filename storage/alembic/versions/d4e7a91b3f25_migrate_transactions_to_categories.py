"""migrate transactions to dynamic categories

Revision ID: d4e7a91b3f25
Revises: 8b4f1d2a6c90
Create Date: 2026-08-25 00:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e7a91b3f25"
down_revision: str | Sequence[str] | None = "8b4f1d2a6c90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


EXPENSE_CATEGORY_BY_OLD_VALUE = {
    "eat": "EAT",
    "transport": "TRANSPORT",
    "travel": "TRAVEL",
    "tooth": "TOOTH",
    "subscribe": "SUBSCRIBE",
    "rent": "RENT",
    "sport": "SPORT",
    "clothes": "CLOTHES",
    "look": "LOOK",
    "household": "HOUSEHOLD",
    "cigarettes": "CIGARETTES",
    "alcohol": "ALCOHOL",
}

INCOME_CATEGORY_BY_OLD_VALUE = {
    "salary": "SALARY",
    "percentage_of_the_deposit": "PERCENTAGEOFTHEDEPOSIT",
    "part_time_job": "PARTTIMEJOB",
    "gift": "GIFT",
}


def _category_case(column: str, mapping: dict[str, str]) -> str:
    branches = " ".join(
        f"WHEN '{old}' THEN '{new}' WHEN '{old.upper()}' THEN '{new}'"
        for old, new in mapping.items()
    )
    return f"CASE {column} {branches} END"


def _populate_category_ids(
    table: str,
    old_column: str,
    direction: str,
    mapping: dict[str, str],
) -> None:
    category_name = _category_case(old_column, mapping)
    connection = op.get_bind()
    connection.execute(
        sa.text(
            f"""
            UPDATE {table}
            SET category_id = (
                SELECT categories.id
                FROM categories
                WHERE categories.direction = :direction
                  AND categories.name = {category_name}
            )
            """
        ),
        {"direction": direction},
    )

    missing = connection.scalar(
        sa.text(f"SELECT COUNT(*) FROM {table} WHERE category_id IS NULL")
    )
    if missing:
        raise RuntimeError(
            f"Cannot migrate {missing} rows from {table}: category mapping is missing"
        )


def upgrade() -> None:
    with op.batch_alter_table("expense_transactions") as batch_op:
        batch_op.add_column(sa.Column("category_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_expense_transactions_category_id_categories",
            "categories",
            ["category_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    with op.batch_alter_table("incoming_transactions") as batch_op:
        batch_op.add_column(sa.Column("category_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_incoming_transactions_category_id_categories",
            "categories",
            ["category_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    _populate_category_ids(
        "expense_transactions",
        "expense_type",
        "EXPENSE",
        EXPENSE_CATEGORY_BY_OLD_VALUE,
    )
    _populate_category_ids(
        "incoming_transactions",
        "incoming_type",
        "INCOME",
        INCOME_CATEGORY_BY_OLD_VALUE,
    )

    with op.batch_alter_table("expense_transactions") as batch_op:
        batch_op.alter_column("category_id", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column("expense_type")

    with op.batch_alter_table("incoming_transactions") as batch_op:
        batch_op.alter_column("category_id", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column("incoming_type")


def _restore_old_values(
    table: str,
    old_column: str,
    mapping: dict[str, str],
) -> None:
    reverse_mapping = {category: old for old, category in mapping.items()}
    branches = " ".join(
        f"WHEN '{category}' THEN '{old}'" for category, old in reverse_mapping.items()
    )
    connection = op.get_bind()
    connection.execute(
        sa.text(
            f"""
            UPDATE {table}
            SET {old_column} = (
                SELECT CASE categories.name {branches} END
                FROM categories
                WHERE categories.id = {table}.category_id
            )
            """
        )
    )
    missing = connection.scalar(
        sa.text(f"SELECT COUNT(*) FROM {table} WHERE {old_column} IS NULL")
    )
    if missing:
        raise RuntimeError(
            f"Cannot downgrade {missing} rows from {table}: legacy enum has no value"
        )


def downgrade() -> None:
    expense_enum = sa.Enum(*EXPENSE_CATEGORY_BY_OLD_VALUE, name="expensetype")
    income_enum = sa.Enum(*INCOME_CATEGORY_BY_OLD_VALUE, name="incomingtype")

    with op.batch_alter_table("expense_transactions") as batch_op:
        batch_op.add_column(
            sa.Column("expense_type", expense_enum, nullable=True),
        )
    with op.batch_alter_table("incoming_transactions") as batch_op:
        batch_op.add_column(
            sa.Column("incoming_type", income_enum, nullable=True),
        )

    _restore_old_values(
        "expense_transactions",
        "expense_type",
        EXPENSE_CATEGORY_BY_OLD_VALUE,
    )
    _restore_old_values(
        "incoming_transactions",
        "incoming_type",
        INCOME_CATEGORY_BY_OLD_VALUE,
    )

    with op.batch_alter_table("expense_transactions") as batch_op:
        batch_op.alter_column(
            "expense_type",
            existing_type=expense_enum,
            nullable=False,
        )
        batch_op.drop_constraint(
            "fk_expense_transactions_category_id_categories",
            type_="foreignkey",
        )
        batch_op.drop_column("category_id")

    with op.batch_alter_table("incoming_transactions") as batch_op:
        batch_op.alter_column(
            "incoming_type",
            existing_type=income_enum,
            nullable=False,
        )
        batch_op.drop_constraint(
            "fk_incoming_transactions_category_id_categories",
            type_="foreignkey",
        )
        batch_op.drop_column("category_id")
