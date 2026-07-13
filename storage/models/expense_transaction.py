from decimal import Decimal
from enum import Enum

from sqlalchemy import CheckConstraint, DECIMAL, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from storage.models.abstract import AbstractModel


class ExpenseType(Enum):
    eat = "EAT"
    transport = "TRANSPORT"
    travel = "TRAVEL"
    tooth = "TOOTH"
    subscribe = "SUBSCRIBE"
    rent = "RENT"
    sport = "SPORT"
    clothes = "CLOTHES"
    look = "LOOK"
    household = "HOUSEHOLD"
    cigarettes = "CIGARETTES"
    alcohol = "ALCOHOL"


class ExpenseTransaction(AbstractModel):
    __tablename__ = "expense_transactions"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_expense_amount_positive"),)

    name: Mapped[str] = mapped_column(String(length=128), nullable=False)
    expense_type: Mapped[ExpenseType] = mapped_column(nullable=False)
    amount: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), nullable=False)
    currency_id: Mapped[int] = mapped_column(
        ForeignKey("currencies.id", ondelete="RESTRICT"),
        nullable=False,
    )
