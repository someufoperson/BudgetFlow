from datetime import datetime
from decimal import Decimal

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from storage.models.currency import Currency
from storage.models.incoming_transaction import IncomingTransaction
from storage.repositories.transaction_repository import (
    TransactionUpdates,
    matches_transaction_name,
)


class IncomingTransactionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        name: str,
        category_id: int,
        amount: Decimal,
        currency: Currency,
        occurred_at: datetime,
    ) -> IncomingTransaction:
        incoming_transaction = IncomingTransaction(
            name=name,
            category_id=category_id,
            amount=amount,
            currency=currency,
            occurred_at=occurred_at,
        )
        self._session.add(incoming_transaction)
        await self._session.flush()
        await self._session.refresh(incoming_transaction, attribute_names=["category"])
        return incoming_transaction

    async def delete(self, id: int, expected: TransactionUpdates | None = None) -> bool:
        stmt = delete(IncomingTransaction).where(IncomingTransaction.id == id)
        if expected is not None:
            for field, value in expected.items():
                stmt = stmt.where(getattr(IncomingTransaction, field) == value)
        result = await self._session.execute(
            stmt.returning(IncomingTransaction.id),
        )
        return result.scalar_one_or_none() is not None

    async def select(
        self,
        *,
        name: str | None = None,
        amount: Decimal | None = None,
        amount_from: Decimal | None = None,
        amount_to: Decimal | None = None,
        category_id: int | None = None,
        currency_code: str | None = None,
        occurred_from: datetime | None = None,
        occurred_to: datetime | None = None,
    ) -> list[IncomingTransaction]:
        stmt = select(IncomingTransaction).options(
            selectinload(IncomingTransaction.currency),
            selectinload(IncomingTransaction.category),
        )

        if amount is not None:
            stmt = stmt.where(IncomingTransaction.amount == amount)
        if amount_from is not None:
            stmt = stmt.where(IncomingTransaction.amount >= amount_from)
        if amount_to is not None:
            stmt = stmt.where(IncomingTransaction.amount <= amount_to)

        if category_id is not None:
            stmt = stmt.where(IncomingTransaction.category_id == category_id)

        if currency_code is not None:
            stmt = stmt.where(
                IncomingTransaction.currency_code == currency_code,
            )

        if occurred_from is not None:
            stmt = stmt.where(IncomingTransaction.occurred_at >= occurred_from)

        if occurred_to is not None:
            stmt = stmt.where(IncomingTransaction.occurred_at < occurred_to)

        stmt = stmt.order_by(
            IncomingTransaction.occurred_at.desc(),
            IncomingTransaction.id.desc(),
        )

        result = await self._session.scalars(stmt)
        return [
            transaction
            for transaction in result.all()
            if matches_transaction_name(transaction.name, name)
        ]

    async def get_by_id(self, id: int) -> IncomingTransaction | None:
        return await self._session.scalar(
            select(IncomingTransaction)
            .where(IncomingTransaction.id == id)
            .options(
                selectinload(IncomingTransaction.currency),
                selectinload(IncomingTransaction.category),
            )
            .execution_options(populate_existing=True)
        )

    async def update(
        self, id: int, updates: TransactionUpdates, expected: TransactionUpdates
    ) -> IncomingTransaction | None:
        stmt = update(IncomingTransaction).where(IncomingTransaction.id == id)
        for field, value in expected.items():
            stmt = stmt.where(getattr(IncomingTransaction, field) == value)
        result = await self._session.execute(
            stmt.values(**updates)
            .returning(IncomingTransaction.id)
            .execution_options(synchronize_session=False)
        )
        if result.scalar_one_or_none() is None:
            return None
        return await self.get_by_id(id)
