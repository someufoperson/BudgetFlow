from typing import TypedDict

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.enums import CurrencyType
from storage.models.currency import Currency


class CurrencyUpdates(TypedDict, total=False):
    name: str
    code: str
    currency_type: CurrencyType


class CurrencyRepository:
    _UPDATABLE_FIELDS = frozenset(CurrencyUpdates.__annotations__)

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        name: str,
        code: str,
        currency_type: CurrencyType,
    ) -> Currency:
        currency = Currency(name=name, code=code, currency_type=currency_type)
        self._session.add(currency)
        await self._session.flush()
        return currency

    async def get_currency_by_code(self, code: str) -> Currency | None:
        currency = await self._session.execute(
            select(Currency).where(Currency.code == code)
        )
        return currency.scalar_one_or_none()

    async def delete_by_id(self, currency_id: int) -> bool:
        result = await self._session.execute(
            delete(Currency).where(Currency.id == currency_id).returning(Currency.id),
        )
        return result.scalar_one_or_none() is not None

    async def delete_by_code(self, code: str) -> bool:
        result = await self._session.execute(
            delete(Currency).where(Currency.code == code).returning(Currency.id),
        )
        return result.scalar_one_or_none() is not None

    async def update(self, code: str, updates: CurrencyUpdates) -> Currency | None:
        currency = await self.get_currency_by_code(code)

        if currency is None:
            return None

        if not updates:
            return currency

        invalid_fields = updates.keys() - self._UPDATABLE_FIELDS
        if invalid_fields:
            fields = ", ".join(sorted(invalid_fields))
            raise ValueError(f"Fields cannot be updated: {fields}")

        for field, value in updates.items():
            setattr(currency, field, value)

        await self._session.flush()
        await self._session.refresh(currency)
        return currency
