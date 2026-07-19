from decimal import Decimal

from sqlalchemy import CheckConstraint, DECIMAL, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from domain.enums import IncomingType
from storage.models.abstract import AbstractModel
from storage.models.currency import Currency


class IncomingTransaction(AbstractModel):
    __tablename__ = "incoming_transactions"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_income_amount_positive"),)

    name: Mapped[str] = mapped_column(String(length=128), nullable=False)
    incoming_type: Mapped[IncomingType] = mapped_column(nullable=False)
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
