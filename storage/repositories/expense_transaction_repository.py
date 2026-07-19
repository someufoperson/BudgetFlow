from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from domain.enums import ExpenseType
from storage.models.expense_transaction import ExpenseTransaction
from storage.models.currency import Currency


class ExpenseTransactionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        name: str,
        expense_type: ExpenseType,
        amount: Decimal,
        currency: Currency,
    ) -> ExpenseTransaction:
        expense_transaction = ExpenseTransaction(
            name=name,
            expense_type=expense_type,
            amount=amount,
            currency=currency,
        )
        self._session.add(expense_transaction)
        await self._session.flush()
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
        expense_type: ExpenseType | None = None,
        currency_code: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[ExpenseTransaction]:
        if date_from is not None and date_to is not None:
            if date_from > date_to:
                raise ValueError("date_from cannot be later than date_to")

        stmt = select(ExpenseTransaction).options(
            selectinload(ExpenseTransaction.currency)
        )

        if expense_type is not None:
            stmt = stmt.where(
                ExpenseTransaction.expense_type == expense_type,
            )

        if currency_code is not None:
            stmt = stmt.where(
                ExpenseTransaction.currency_code == currency_code,
            )

        if date_from is not None:
            start_datetime = datetime.combine(date_from, time.min)
            stmt = stmt.where(ExpenseTransaction.created_at >= start_datetime)

        if date_to is not None:
            end_datetime = datetime.combine(
                date_to + timedelta(days=1),
                time.min,
            )
            stmt = stmt.where(
                ExpenseTransaction.created_at < end_datetime,
            )

        stmt = stmt.order_by(ExpenseTransaction.created_at.desc())

        result = await self._session.scalars(stmt)
        return list(result.all())
