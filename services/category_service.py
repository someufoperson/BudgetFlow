from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from domain.enums import CategoryType
from schemas.category import (
    CategoryResult,
    CreateCategoryCommand,
    DeleteCategoryByIdCommand,
    GetAllCategoriesCommand,
    GetCategoryByIdCommand,
    UpdateCategoryCommand,
)
from services.exceptions import (
    CategoryAlreadyExistsError,
    CategoryDirectionChangeInUseError,
    CategoryDirectionMismatchError,
    CategoryInUseError,
    CategoryNotFoundError,
)
from storage.repositories.category_repository import (
    CategoryRepository,
    CategoryUpdates,
)


class CategoryService:
    def __init__(
        self,
        session: AsyncSession,
        category_repository: CategoryRepository,
    ) -> None:
        self._session = session
        self._categories = category_repository

    async def require_direction(
        self,
        category_id: int,
        expected_direction: CategoryType,
    ) -> CategoryResult:
        category = await self._categories.get_by_id(category_id)

        if category is None:
            raise CategoryNotFoundError(category_id)

        if category.direction is not expected_direction:
            raise CategoryDirectionMismatchError(
                category_id,
                expected_direction.value,
            )
        return CategoryResult.model_validate(category)

    async def create(self, command: CreateCategoryCommand) -> CategoryResult:
        try:
            async with self._session.begin():
                existing = await self._categories.get_by_name_and_direction(
                    command.name,
                    command.direction,
                )
                if existing is not None:
                    raise CategoryAlreadyExistsError(
                        command.name,
                        command.direction.value,
                    )

                category = await self._categories.create(
                    name=command.name,
                    direction=command.direction,
                    description=command.description,
                )
        except IntegrityError as error:
            raise CategoryAlreadyExistsError(
                command.name,
                command.direction.value,
            ) from error

        return CategoryResult.model_validate(category)

    async def get_by_id(self, command: GetCategoryByIdCommand) -> CategoryResult:
        async with self._session.begin():
            category = await self._categories.get_by_id(command.id)

            if category is None:
                raise CategoryNotFoundError(command.id)

        return CategoryResult.model_validate(category)

    async def get_all(
        self,
        command: GetAllCategoriesCommand,
    ) -> list[CategoryResult]:
        async with self._session.begin():
            categories = await self._categories.get_all(direction=command.direction)

            return [CategoryResult.model_validate(category) for category in categories]

    async def update(self, command: UpdateCategoryCommand) -> CategoryResult:
        try:
            async with self._session.begin():
                category = await self._categories.get_by_id(command.id)
                if category is None:
                    raise CategoryNotFoundError(command.id)

                if (
                    command.direction is not None
                    and command.direction is not category.direction
                    and await self._categories.is_used(command.id)
                ):
                    raise CategoryDirectionChangeInUseError(command.id)

                target_name = (
                    command.name if command.name is not None else category.name
                )
                target_direction = (
                    command.direction
                    if command.direction is not None
                    else category.direction
                )
                duplicate = await self._categories.get_by_name_and_direction(
                    target_name,
                    target_direction,
                )
                if duplicate is not None and duplicate.id != command.id:
                    raise CategoryAlreadyExistsError(
                        target_name,
                        target_direction.value,
                    )

                updates: CategoryUpdates = {}

                if command.name is not None:
                    updates["name"] = command.name

                if command.direction is not None:
                    updates["direction"] = command.direction

                if "description" in command.model_fields_set:
                    updates["description"] = command.description

                updated = await self._categories.update(command.id, updates)
                if updated is None:
                    raise CategoryNotFoundError(command.id)
        except IntegrityError as error:
            raise CategoryAlreadyExistsError(
                target_name,
                target_direction.value,
            ) from error

        return CategoryResult.model_validate(updated)

    async def delete_by_id(self, command: DeleteCategoryByIdCommand) -> None:
        try:
            async with self._session.begin():
                category = await self._categories.get_by_id(command.id)
                if category is None:
                    raise CategoryNotFoundError(command.id)

                if await self._categories.is_used(command.id):
                    raise CategoryInUseError(command.id)

                deleted = await self._categories.delete_by_id(command.id)
                if not deleted:
                    raise CategoryNotFoundError(command.id)
        except IntegrityError as error:
            raise CategoryInUseError(command.id) from error
