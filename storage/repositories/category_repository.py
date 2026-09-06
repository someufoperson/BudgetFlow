from typing import TypedDict

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.category import normalize_category_name
from domain.enums import CategoryType
from storage.models.category import Category
from storage.models.expense_transaction import ExpenseTransaction
from storage.models.incoming_transaction import IncomingTransaction


class CategoryUpdates(TypedDict, total=False):
    name: str
    direction: CategoryType
    description: str | None


class CategoryRepository:
    _UPDATABLE_FIELDS = frozenset(CategoryUpdates.__annotations__)

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        name: str,
        direction: CategoryType,
        description: str | None,
    ) -> Category:
        category = Category(
            name=name,
            direction=direction,
            description=description,
        )
        self._session.add(category)
        await self._session.flush()
        return category

    async def get_by_id(self, category_id: int) -> Category | None:
        return await self._session.get(Category, category_id)

    async def get_by_name_and_direction(
        self,
        name: str,
        direction: CategoryType,
    ) -> Category | None:
        result = await self._session.scalars(
            select(Category).where(
                Category.name == normalize_category_name(name),
                Category.direction == direction,
            ),
        )
        return result.one_or_none()

    async def get_all(
        self,
        *,
        direction: CategoryType | None = None,
    ) -> list[Category]:
        stmt = select(Category)

        if direction is not None:
            stmt = stmt.where(Category.direction == direction)

        result = await self._session.scalars(
            stmt.order_by(Category.direction, Category.name),
        )

        return list(result.all())

    async def update(
        self,
        category_id: int,
        updates: CategoryUpdates,
    ) -> Category | None:
        category = await self.get_by_id(category_id)

        if category is None:
            return None

        invalid_fields = updates.keys() - self._UPDATABLE_FIELDS
        if invalid_fields:
            fields = ", ".join(sorted(invalid_fields))
            raise ValueError(f"Fields cannot be updated: {fields}")

        for field, value in updates.items():
            setattr(category, field, value)

        await self._session.flush()
        await self._session.refresh(category)
        return category

    async def delete_by_id(self, category_id: int) -> bool:
        result = await self._session.execute(
            delete(Category).where(Category.id == category_id).returning(Category.id),
        )
        return result.scalar_one_or_none() is not None

    async def is_used(self, category_id: int) -> bool:
        expense_id = await self._session.scalar(
            select(ExpenseTransaction.id)
            .where(ExpenseTransaction.category_id == category_id)
            .limit(1)
        )
        if expense_id is not None:
            return True

        income_id = await self._session.scalar(
            select(IncomingTransaction.id)
            .where(IncomingTransaction.category_id == category_id)
            .limit(1)
        )
        return income_id is not None
