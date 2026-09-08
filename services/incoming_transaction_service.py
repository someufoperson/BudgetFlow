from sqlalchemy.ext.asyncio import AsyncSession

from domain.enums import CategoryType
from domain.transaction_time import occurred_at_to_storage
from schemas.incoming_transaction import (
    CreateIncomingTransactionCommand,
    DeleteIncomingTransactionCommand,
    GetIncomingTransactionCommand,
    IncomingTransactionResult,
    UpdateIncomingTransactionCommand,
)
from schemas.transaction import TransactionSnapshot
from services.account_service import AccountService
from services.category_service import CategoryService
from services.exceptions import (
    CurrencyNotFoundError,
    IncomingTransactionNotFoundError,
    TransactionChangedError,
)
from services.transaction_time import (
    occurred_at_bounds,
    resolve_occurred_at,
    resolve_updated_occurred_at,
)
from settings import settings
from storage.repositories.currency_repository import CurrencyRepository
from storage.repositories.incoming_transaction_repository import (
    IncomingTransactionRepository,
)
from storage.repositories.transaction_repository import TransactionUpdates


class IncomingTransactionService:
    def __init__(
        self,
        session: AsyncSession,
        transaction_repository: IncomingTransactionRepository,
        currency_repository: CurrencyRepository,
        category_service: CategoryService,
        account_service: AccountService,
    ) -> None:
        self._session = session
        self._transactions = transaction_repository
        self._currencies = currency_repository
        self._category_service = category_service
        self._account_service = account_service

    async def create(
        self,
        command: CreateIncomingTransactionCommand,
    ) -> IncomingTransactionResult:
        async with self._session.begin():
            currency = await self._currencies.get_currency_by_code(
                command.currency_code,
            )

            if currency is None:
                raise CurrencyNotFoundError(command.currency_code)

            category = await self._category_service.require_direction(
                command.category_id,
                CategoryType.income,
            )

            account = await self._account_service.require_account(
                command.account_id, command.currency_code
            )
            transaction = await self._transactions.create(
                account_id=account.id,
                name=command.name,
                category_id=category.id,
                amount=command.amount,
                currency=currency,
                occurred_at=resolve_occurred_at(command.occurred_at),
            )

        return IncomingTransactionResult.model_validate(transaction)

    async def get(
        self,
        command: GetIncomingTransactionCommand,
    ) -> list[IncomingTransactionResult]:
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
                account_id=command.account_id,
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
            IncomingTransactionResult.model_validate(transaction)
            for transaction in transactions
        ]

    async def delete(
        self,
        command: DeleteIncomingTransactionCommand,
    ) -> None:
        async with self._session.begin():
            expected: TransactionUpdates | None = None
            if command.expected is not None:
                transaction = await self._transactions.get_by_id(command.id)
                if transaction is None:
                    raise IncomingTransactionNotFoundError(command.id)
                snapshot = command.expected
                expected = {
                    "account_id": snapshot.account_id,
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
                raise IncomingTransactionNotFoundError(command.id)

    async def update(
        self, command: UpdateIncomingTransactionCommand
    ) -> IncomingTransactionResult:
        async with self._session.begin():
            transaction = await self._transactions.get_by_id(command.id)
            if transaction is None:
                raise IncomingTransactionNotFoundError(command.id)
            current = IncomingTransactionResult.model_validate(transaction)
            snapshot = TransactionSnapshot(
                account_id=current.account_id,
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
            if changes.account_id is not None:
                account = await self._account_service.require_account(
                    changes.account_id, changes.currency_code or current.currency.code
                )
                updates["account_id"] = account.id
            if changes.name is not None:
                updates["name"] = changes.name
            if changes.amount is not None:
                updates["amount"] = changes.amount
            if changes.category_id is not None:
                category = await self._category_service.require_direction(
                    changes.category_id, CategoryType.income
                )
                updates["category_id"] = category.id
            if changes.currency_code is not None:
                currency = await self._currencies.get_currency_by_code(
                    changes.currency_code
                )
                if currency is None:
                    raise CurrencyNotFoundError(changes.currency_code)
                if current.account_id is not None and changes.account_id is None:
                    await self._account_service.require_account(
                        current.account_id, currency.code
                    )
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
                "account_id": snapshot.account_id,
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
            return IncomingTransactionResult.model_validate(updated)
