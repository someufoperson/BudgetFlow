from datetime import date
from decimal import Decimal

from sqlalchemy import DECIMAL, CheckConstraint, Date, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from domain.enums import DebtDirection
from storage.models.abstract import AbstractModel
from storage.models.account import Account


class Debt(AbstractModel):
    __tablename__ = "debts"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_debt_amount_nonnegative"),
        CheckConstraint("priority BETWEEN 1 AND 5", name="ck_debt_priority"),
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    direction: Mapped[DebtDirection] = mapped_column(
        Enum(
            DebtDirection,
            name="debt_direction",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(DECIMAL(15, 2), nullable=False)
    currency_code: Mapped[str] = mapped_column(
        String(16),
        ForeignKey("currencies.code", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    priority: Mapped[int] = mapped_column(
        Integer, default=3, server_default="3", nullable=False
    )
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True
    )
    account: Mapped[Account | None] = relationship()
    counterparty: Mapped[str | None] = mapped_column(String(128), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
