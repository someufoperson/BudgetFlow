from datetime import datetime
from decimal import Decimal

from sqlalchemy import DECIMAL, CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from storage.models.abstract import AbstractModel
from storage.models.account import Account


class BalanceAdjustment(AbstractModel):
    __tablename__ = "balance_adjustments"
    __table_args__ = (
        CheckConstraint("amount != 0", name="ck_adjustment_amount_nonzero"),
        Index("ix_adjustment_account_occurred_at", "account_id", "occurred_at"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    account: Mapped[Account] = relationship()
    currency_code: Mapped[str] = mapped_column(
        String(16),
        ForeignKey("currencies.code", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), nullable=False)
    calculated_balance: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), nullable=False)
    actual_balance: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), nullable=False)
    reconciled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    description: Mapped[str] = mapped_column(String(512), nullable=False)
    confirmation_id: Mapped[str] = mapped_column(
        String(36), unique=True, nullable=False
    )
