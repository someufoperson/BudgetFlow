from datetime import datetime
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from storage.models.balance_adjustment import BalanceAdjustment
from storage.models.category import Category
from storage.models.expense_transaction import ExpenseTransaction
from storage.models.incoming_transaction import IncomingTransaction


class ReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_adjustments(
        self, occurred_from: datetime, occurred_to: datetime
    ) -> list[tuple[str, int, Decimal, Decimal]]:
        result = await self._session.execute(
            select(
                BalanceAdjustment.currency_code,
                func.count(BalanceAdjustment.id),
                func.sum(
                    case(
                        (BalanceAdjustment.amount > 0, BalanceAdjustment.amount),
                        else_=0,
                    )
                ),
                func.sum(
                    case(
                        (BalanceAdjustment.amount < 0, -BalanceAdjustment.amount),
                        else_=0,
                    )
                ),
            )
            .where(
                BalanceAdjustment.occurred_at >= occurred_from,
                BalanceAdjustment.occurred_at < occurred_to,
            )
            .group_by(BalanceAdjustment.currency_code)
        )
        return [
            (code, count, increase, decrease)
            for code, count, increase, decrease in result
        ]

    async def get_totals(
        self, occurred_from: datetime, occurred_to: datetime, *, income: bool
    ) -> list[tuple[str, Decimal, int, int]]:
        model = IncomingTransaction if income else ExpenseTransaction
        result = await self._session.execute(
            select(
                model.currency_code,
                func.sum(model.amount),
                func.count(model.id),
                func.sum(case((model.account_id.is_(None), 1), else_=0)),
            )
            .where(model.occurred_at >= occurred_from, model.occurred_at < occurred_to)
            .group_by(model.currency_code)
        )
        return [
            (code, amount, count, unassigned)
            for code, amount, count, unassigned in result
        ]

    async def get_categories(
        self, occurred_from: datetime, occurred_to: datetime
    ) -> list[tuple[str, str, Decimal]]:
        result = await self._session.execute(
            select(
                ExpenseTransaction.currency_code,
                Category.name,
                func.sum(ExpenseTransaction.amount),
            )
            .join(Category, Category.id == ExpenseTransaction.category_id)
            .where(
                ExpenseTransaction.occurred_at >= occurred_from,
                ExpenseTransaction.occurred_at < occurred_to,
            )
            .group_by(ExpenseTransaction.currency_code, Category.id, Category.name)
        )
        return [(code, name, amount) for code, name, amount in result]

    async def get_periods(
        self, bounds: list[tuple[datetime, datetime]]
    ) -> list[tuple[str, int, Decimal]]:
        period = case(
            *[
                (ExpenseTransaction.occurred_at < end, index)
                for index, (_, end) in enumerate(bounds)
            ],
            else_=-1,
        )
        result = await self._session.execute(
            select(
                ExpenseTransaction.currency_code,
                period,
                func.sum(ExpenseTransaction.amount),
            )
            .where(
                ExpenseTransaction.occurred_at >= bounds[0][0],
                ExpenseTransaction.occurred_at < bounds[-1][1],
            )
            .group_by(ExpenseTransaction.currency_code, period)
        )
        return [(code, index, amount) for code, index, amount in result]
