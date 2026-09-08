from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DECIMAL,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from domain.enums import AccountType
from storage.models.abstract import AbstractModel


class Account(AbstractModel):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint(
            "(account_type = 'STANDARD' AND credit_limit IS NULL) OR "
            "(account_type = 'CREDIT' AND credit_limit IS NOT NULL AND credit_limit >= 0)",
            name="ck_account_credit_limit",
        ),
        CheckConstraint(
            "NOT is_default OR is_active", name="ck_account_default_active"
        ),
        Index(
            "uq_account_default",
            "is_default",
            unique=True,
            sqlite_where=text("is_default = 1"),
        ),
    )

    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    currency_code: Mapped[str] = mapped_column(
        String(16),
        ForeignKey("currencies.code", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    opening_balance: Mapped[Decimal] = mapped_column(DECIMAL(18, 2), nullable=False)
    account_type: Mapped[AccountType] = mapped_column(
        Enum(
            AccountType,
            name="account_type",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=AccountType.STANDARD,
        server_default="STANDARD",
        nullable=False,
    )
    credit_limit: Mapped[Decimal | None] = mapped_column(DECIMAL(18, 2), nullable=True)
    opening_balance_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("1"), nullable=False
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("0"), nullable=False
    )
