from datetime import datetime
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from storage.models.balance_adjustment import BalanceAdjustment


class BalanceAdjustmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def begin_snapshot(self, *, for_update: bool = False) -> None:
        await self._session.execute(text("BEGIN IMMEDIATE" if for_update else "BEGIN"))

    async def create(
        self,
        account_id: int,
        currency_code: str,
        amount: Decimal,
        calculated_balance: Decimal,
        actual_balance: Decimal | None,
        reconciled_at: datetime | None,
        occurred_at: datetime,
        description: str,
        confirmation_id: str,
        reversal_of_id: int | None = None,
    ) -> BalanceAdjustment:
        adjustment = BalanceAdjustment(
            account_id=account_id,
            currency_code=currency_code,
            amount=amount,
            calculated_balance=calculated_balance,
            actual_balance=actual_balance,
            reconciled_at=reconciled_at,
            occurred_at=occurred_at,
            description=description,
            confirmation_id=confirmation_id,
            reversal_of_id=reversal_of_id,
        )
        self._session.add(adjustment)
        await self._session.flush()
        await self._session.refresh(adjustment, attribute_names=["account", "reversal"])
        return adjustment

    async def get_by_confirmation_id(
        self, confirmation_id: str
    ) -> BalanceAdjustment | None:
        return await self._session.scalar(
            select(BalanceAdjustment)
            .options(selectinload(BalanceAdjustment.account))
            .where(BalanceAdjustment.confirmation_id == confirmation_id)
            .options(selectinload(BalanceAdjustment.reversal))
            .execution_options(populate_existing=True)
        )

    async def get_by_id(self, adjustment_id: int) -> BalanceAdjustment | None:
        return await self._session.scalar(
            select(BalanceAdjustment)
            .options(selectinload(BalanceAdjustment.account))
            .where(BalanceAdjustment.id == adjustment_id)
            .options(selectinload(BalanceAdjustment.reversal))
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
    ) -> list[BalanceAdjustment]:
        stmt = select(BalanceAdjustment).options(
            selectinload(BalanceAdjustment.account),
            selectinload(BalanceAdjustment.reversal),
        )
        if account_id is not None:
            stmt = stmt.where(BalanceAdjustment.account_id == account_id)
        if occurred_from is not None:
            stmt = stmt.where(BalanceAdjustment.occurred_at >= occurred_from)
        if occurred_to is not None:
            stmt = stmt.where(BalanceAdjustment.occurred_at < occurred_to)
        return list(
            await self._session.scalars(
                stmt.order_by(
                    BalanceAdjustment.occurred_at.desc(), BalanceAdjustment.id.desc()
                )
                .offset(offset)
                .limit(limit)
                .execution_options(populate_existing=True)
            )
        )
