from datetime import date
from typing import TypedDict

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from domain.enums import SavingsGoalStatus
from storage.models.savings_goal import SavingsGoal


class SavingsGoalUpdates(TypedDict, total=False):
    name: str
    target_amount_minor: int
    due_date: date | None
    priority: int
    status: SavingsGoalStatus


class SavingsGoalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def begin_write(self) -> None:
        await self._session.execute(text("BEGIN IMMEDIATE"))

    async def begin_snapshot(self) -> None:
        await self._session.execute(text("BEGIN"))

    async def create(
        self,
        name: str,
        target_amount_minor: int,
        currency_code: str,
        due_date: date | None,
        priority: int,
    ) -> SavingsGoal:
        goal = SavingsGoal(
            name=name,
            target_amount_minor=target_amount_minor,
            currency_code=currency_code,
            due_date=due_date,
            priority=priority,
        )
        self._session.add(goal)
        await self._session.flush()
        return goal

    async def get_by_id(self, goal_id: int) -> SavingsGoal | None:
        return await self._session.scalar(
            select(SavingsGoal)
            .where(SavingsGoal.id == goal_id)
            .execution_options(populate_existing=True)
        )

    async def get_all(self) -> list[SavingsGoal]:
        return list(
            await self._session.scalars(
                select(SavingsGoal)
                .order_by(SavingsGoal.priority.desc(), SavingsGoal.id)
                .execution_options(populate_existing=True)
            )
        )

    async def update(
        self, goal_id: int, updates: SavingsGoalUpdates
    ) -> SavingsGoal | None:
        goal = await self.get_by_id(goal_id)
        if goal is None:
            return None
        for field, value in updates.items():
            if field not in SavingsGoalUpdates.__annotations__:
                raise ValueError(f"Field cannot be updated: {field}")
            setattr(goal, field, value)
        await self._session.flush()
        await self._session.refresh(goal)
        return goal
