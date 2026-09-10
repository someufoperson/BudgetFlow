from datetime import date
from decimal import Decimal
from typing import TypedDict

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from domain.enums import DebtDirection
from storage.models.debt import Debt


class DebtUpdates(TypedDict, total=False):
    name: str
    direction: DebtDirection
    amount: Decimal
    currency_code: str
    as_of_date: date
    priority: int
    account_id: int | None
    counterparty: str | None
    due_date: date | None
    description: str | None


class DebtRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        name: str,
        direction: DebtDirection,
        amount: Decimal,
        currency_code: str,
        as_of_date: date,
        priority: int,
        account_id: int | None,
        counterparty: str | None,
        due_date: date | None,
        description: str | None,
    ) -> Debt:
        debt = Debt(
            name=name,
            direction=direction,
            amount=amount,
            currency_code=currency_code,
            as_of_date=as_of_date,
            priority=priority,
            account_id=account_id,
            counterparty=counterparty,
            due_date=due_date,
            description=description,
        )
        self._session.add(debt)
        await self._session.flush()
        await self._session.refresh(debt, attribute_names=["account"])
        return debt

    async def get_by_id(self, debt_id: int) -> Debt | None:
        return await self._session.scalar(
            select(Debt)
            .options(selectinload(Debt.account))
            .where(Debt.id == debt_id)
            .execution_options(populate_existing=True)
        )

    async def get_all(self, *, include_repaid: bool = False) -> list[Debt]:
        stmt = select(Debt).options(selectinload(Debt.account))
        if not include_repaid:
            stmt = stmt.where(Debt.amount > 0)
        return list(
            await self._session.scalars(
                stmt.order_by(
                    Debt.priority.desc(), Debt.amount.desc(), Debt.id
                ).execution_options(populate_existing=True)
            )
        )

    async def delete(self, debt_id: int, expected: DebtUpdates) -> bool:
        stmt = delete(Debt).where(Debt.id == debt_id)
        for field, value in expected.items():
            if field not in DebtUpdates.__annotations__:
                raise ValueError(f"Field cannot be compared: {field}")
            stmt = stmt.where(getattr(Debt, field) == value)
        result = await self._session.execute(stmt.returning(Debt.id))
        return result.scalar_one_or_none() is not None

    async def update(self, debt_id: int, updates: DebtUpdates) -> Debt | None:
        debt = await self.get_by_id(debt_id)
        if debt is None:
            return None
        for field, value in updates.items():
            if field not in DebtUpdates.__annotations__:
                raise ValueError(f"Field cannot be updated: {field}")
            setattr(debt, field, value)
        await self._session.flush()
        await self._session.refresh(debt)
        await self._session.refresh(debt, attribute_names=["account"])
        return debt
