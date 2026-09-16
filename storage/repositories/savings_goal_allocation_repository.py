from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from storage.models.savings_goal_allocation import SavingsGoalAllocation


class SavingsGoalAllocationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, goal_id: int, account_id: int, amount_minor: int
    ) -> SavingsGoalAllocation:
        allocation = SavingsGoalAllocation(
            goal_id=goal_id, account_id=account_id, amount_minor=amount_minor
        )
        self._session.add(allocation)
        await self._session.flush()
        return allocation

    async def get_all(
        self, *, goal_id: int | None = None, account_id: int | None = None
    ) -> list[SavingsGoalAllocation]:
        stmt = select(SavingsGoalAllocation)
        if goal_id is not None:
            stmt = stmt.where(SavingsGoalAllocation.goal_id == goal_id)
        if account_id is not None:
            stmt = stmt.where(SavingsGoalAllocation.account_id == account_id)
        return list(
            await self._session.scalars(
                stmt.order_by(SavingsGoalAllocation.id).execution_options(
                    populate_existing=True
                )
            )
        )
