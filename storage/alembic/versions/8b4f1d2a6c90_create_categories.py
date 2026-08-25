"""create categories and seed initial values

Revision ID: 8b4f1d2a6c90
Revises: c351ef005e00
Create Date: 2026-08-25 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8b4f1d2a6c90"
down_revision: str | Sequence[str] | None = "c351ef005e00"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


INITIAL_CATEGORIES = (
    ("EAT", "EXPENSE", "Продукты, кафе, рестораны и напитки"),
    ("TRANSPORT", "EXPENSE", "Такси, общественный транспорт и топливо"),
    ("TRAVEL", "EXPENSE", "Путешествия, билеты и отели"),
    ("TOOTH", "EXPENSE", "Стоматология"),
    ("SUBSCRIBE", "EXPENSE", "Подписки и цифровые сервисы"),
    ("RENT", "EXPENSE", "Аренда жилья"),
    ("SPORT", "EXPENSE", "Спорт и тренировки"),
    ("CLOTHES", "EXPENSE", "Одежда и обувь"),
    ("LOOK", "EXPENSE", "Косметика, парикмахерская и уход"),
    ("HOUSEHOLD", "EXPENSE", "Товары и расходы для дома"),
    ("CIGARETTES", "EXPENSE", "Сигареты"),
    ("ALCOHOL", "EXPENSE", "Алкоголь"),
    ("Прочие расходы", "EXPENSE", "Расходы без подходящей категории"),
    ("SALARY", "INCOME", "Заработная плата"),
    ("PERCENTAGEOFTHEDEPOSIT", "INCOME", "Проценты по вкладу"),
    ("PARTTIMEJOB", "INCOME", "Подработка"),
    ("GIFT", "INCOME", "Подарок или безвозмездно полученные деньги"),
    ("Прочие доходы", "INCOME", "Доходы без подходящей категории"),
)


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column(
            "direction",
            sa.Enum(
                "EXPENSE",
                "INCOME",
                name="category_type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("description", sa.String(length=512), nullable=True),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "name",
            "direction",
            name="uq_category_name_direction",
        ),
    )

    connection = op.get_bind()
    for name, direction, description in INITIAL_CATEGORIES:
        connection.execute(
            sa.text(
                """
                INSERT INTO categories (name, direction, description)
                SELECT :name, :direction, :description
                WHERE NOT EXISTS (
                    SELECT 1 FROM categories
                    WHERE name = :name AND direction = :direction
                )
                """
            ),
            {
                "name": name,
                "direction": direction,
                "description": description,
            },
        )


def downgrade() -> None:
    op.drop_table("categories")
