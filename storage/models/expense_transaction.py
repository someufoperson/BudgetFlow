from decimal import Decimal

from sqlalchemy import CheckConstraint, DECIMAL, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from domain.enums import ExpenseType
from storage.models.abstract import AbstractModel
from storage.models.currency import Currency


class ExpenseTransaction(AbstractModel):
    __tablename__ = "expense_transactions"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_expense_amount_positive"),)

    name: Mapped[str] = mapped_column(String(length=128), nullable=False)
    expense_type: Mapped[ExpenseType] = mapped_column(nullable=False)
    amount: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), nullable=False)
    currency_code: Mapped[str] = mapped_column(
        String(16),
        ForeignKey(
            "currencies.code",
            ondelete="RESTRICT",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    currency: Mapped["Currency"] = relationship()
