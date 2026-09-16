from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from storage.models.abstract import AbstractModel


class SavingsGoalAllocation(AbstractModel):
    __tablename__ = "savings_goal_allocations"
    __table_args__ = (
        CheckConstraint(
            "typeof(amount_minor) = 'integer' AND amount_minor != 0 AND "
            "amount_minor BETWEEN -999999999999999999 AND 999999999999999999",
            name="ck_savings_goal_allocation_amount",
        ),
        Index("ix_savings_goal_allocation_goal_account", "goal_id", "account_id"),
        Index("ix_savings_goal_allocation_account", "account_id"),
    )

    goal_id: Mapped[int] = mapped_column(
        ForeignKey("savings_goals.id", ondelete="RESTRICT"), nullable=False
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
