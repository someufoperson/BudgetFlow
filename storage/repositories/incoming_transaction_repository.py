from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from storage.models.currency import Currency
from storage.models.incoming_transaction import IncomingTransaction


class IncomingTransactionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        name: str,
        category_id: int,
        amount: Decimal,
        currency: Currency,
    ) -> IncomingTransaction:
        incoming_transaction = IncomingTransaction(
            name=name,
            category_id=category_id,
            amount=amount,
            currency=currency,
        )
        self._session.add(incoming_transaction)
        await self._session.flush()
        await self._session.refresh(incoming_transaction, attribute_names=["category"])
        return incoming_transaction

    async def delete(self, id: int) -> bool:
        result = await self._session.execute(
            delete(IncomingTransaction)
            .where(IncomingTransaction.id == id)
            .returning(IncomingTransaction.id),
        )
        return result.scalar_one_or_none() is not None

    async def select(
        self,
        *,
        category_id: int | None = None,
        currency_code: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[IncomingTransaction]:
        if date_from is not None and date_to is not None and date_from > date_to:
            raise ValueError("date_from cannot be later than date_to")

        stmt = select(IncomingTransaction).options(
            selectinload(IncomingTransaction.currency),
            selectinload(IncomingTransaction.category),
        )

        if category_id is not None:
            stmt = stmt.where(IncomingTransaction.category_id == category_id)

        if currency_code is not None:
            stmt = stmt.where(
                IncomingTransaction.currency_code == currency_code,
            )

        if date_from is not None:
            start_datetime = datetime.combine(date_from, time.min)
            stmt = stmt.where(IncomingTransaction.created_at >= start_datetime)

        if date_to is not None:
            end_datetime = datetime.combine(
                date_to + timedelta(days=1),
                time.min,
            )
            stmt = stmt.where(
                IncomingTransaction.created_at < end_datetime,
            )

        stmt = stmt.order_by(IncomingTransaction.created_at.desc())

        result = await self._session.scalars(stmt)
        return list(result.all())
