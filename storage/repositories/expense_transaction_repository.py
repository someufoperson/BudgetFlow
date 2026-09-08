from datetime import datetime
from decimal import Decimal

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from storage.models.currency import Currency
from storage.models.expense_transaction import ExpenseTransaction
from storage.repositories.transaction_repository import (
    TransactionUpdates,
    matches_transaction_name,
)


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
        account_id: int | None = None,
    ) -> ExpenseTransaction:
        expense_transaction = ExpenseTransaction(
            account_id=account_id,
            name=name,
            category_id=category_id,
            amount=amount,
            currency=currency,
            occurred_at=occurred_at,
        )
        self._session.add(expense_transaction)
        await self._session.flush()
        await self._session.refresh(
            expense_transaction, attribute_names=["category", "account"]
        )
        return expense_transaction

    async def delete(self, id: int, expected: TransactionUpdates | None = None) -> bool:
        stmt = delete(ExpenseTransaction).where(ExpenseTransaction.id == id)
        if expected is not None:
            for field, value in expected.items():
                stmt = stmt.where(getattr(ExpenseTransaction, field) == value)
        result = await self._session.execute(
            stmt.returning(ExpenseTransaction.id),
        )
        return result.scalar_one_or_none() is not None

    async def select(
        self,
        *,
        account_id: int | None = None,
        name: str | None = None,
        amount: Decimal | None = None,
        amount_from: Decimal | None = None,
        amount_to: Decimal | None = None,
        category_id: int | None = None,
        currency_code: str | None = None,
        occurred_from: datetime | None = None,
        occurred_to: datetime | None = None,
    ) -> list[ExpenseTransaction]:
        stmt = select(ExpenseTransaction).options(
            selectinload(ExpenseTransaction.currency),
            selectinload(ExpenseTransaction.category),
            selectinload(ExpenseTransaction.account),
        )

        if account_id is not None:
            stmt = stmt.where(ExpenseTransaction.account_id == account_id)

        if amount is not None:
            stmt = stmt.where(ExpenseTransaction.amount == amount)
        if amount_from is not None:
            stmt = stmt.where(ExpenseTransaction.amount >= amount_from)
        if amount_to is not None:
            stmt = stmt.where(ExpenseTransaction.amount <= amount_to)

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
        return [
            transaction
            for transaction in result.all()
            if matches_transaction_name(transaction.name, name)
        ]

    async def get_by_id(self, id: int) -> ExpenseTransaction | None:
        return await self._session.scalar(
            select(ExpenseTransaction)
            .where(ExpenseTransaction.id == id)
            .options(
                selectinload(ExpenseTransaction.currency),
                selectinload(ExpenseTransaction.category),
                selectinload(ExpenseTransaction.account),
            )
            .execution_options(populate_existing=True)
        )

    async def update(
        self, id: int, updates: TransactionUpdates, expected: TransactionUpdates
    ) -> ExpenseTransaction | None:
        stmt = update(ExpenseTransaction).where(ExpenseTransaction.id == id)
        for field, value in expected.items():
            stmt = stmt.where(getattr(ExpenseTransaction, field) == value)
        result = await self._session.execute(
            stmt.values(**updates)
            .returning(ExpenseTransaction.id)
            .execution_options(synchronize_session=False)
        )
        if result.scalar_one_or_none() is None:
            return None
        return await self.get_by_id(id)
