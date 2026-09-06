"""add normalized category names

Revision ID: f2c4a6e8b190
Revises: d4e7a91b3f25
Create Date: 2026-08-30 00:00:00.000000

"""

from collections import defaultdict
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection, Row

revision: str = "f2c4a6e8b190"
down_revision: str | Sequence[str] | None = "d4e7a91b3f25"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _normalized_category_name(name: str) -> str:
    return " ".join(name.split()).casefold()


def _category_rows(connection: Connection) -> list[Row[tuple[int, str, str]]]:
    return list(
        connection.execute(
            sa.text("SELECT id, name, direction FROM categories ORDER BY id")
        )
    )


def _raise_for_conflicts(
    rows: list[Row[tuple[int, str, str]]],
) -> None:
    categories_by_key: dict[tuple[str, str], list[tuple[int, str]]] = defaultdict(list)
    for category_id, name, direction in rows:
        key = (_normalized_category_name(name), direction)
        categories_by_key[key].append((category_id, name))

    conflicts = {
        key: categories
        for key, categories in categories_by_key.items()
        if len(categories) > 1
    }
    if not conflicts:
        return

    details = "; ".join(
        f"direction={direction}, normalized_name={normalized_name!r}: "
        + ", ".join(f"id={category_id}, name={name!r}" for category_id, name in rows)
        for (normalized_name, direction), rows in sorted(conflicts.items())
    )
    raise RuntimeError(
        "Cannot add normalized category uniqueness because conflicting categories "
        f"exist: {details}"
    )


def upgrade() -> None:
    connection = op.get_bind()
    rows = _category_rows(connection)
    _raise_for_conflicts(rows)

    with op.batch_alter_table("categories") as batch_op:
        batch_op.add_column(
            sa.Column("normalized_name", sa.String(length=192), nullable=True)
        )

    if rows:
        connection.execute(
            sa.text(
                "UPDATE categories "
                "SET normalized_name = :normalized_name WHERE id = :id"
            ),
            [
                {
                    "id": category_id,
                    "normalized_name": _normalized_category_name(name),
                }
                for category_id, name, _direction in rows
            ],
        )

    with op.batch_alter_table("categories") as batch_op:
        batch_op.alter_column(
            "normalized_name",
            existing_type=sa.String(length=192),
            nullable=False,
        )
        batch_op.drop_constraint("uq_category_name_direction", type_="unique")
        batch_op.create_unique_constraint(
            "uq_category_normalized_name_direction",
            ["normalized_name", "direction"],
        )


def downgrade() -> None:
    with op.batch_alter_table("categories") as batch_op:
        batch_op.drop_constraint(
            "uq_category_normalized_name_direction",
            type_="unique",
        )
        batch_op.create_unique_constraint(
            "uq_category_name_direction",
            ["name", "direction"],
        )
        batch_op.drop_column("normalized_name")
