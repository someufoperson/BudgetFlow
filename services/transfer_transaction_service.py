from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from domain.transaction_time import occurred_at_to_storage
from schemas.account import AccountHistoryChange, AccountHistoryWarning
from schemas.transfer_transaction import (
    CreateTransferTransactionCommand,
    DeleteTransferTransactionCommand,
    GetTransferTransactionByIdCommand,
    GetTransferTransactionsCommand,
    TransferTransactionDeletionResult,
    TransferTransactionResult,
    UpdateTransferTransactionCommand,
)
from services.account_service import AccountService
from services.exceptions import (
    ServiceError,
    TransactionChangedError,
    TransferTransactionDeletionChangedError,
    TransferTransactionNotFoundError,
)
from services.transaction_time import occurred_at_bounds, resolve_occurred_at
from settings import settings
from storage.repositories.transfer_transaction_repository import (
    TransferTransactionRepository,
    TransferTransactionUpdates,
)


class TransferTransactionService:
    def __init__(
        self,
        session: AsyncSession,
        transaction_repository: TransferTransactionRepository,
        account_service: AccountService,
    ) -> None:
        self._session = session
        self._transactions = transaction_repository
        self._accounts = account_service

    async def create(
        self, command: CreateTransferTransactionCommand
    ) -> TransferTransactionResult:
        try:
            async with self._session.begin():
                await self._transactions.begin_write()
                await self._accounts.require_account(
                    command.source_account_id, command.currency_code
                )
                await self._accounts.require_account(
                    command.destination_account_id, command.currency_code
                )
                transfer = await self._transactions.create(
                    command.source_account_id,
                    command.destination_account_id,
                    command.amount,
                    command.currency_code,
                    resolve_occurred_at(command.occurred_at),
                )
                result = TransferTransactionResult.model_validate(transfer)
                result.history_warnings = await self._accounts.get_history_warnings(
                    [], self._history(result)
                )
                return result
        except SQLAlchemyError as error:
            raise ServiceError(
                "Не удалось сохранить перевод. Повторите запрос."
            ) from error

    async def get_all(
        self, command: GetTransferTransactionsCommand
    ) -> list[TransferTransactionResult]:
        lower, upper = occurred_at_bounds(
            command.date_from, command.date_to, settings.timezone_info
        )
        async with self._session.begin():
            transfers = await self._transactions.get_all(
                account_id=command.account_id,
                occurred_from=lower,
                occurred_to=upper,
                offset=command.offset,
                limit=command.limit,
                source_account_id=command.source_account_id,
                destination_account_id=command.destination_account_id,
                amount=command.amount,
            )
            return [
                TransferTransactionResult.model_validate(item) for item in transfers
            ]

    async def get_by_id(
        self, command: GetTransferTransactionByIdCommand
    ) -> TransferTransactionResult:
        async with self._session.begin():
            transfer = await self._transactions.get_by_id(command.id)
            if transfer is None:
                raise TransferTransactionNotFoundError(command.id)
            return TransferTransactionResult.model_validate(transfer)

    @staticmethod
    def _history(transfer: TransferTransactionResult) -> list[AccountHistoryChange]:
        return [
            AccountHistoryChange(
                account_id=transfer.source_account_id,
                occurred_at=transfer.occurred_at,
                amount=-transfer.amount,
            ),
            AccountHistoryChange(
                account_id=transfer.destination_account_id,
                occurred_at=transfer.occurred_at,
                amount=transfer.amount,
            ),
        ]

    @staticmethod
    def _snapshot(transfer: TransferTransactionResult) -> TransferTransactionUpdates:
        return {
            "source_account_id": transfer.source_account_id,
            "destination_account_id": transfer.destination_account_id,
            "amount": transfer.amount,
            "currency_code": transfer.currency_code,
            "occurred_at": occurred_at_to_storage(transfer.occurred_at),
        }

    async def update(
        self, command: UpdateTransferTransactionCommand
    ) -> TransferTransactionResult:
        try:
            async with self._session.begin():
                await self._transactions.begin_write()
                transfer = await self._transactions.get_by_id(command.id)
                if transfer is None:
                    raise TransferTransactionNotFoundError(command.id)
                current = TransferTransactionResult.model_validate(transfer)
                if command.expected.id != command.id or self._snapshot(
                    current
                ) != self._snapshot(command.expected):
                    raise TransactionChangedError()
                await self._accounts.require_account(
                    current.source_account_id, current.currency_code
                )
                await self._accounts.require_account(
                    current.destination_account_id, current.currency_code
                )
                changes = command.changes
                source_id = changes.source_account_id or current.source_account_id
                destination_id = (
                    changes.destination_account_id or current.destination_account_id
                )
                if source_id == destination_id:
                    raise ServiceError("Для перевода нужны разные счета.")
                await self._accounts.require_account(source_id, current.currency_code)
                await self._accounts.require_account(
                    destination_id, current.currency_code
                )
                updates: TransferTransactionUpdates = {
                    "source_account_id": source_id,
                    "destination_account_id": destination_id,
                    "amount": changes.amount
                    if changes.amount is not None
                    else current.amount,
                    "currency_code": current.currency_code,
                    "occurred_at": resolve_occurred_at(
                        changes.occurred_at or current.occurred_at
                    ),
                }
                updated = await self._transactions.update(
                    command.id, updates, self._snapshot(command.expected)
                )
                if updated is None:
                    raise TransactionChangedError()
                result = TransferTransactionResult.model_validate(updated)
                result.history_warnings = await self._accounts.get_history_warnings(
                    self._history(current), self._history(result)
                )
                return result
        except SQLAlchemyError as error:
            raise ServiceError(
                "Не удалось изменить перевод. Повторите запрос."
            ) from error

    async def _deletion_result(
        self, transfer_id: int
    ) -> TransferTransactionDeletionResult:
        transfer = await self._transactions.get_by_id(transfer_id)
        if transfer is None:
            raise TransferTransactionNotFoundError(transfer_id)
        result = TransferTransactionResult.model_validate(transfer)
        history = self._history(result)
        changes = [
            await self._accounts.get_balance_change(
                item.model_copy(update={"amount": -item.amount})
            )
            for item in history
        ]
        return TransferTransactionDeletionResult(
            transfer=result,
            balance_changes=changes,
            history_warnings=await self._accounts.get_history_warnings(history, []),
        )

    async def prepare_delete(
        self, command: GetTransferTransactionByIdCommand
    ) -> TransferTransactionDeletionResult:
        async with self._session.begin():
            await self._transactions.begin_snapshot()
            return await self._deletion_result(command.id)

    async def delete(
        self, command: DeleteTransferTransactionCommand
    ) -> list[AccountHistoryWarning]:
        try:
            async with self._session.begin():
                await self._transactions.begin_write()
                if command.expected.transfer.id != command.id:
                    raise TransactionChangedError()
                current = await self._deletion_result(command.id)
                if current != command.expected:
                    raise TransferTransactionDeletionChangedError(current)
                if not await self._transactions.delete(
                    command.id, self._snapshot(command.expected.transfer)
                ):
                    raise TransactionChangedError()
                return current.history_warnings
        except SQLAlchemyError as error:
            raise ServiceError(
                "Не удалось удалить перевод. Повторите запрос."
            ) from error
