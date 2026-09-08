from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DECIMAL,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from storage.models.abstract import AbstractModel
from storage.models.account import Account
from storage.models.category import Category
from storage.models.currency import Currency


class ExpenseTransaction(AbstractModel):
    __tablename__ = "expense_transactions"
    __table_args__ = (
        Index(
            "ix_expense_transactions_account_occurred_at", "account_id", "occurred_at"
        ),
        CheckConstraint("amount > 0", name="ck_expense_amount_positive"),
    )

    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True
    )
    account: Mapped[Account | None] = relationship()

    name: Mapped[str] = mapped_column(String(length=128), nullable=False)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
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
    category: Mapped["Category"] = relationship()
