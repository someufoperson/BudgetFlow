from datetime import datetime
from decimal import Decimal
from typing import TypedDict

from sqlalchemy import delete, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from storage.models.transfer_transaction import TransferTransaction


class TransferTransactionUpdates(TypedDict):
    source_account_id: int
    destination_account_id: int
    amount: Decimal
    currency_code: str
    occurred_at: datetime


class TransferTransactionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def begin_write(self) -> None:
        await self._session.execute(text("BEGIN IMMEDIATE"))

    async def begin_snapshot(self) -> None:
        await self._session.execute(text("BEGIN"))

    async def create(
        self,
        source_account_id: int,
        destination_account_id: int,
        amount: Decimal,
        currency_code: str,
        occurred_at: datetime,
    ) -> TransferTransaction:
        transfer = TransferTransaction(
            source_account_id=source_account_id,
            destination_account_id=destination_account_id,
            amount=amount,
            currency_code=currency_code,
            occurred_at=occurred_at,
        )
        self._session.add(transfer)
        await self._session.flush()
        await self._session.refresh(
            transfer, attribute_names=["source_account", "destination_account"]
        )
        return transfer

    async def get_by_id(self, transfer_id: int) -> TransferTransaction | None:
        return await self._session.scalar(
            select(TransferTransaction)
            .options(
                selectinload(TransferTransaction.source_account),
                selectinload(TransferTransaction.destination_account),
            )
            .where(TransferTransaction.id == transfer_id)
            .execution_options(populate_existing=True)
        )

    async def get_all(
        self,
        *,
        account_id: int | None,
        occurred_from: datetime | None,
        occurred_to: datetime | None,
        offset: int,
        limit: int,
        source_account_id: int | None = None,
        destination_account_id: int | None = None,
        amount: Decimal | None = None,
    ) -> list[TransferTransaction]:
        stmt = select(TransferTransaction).options(
            selectinload(TransferTransaction.source_account),
            selectinload(TransferTransaction.destination_account),
        )
        if account_id is not None:
            stmt = stmt.where(
                or_(
                    TransferTransaction.source_account_id == account_id,
                    TransferTransaction.destination_account_id == account_id,
                )
            )
        if occurred_from is not None:
            stmt = stmt.where(TransferTransaction.occurred_at >= occurred_from)
        if source_account_id is not None:
            stmt = stmt.where(
                TransferTransaction.source_account_id == source_account_id
            )
        if destination_account_id is not None:
            stmt = stmt.where(
                TransferTransaction.destination_account_id == destination_account_id
            )
        if amount is not None:
            stmt = stmt.where(TransferTransaction.amount == amount)
        if occurred_to is not None:
            stmt = stmt.where(TransferTransaction.occurred_at < occurred_to)
        return list(
            await self._session.scalars(
                stmt.order_by(
                    TransferTransaction.occurred_at.desc(),
                    TransferTransaction.id.desc(),
                )
                .offset(offset)
                .limit(limit)
                .execution_options(populate_existing=True)
            )
        )

    async def update(
        self,
        transfer_id: int,
        updates: TransferTransactionUpdates,
        expected: TransferTransactionUpdates,
    ) -> TransferTransaction | None:
        stmt = update(TransferTransaction).where(TransferTransaction.id == transfer_id)
        for field, value in expected.items():
            stmt = stmt.where(getattr(TransferTransaction, field) == value)
        result = await self._session.execute(
            stmt.values(**updates)
            .returning(TransferTransaction.id)
            .execution_options(synchronize_session=False)
        )
        if result.scalar_one_or_none() is None:
            return None
        return await self.get_by_id(transfer_id)

    async def delete(
        self, transfer_id: int, expected: TransferTransactionUpdates
    ) -> bool:
        stmt = delete(TransferTransaction).where(TransferTransaction.id == transfer_id)
        for field, value in expected.items():
            stmt = stmt.where(getattr(TransferTransaction, field) == value)
        result = await self._session.execute(stmt.returning(TransferTransaction.id))
        return result.scalar_one_or_none() is not None
