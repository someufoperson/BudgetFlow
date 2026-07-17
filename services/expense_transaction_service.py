from sqlalchemy.ext.asyncio import AsyncSession

from schemas.expense_transaction import (
    CreateExpenseTransactionCommand,
    DeleteExpenseTransactionCommand,
    ExpenseTransactionResult,
    GetExpenseTransactionCommand,
)
from services.exceptions import (
    CurrencyNotFoundError,
    ExpenseTransactionNotFoundError,
)
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
    ) -> None:
        self._session = session
        self._transactions = transaction_repository
        self._currencies = currency_repository

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

            transaction = await self._transactions.create(
                name=command.name,
                expense_type=command.expense_type,
                amount=command.amount,
                currency_id=currency.id,
            )

        return ExpenseTransactionResult.model_validate(transaction)

    async def get(
        self,
        command: GetExpenseTransactionCommand,
    ) -> list[ExpenseTransactionResult]:
        async with self._session.begin():
            currency_id: int | None = None

            if command.currency_code is not None:
                currency = await self._currencies.get_currency_by_code(
                    command.currency_code,
                )

                if currency is None:
                    raise CurrencyNotFoundError(command.currency_code)

                currency_id = currency.id

            transactions = await self._transactions.select(
                expense_type=command.expense_type,
                currency_id=currency_id,
                date_from=command.date_from,
                date_to=command.date_to,
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
