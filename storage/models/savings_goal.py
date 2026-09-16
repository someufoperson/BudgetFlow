from datetime import date

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    Enum,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from domain.enums import SavingsGoalStatus
from storage.models.abstract import AbstractModel


class SavingsGoal(AbstractModel):
    __tablename__ = "savings_goals"
    __table_args__ = (
        CheckConstraint(
            "typeof(target_amount_minor) = 'integer' AND "
            "target_amount_minor BETWEEN 1 AND 999999999999999999",
            name="ck_savings_goal_target_amount",
        ),
        CheckConstraint("priority BETWEEN 1 AND 5", name="ck_savings_goal_priority"),
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    target_amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency_code: Mapped[str] = mapped_column(
        String(16),
        ForeignKey("currencies.code", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    priority: Mapped[int] = mapped_column(
        Integer, default=3, server_default="3", nullable=False
    )
    status: Mapped[SavingsGoalStatus] = mapped_column(
        Enum(
            SavingsGoalStatus,
            name="savings_goal_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=SavingsGoalStatus.ACTIVE,
        server_default="ACTIVE",
        nullable=False,
    )
