from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from storage.models.currency import Currency, CurrencyType


class CurrencyRepository:
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

    async def delete_by_id(self, currency_id: int) -> bool:
        result = await self._session.execute(
            delete(Currency).where(Currency.id == currency_id),
        )
        return result.rowcount > 0
