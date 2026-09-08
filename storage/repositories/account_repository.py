from datetime import datetime
from decimal import Decimal
from typing import TypedDict

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from domain.enums import AccountType
from storage.models.account import Account
from storage.models.expense_transaction import ExpenseTransaction
from storage.models.incoming_transaction import IncomingTransaction


class AccountUpdates(TypedDict, total=False):
    opening_balance: Decimal
    name: str
    is_active: bool
    is_default: bool
    account_type: AccountType
    credit_limit: Decimal | None


class AccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        name: str,
        currency_code: str,
        opening_balance: Decimal,
        opening_balance_at: datetime,
        is_default: bool,
        account_type: AccountType = AccountType.STANDARD,
        credit_limit: Decimal | None = None,
    ) -> Account:
        account = Account(
            name=name,
            currency_code=currency_code,
            opening_balance=opening_balance,
            opening_balance_at=opening_balance_at,
            is_default=is_default,
            account_type=account_type,
            credit_limit=credit_limit,
        )
        self._session.add(account)
        await self._session.flush()
        return account

    async def get_by_id(self, account_id: int) -> Account | None:
        return await self._session.scalar(
            select(Account)
            .where(Account.id == account_id)
            .execution_options(populate_existing=True)
        )

    async def get_all(self, *, include_inactive: bool = False) -> list[Account]:
        stmt = select(Account).order_by(Account.id)
        if not include_inactive:
            stmt = stmt.where(Account.is_active.is_(True))
        return list(
            await self._session.scalars(stmt.execution_options(populate_existing=True))
        )

    async def get_default(self) -> Account | None:
        return await self._session.scalar(
            select(Account)
            .where(Account.is_default.is_(True), Account.is_active.is_(True))
            .execution_options(populate_existing=True)
        )

    async def update(self, account_id: int, updates: AccountUpdates) -> Account | None:
        account = await self.get_by_id(account_id)
        if account is None:
            return None
        if updates.get("is_default"):
            await self._session.execute(
                update(Account)
                .where(Account.is_default.is_(True))
                .values(is_default=False)
            )
        for field, value in updates.items():
            if field not in AccountUpdates.__annotations__:
                raise ValueError(f"Field cannot be updated: {field}")
            setattr(account, field, value)
        await self._session.flush()
        await self._session.refresh(account)
        return account

    async def get_balance(self, account: Account, until: datetime) -> Decimal:
        income = await self._session.scalar(
            select(func.sum(IncomingTransaction.amount)).where(
                IncomingTransaction.account_id == account.id,
                IncomingTransaction.occurred_at > account.opening_balance_at,
                IncomingTransaction.occurred_at <= until,
            )
        )
        expense = await self._session.scalar(
            select(func.sum(ExpenseTransaction.amount)).where(
                ExpenseTransaction.account_id == account.id,
                ExpenseTransaction.occurred_at > account.opening_balance_at,
                ExpenseTransaction.occurred_at <= until,
            )
        )
        return (
            account.opening_balance
            + (income or Decimal("0.00"))
            - (expense or Decimal("0.00"))
        )

    async def assign_transactions(self, account: Account) -> int:
        count = 0
        for model in (ExpenseTransaction, IncomingTransaction):
            result = await self._session.scalars(
                update(model)
                .where(
                    model.account_id.is_(None),
                    model.currency_code == account.currency_code,
                )
                .values(account_id=account.id)
                .returning(model.id)
            )
            count += len(result.all())
        return count
