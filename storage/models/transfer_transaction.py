from datetime import datetime
from decimal import Decimal

from sqlalchemy import DECIMAL, CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from storage.models.abstract import AbstractModel
from storage.models.account import Account


class TransferTransaction(AbstractModel):
    __tablename__ = "transfer_transactions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_transfer_amount_positive"),
        CheckConstraint(
            "source_account_id != destination_account_id", name="ck_transfer_accounts"
        ),
        Index("ix_transfer_source_occurred_at", "source_account_id", "occurred_at"),
        Index(
            "ix_transfer_destination_occurred_at",
            "destination_account_id",
            "occurred_at",
        ),
    )

    source_account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    destination_account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    source_account: Mapped[Account] = relationship(foreign_keys=[source_account_id])
    destination_account: Mapped[Account] = relationship(
        foreign_keys=[destination_account_id]
    )
    amount: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), nullable=False)
    currency_code: Mapped[str] = mapped_column(
        String(16),
        ForeignKey("currencies.code", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
