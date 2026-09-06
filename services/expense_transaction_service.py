from sqlalchemy.ext.asyncio import AsyncSession

from domain.enums import CategoryType
from schemas.expense_transaction import (
    CreateExpenseTransactionCommand,
    DeleteExpenseTransactionCommand,
    ExpenseTransactionResult,
    GetExpenseTransactionCommand,
)
from services.category_service import CategoryService
from services.exceptions import (
    CurrencyNotFoundError,
    ExpenseTransactionNotFoundError,
)
from services.transaction_time import occurred_at_bounds, resolve_occurred_at
from settings import settings
from storage.repositories.currency_repository import CurrencyRepository
from storage.repositories.expense_transaction_repository import (
    ExpenseTransactionRepository,
)


class ExpenseTransactionService:
    def __init__(
        self,
        session: AsyncSession,
        transaction_repository: ExpenseTransactionRepository,
        currency_repository: CurrencyRepository,
        category_service: CategoryService,
    ) -> None:
        self._session = session
        self._transactions = transaction_repository
        self._currencies = currency_repository
        self._category_service = category_service

    async def create(
        self,
        command: CreateExpenseTransactionCommand,
    ) -> ExpenseTransactionResult:
        async with self._session.begin():
            currency = await self._currencies.get_currency_by_code(
                command.currency_code,
            )

            if currency is None:
                raise CurrencyNotFoundError(command.currency_code)

            category = await self._category_service.require_direction(
                command.category_id,
                CategoryType.expense,
            )

            transaction = await self._transactions.create(
                name=command.name,
                category_id=category.id,
                amount=command.amount,
                currency=currency,
                occurred_at=resolve_occurred_at(command.occurred_at),
            )

        return ExpenseTransactionResult.model_validate(transaction)

    async def get(
        self,
        command: GetExpenseTransactionCommand,
    ) -> list[ExpenseTransactionResult]:
        async with self._session.begin():
            currency_code: str | None = None

            if command.currency_code is not None:
                currency = await self._currencies.get_currency_by_code(
                    command.currency_code,
                )

                if currency is None:
                    raise CurrencyNotFoundError(command.currency_code)

                currency_code = currency.code

            occurred_from, occurred_to = occurred_at_bounds(
                command.date_from,
                command.date_to,
                settings.timezone_info,
            )
            transactions = await self._transactions.select(
                category_id=command.category_id,
                currency_code=currency_code,
                occurred_from=occurred_from,
                occurred_to=occurred_to,
            )

        return [
            ExpenseTransactionResult.model_validate(transaction)
            for transaction in transactions
        ]

    async def delete(
        self,
        command: DeleteExpenseTransactionCommand,
    ) -> None:
        async with self._session.begin():
            deleted = await self._transactions.delete(command.id)

            if not deleted:
                raise ExpenseTransactionNotFoundError(command.id)
