from decimal import Decimal
from enum import Enum

from sqlalchemy import CheckConstraint, DECIMAL, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from storage.models.abstract import AbstractModel


class IncomingType(Enum):
    salary = "SALARY"
    percentage_of_the_deposit = "PERCENTAGEOFTHEDEPOSIT"
    part_time_job = "PARTTIMEJOB"
    gift = "GIFT"


class IncomingTransaction(AbstractModel):
    __tablename__ = "incoming_transactions"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_income_amount_positive"),)

    name: Mapped[str] = mapped_column(String(length=128), nullable=False)
    incoming_type: Mapped[IncomingType] = mapped_column(nullable=False)
    amount: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), nullable=False)
    currency_id: Mapped[int] = mapped_column(
        ForeignKey("currencies.id", ondelete="RESTRICT"),
        nullable=False,
    )
