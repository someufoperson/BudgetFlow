from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from domain.transaction_time import occurred_at_to_storage
from schemas.transfer_transaction import (
    CreateTransferTransactionCommand,
    DeleteTransferTransactionCommand,
    GetTransferTransactionByIdCommand,
    GetTransferTransactionsCommand,
    TransferTransactionResult,
    UpdateTransferTransactionCommand,
)
from services.account_service import AccountService
from services.exceptions import (
    ServiceError,
    TransactionChangedError,
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
                return TransferTransactionResult.model_validate(transfer)
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
                return TransferTransactionResult.model_validate(updated)
        except SQLAlchemyError as error:
            raise ServiceError(
                "Не удалось изменить перевод. Повторите запрос."
            ) from error

    async def delete(self, command: DeleteTransferTransactionCommand) -> None:
        try:
            async with self._session.begin():
                if command.expected.id != command.id:
                    raise TransactionChangedError()
                if not await self._transactions.delete(
                    command.id, self._snapshot(command.expected)
                ):
                    raise TransactionChangedError()
        except SQLAlchemyError as error:
            raise ServiceError(
                "Не удалось удалить перевод. Повторите запрос."
            ) from error
