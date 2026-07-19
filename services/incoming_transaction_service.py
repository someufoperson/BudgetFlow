from sqlalchemy.ext.asyncio import AsyncSession

from schemas.incoming_transaction import (
    CreateIncomingTransactionCommand,
    DeleteIncomingTransactionCommand,
    IncomingTransactionResult,
    GetIncomingTransactionCommand,
)
from services.exceptions import (
    CurrencyNotFoundError,
    IncomingTransactionNotFoundError,
)
from storage.repositories.currency_repository import CurrencyRepository
from storage.repositories.incoming_transaction_repository import (
    IncomingTransactionRepository,
)


class IncomingTransactionService:
    def __init__(
        self,
        session: AsyncSession,
        transaction_repository: IncomingTransactionRepository,
        currency_repository: CurrencyRepository,
    ) -> None:
        self._session = session
        self._transactions = transaction_repository
        self._currencies = currency_repository

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

            transaction = await self._transactions.create(
                name=command.name,
                incoming_type=command.incoming_type,
                amount=command.amount,
                currency=currency,
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

            transactions = await self._transactions.select(
                incoming_type=command.incoming_type,
                currency_code=currency_code,
                date_from=command.date_from,
                date_to=command.date_to,
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
            deleted = await self._transactions.delete(command.id)

            if not deleted:
                raise IncomingTransactionNotFoundError(command.id)
