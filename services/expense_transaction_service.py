from sqlalchemy.ext.asyncio import AsyncSession

from domain.enums import CategoryType
from domain.transaction_time import occurred_at_to_storage
from schemas.expense_transaction import (
    CreateExpenseTransactionCommand,
    DeleteExpenseTransactionCommand,
    ExpenseTransactionResult,
    GetExpenseTransactionCommand,
    UpdateExpenseTransactionCommand,
)
from schemas.transaction import TransactionSnapshot
from services.category_service import CategoryService
from services.exceptions import (
    CurrencyNotFoundError,
    ExpenseTransactionNotFoundError,
    TransactionChangedError,
)
from services.transaction_time import (
    occurred_at_bounds,
    resolve_occurred_at,
    resolve_updated_occurred_at,
)
from settings import settings
from storage.repositories.currency_repository import CurrencyRepository
from storage.repositories.expense_transaction_repository import (
    ExpenseTransactionRepository,
)
from storage.repositories.transaction_repository import TransactionUpdates


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
                name=command.name,
                amount=command.amount,
                amount_from=command.amount_from,
                amount_to=command.amount_to,
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
            expected: TransactionUpdates | None = None
            if command.expected is not None:
                transaction = await self._transactions.get_by_id(command.id)
                if transaction is None:
                    raise ExpenseTransactionNotFoundError(command.id)
                snapshot = command.expected
                expected = {
                    "name": snapshot.name,
                    "amount": snapshot.amount,
                    "category_id": snapshot.category_id,
                    "currency_code": snapshot.currency_code,
                    "occurred_at": occurred_at_to_storage(snapshot.occurred_at),
                }
            deleted = await self._transactions.delete(command.id, expected)
            if not deleted:
                if expected is not None:
                    raise TransactionChangedError()
                raise ExpenseTransactionNotFoundError(command.id)

    async def update(
        self, command: UpdateExpenseTransactionCommand
    ) -> ExpenseTransactionResult:
        async with self._session.begin():
            transaction = await self._transactions.get_by_id(command.id)
            if transaction is None:
                raise ExpenseTransactionNotFoundError(command.id)
            current = ExpenseTransactionResult.model_validate(transaction)
            snapshot = TransactionSnapshot(
                name=current.name,
                category_id=current.category.id,
                amount=current.amount,
                currency_code=current.currency.code,
                occurred_at=current.occurred_at,
            )
            if snapshot != command.expected:
                raise TransactionChangedError()
            changes = command.changes
            updates: TransactionUpdates = {}
            if changes.name is not None:
                updates["name"] = changes.name
            if changes.amount is not None:
                updates["amount"] = changes.amount
            if changes.category_id is not None:
                category = await self._category_service.require_direction(
                    changes.category_id, CategoryType.expense
                )
                updates["category_id"] = category.id
            if changes.currency_code is not None:
                currency = await self._currencies.get_currency_by_code(
                    changes.currency_code
                )
                if currency is None:
                    raise CurrencyNotFoundError(changes.currency_code)
                updates["currency_code"] = currency.code
            if (
                changes.occurred_at is not None
                or changes.occurred_date is not None
                or changes.occurred_time is not None
            ):
                updates["occurred_at"] = resolve_updated_occurred_at(
                    current.occurred_at, changes, settings.timezone_info
                )
            expected: TransactionUpdates = {
                "name": snapshot.name,
                "amount": snapshot.amount,
                "category_id": snapshot.category_id,
                "currency_code": snapshot.currency_code,
                "occurred_at": occurred_at_to_storage(snapshot.occurred_at),
            }
            if all(
                value == getattr(transaction, field) for field, value in updates.items()
            ):
                return current
            updated = await self._transactions.update(command.id, updates, expected)
            if updated is None:
                raise TransactionChangedError()
            return ExpenseTransactionResult.model_validate(updated)
