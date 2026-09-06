from datetime import datetime
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from storage.models.currency import Currency
from storage.models.expense_transaction import ExpenseTransaction


class ExpenseTransactionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        name: str,
        category_id: int,
        amount: Decimal,
        currency: Currency,
        occurred_at: datetime,
    ) -> ExpenseTransaction:
        expense_transaction = ExpenseTransaction(
            name=name,
            category_id=category_id,
            amount=amount,
            currency=currency,
            occurred_at=occurred_at,
        )
        self._session.add(expense_transaction)
        await self._session.flush()
        await self._session.refresh(expense_transaction, attribute_names=["category"])
        return expense_transaction

    async def delete(self, id: int) -> bool:
        result = await self._session.execute(
            delete(ExpenseTransaction)
            .where(ExpenseTransaction.id == id)
            .returning(ExpenseTransaction.id),
        )
        return result.scalar_one_or_none() is not None

    async def select(
        self,
        *,
        category_id: int | None = None,
        currency_code: str | None = None,
        occurred_from: datetime | None = None,
        occurred_to: datetime | None = None,
    ) -> list[ExpenseTransaction]:
        stmt = select(ExpenseTransaction).options(
            selectinload(ExpenseTransaction.currency),
            selectinload(ExpenseTransaction.category),
        )

        if category_id is not None:
            stmt = stmt.where(ExpenseTransaction.category_id == category_id)

        if currency_code is not None:
            stmt = stmt.where(
                ExpenseTransaction.currency_code == currency_code,
            )

        if occurred_from is not None:
            stmt = stmt.where(ExpenseTransaction.occurred_at >= occurred_from)

        if occurred_to is not None:
            stmt = stmt.where(ExpenseTransaction.occurred_at < occurred_to)

        stmt = stmt.order_by(
            ExpenseTransaction.occurred_at.desc(),
            ExpenseTransaction.id.desc(),
        )

        result = await self._session.scalars(stmt)
        return list(result.all())
