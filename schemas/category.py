from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from domain.enums import CategoryType


class CategoryDetails(BaseModel):
    """model for relationship"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    direction: CategoryType
    description: str | None


class CategoryNameCommand(BaseModel):
    """the general model that accepts the category name"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=64)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.split())

        if not normalized:
            raise ValueError("Category name cannot be empty")

        return normalized


class CategoryIdCommand(BaseModel):
    """the general model that accepts the category id"""

    model_config = ConfigDict(extra="forbid")

    id: int = Field(gt=0)


class CreateCategoryCommand(CategoryNameCommand):
    """arguments for create category"""

    direction: CategoryType
    description: str | None = Field(default=None, max_length=512)

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = " ".join(value.split())

        return normalized or None


class GetCategoryByIdCommand(CategoryIdCommand):
    """arguments for get category"""


class GetAllCategoriesCommand(BaseModel):
    """arguments for get all categories"""

    model_config = ConfigDict(extra="forbid")

    direction: CategoryType | None = None


class UpdateCategoryCommand(CategoryIdCommand):
    """arguments for update category"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=64)
    direction: CategoryType | None = None
    description: str | None = Field(default=None, max_length=512)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = " ".join(value.split())

        if not normalized:
            raise ValueError("Category name cannot be empty")

        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = " ".join(value.split())

        return normalized or None

    @model_validator(mode="after")
    def validate_update_fields(self) -> Self:
        submitted_fields = self.model_fields_set - {"id"}

        if not submitted_fields:
            raise ValueError("At least one field must be submitted for modification")

        return self


class DeleteCategoryByIdCommand(CategoryIdCommand):
    """arguments for delete category"""


class CategoryResult(CategoryDetails):
    """for return from service"""

    created_at: datetime
    updated_at: datetime
