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
        CheckConstraint(
            "reversal_of_id IS NULL OR reversal_of_id != id",
            name="ck_adjustment_reversal_not_self",
        ),
        CheckConstraint(
            "(reversal_of_id IS NULL AND actual_balance IS NOT NULL AND reconciled_at IS NOT NULL) OR "
            "(reversal_of_id IS NOT NULL AND actual_balance IS NULL AND reconciled_at IS NULL)",
            name="ck_adjustment_reconciliation_fields",
        ),
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
    actual_balance: Mapped[Decimal | None] = mapped_column(
        DECIMAL(18, 2), nullable=True
    )
    reconciled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    description: Mapped[str] = mapped_column(String(512), nullable=False)
    confirmation_id: Mapped[str] = mapped_column(
        String(36), unique=True, nullable=False
    )
    reversal_of_id: Mapped[int | None] = mapped_column(
        ForeignKey("balance_adjustments.id", ondelete="RESTRICT"),
        unique=True,
        nullable=True,
    )
    original: Mapped["BalanceAdjustment | None"] = relationship(
        remote_side="BalanceAdjustment.id", back_populates="reversal"
    )
    reversal: Mapped["BalanceAdjustment | None"] = relationship(
        back_populates="original", uselist=False
    )

    @property
    def reversed_by_id(self) -> int | None:
        return self.reversal.id if self.reversal is not None else None
