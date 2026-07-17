from sqlalchemy.ext.asyncio import AsyncSession

from schemas.currency import (
    CreateCurrencyCommand,
    CurrencyResult,
    DeleteCurrencyByCodeCommand,
    GetAllCurrenciesCommand,
    GetCurrencyByCodeCommand,
    UpdateCurrencyCommand,
)
from services.exceptions import CurrencyAlreadyExistsError, CurrencyNotFoundError
from storage.repositories.currency_repository import CurrencyRepository, CurrencyUpdates


class CurrencyService:
    def __init__(
        self,
        session: AsyncSession,
        currency_repository: CurrencyRepository,
    ) -> None:
        self._session = session
        self._currencies = currency_repository

    async def create(
        self,
        command: CreateCurrencyCommand,
    ) -> CurrencyResult:
        async with self._session.begin():
            existing_currency = await self._currencies.get_currency_by_code(
                code=command.code,
            )

            if existing_currency is not None:
                raise CurrencyAlreadyExistsError(command.code)

            currency = await self._currencies.create(
                name=command.name,
                code=command.code,
                currency_type=command.currency_type,
            )

        return CurrencyResult.model_validate(currency)

    async def get_by_code(
        self,
        command: GetCurrencyByCodeCommand,
    ) -> CurrencyResult:
        async with self._session.begin():
            currency = await self._currencies.get_currency_by_code(
                command.code,
            )

            if currency is None:
                raise CurrencyNotFoundError(command.code)

        return CurrencyResult.model_validate(currency)

    async def get_all(
        self,
        command: GetAllCurrenciesCommand,
    ) -> list[CurrencyResult]:
        async with self._session.begin():
            currencies = await self._currencies.get_all(
                currency_type=command.currency_type,
            )

            return [CurrencyResult.model_validate(currency) for currency in currencies]

    async def update(
        self,
        command: UpdateCurrencyCommand,
    ) -> CurrencyResult:
        async with self._session.begin():
            if command.new_code is not None and command.new_code != command.code:
                existing_currency = await self._currencies.get_currency_by_code(
                    command.new_code,
                )

                if existing_currency is not None:
                    raise CurrencyAlreadyExistsError(command.new_code)

            updates: CurrencyUpdates = {}

            if command.name is not None:
                updates["name"] = command.name

            if command.new_code is not None:
                updates["code"] = command.new_code

            if command.currency_type is not None:
                updates["currency_type"] = command.currency_type

            currency = await self._currencies.update(
                code=command.code,
                updates=updates,
            )

            if currency is None:
                raise CurrencyNotFoundError(command.code)

        return CurrencyResult.model_validate(currency)

    async def delete_by_code(
        self,
        command: DeleteCurrencyByCodeCommand,
    ) -> None:
        async with self._session.begin():
            deleted = await self._currencies.delete_by_code(
                command.code,
            )

            if not deleted:
                raise CurrencyNotFoundError(command.code)
