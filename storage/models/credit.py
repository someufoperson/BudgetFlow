from datetime import date
from decimal import Decimal

from sqlalchemy import DECIMAL, CheckConstraint, Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from storage.models.abstract import AbstractModel


class Credit(AbstractModel):
    __tablename__ = "credits"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_credit_amount"),
        CheckConstraint("original_amount > 0", name="ck_credit_original_amount"),
        CheckConstraint("annual_rate >= 0", name="ck_credit_annual_rate"),
        CheckConstraint("monthly_payment > 0", name="ck_credit_monthly_payment"),
        CheckConstraint("remaining_months BETWEEN 0 AND 1200", name="ck_credit_months"),
        CheckConstraint("version > 0", name="ck_credit_version"),
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    bank: Mapped[str | None] = mapped_column(String(128))
    amount: Mapped[Decimal] = mapped_column(DECIMAL(15, 2), nullable=False)
    currency_code: Mapped[str] = mapped_column(
        String(16),
        ForeignKey("currencies.code", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    original_amount: Mapped[Decimal | None] = mapped_column(DECIMAL(15, 2))
    annual_rate: Mapped[Decimal | None] = mapped_column(DECIMAL(9, 6))
    monthly_payment: Mapped[Decimal | None] = mapped_column(DECIMAL(15, 2))
    next_payment_date: Mapped[date | None] = mapped_column(Date)
    remaining_months: Mapped[int | None] = mapped_column(Integer)
    due_date: Mapped[date | None] = mapped_column(Date)
    repayment_terms: Mapped[str | None] = mapped_column(String(2000))
    description: Mapped[str | None] = mapped_column(String(2000))
    schedule_as_of_date: Mapped[date | None] = mapped_column(Date)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    schedule: Mapped[list["CreditPayment"]] = relationship(
        order_by="CreditPayment.due_date", cascade="all, delete-orphan"
    )


class CreditPayment(AbstractModel):
    __tablename__ = "credit_payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_credit_payment_amount"),
        CheckConstraint("principal >= 0", name="ck_credit_payment_principal"),
        CheckConstraint("interest >= 0", name="ck_credit_payment_interest"),
        CheckConstraint("fees >= 0", name="ck_credit_payment_fees"),
        CheckConstraint("remaining_amount >= 0", name="ck_credit_payment_remaining"),
        CheckConstraint(
            "coalesce(principal, 0) + coalesce(interest, 0) + coalesce(fees, 0) <= amount",
            name="ck_credit_payment_parts",
        ),
    )

    credit_id: Mapped[int] = mapped_column(
        ForeignKey("credits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(DECIMAL(15, 2), nullable=False)
    principal: Mapped[Decimal | None] = mapped_column(DECIMAL(15, 2))
    interest: Mapped[Decimal | None] = mapped_column(DECIMAL(15, 2))
    fees: Mapped[Decimal | None] = mapped_column(DECIMAL(15, 2))
    remaining_amount: Mapped[Decimal | None] = mapped_column(DECIMAL(15, 2))
