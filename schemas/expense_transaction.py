from datetime import date, datetime
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from schemas.category import CategoryDetails
from schemas.currency import CurrencyDetails


class CreateExpenseTransactionCommand(BaseModel):
    """arguments for create expense transaction"""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    name: str = Field(min_length=1, max_length=128)
    category_id: int = Field(gt=0)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency_code: str = Field(
        min_length=2,
        max_length=16,
        pattern=r"^[A-Za-z0-9]+$",
    )

    @field_validator("currency_code")
    @classmethod
    def normalize_currency_code(cls, value: str) -> str:
        return value.upper()


class DeleteExpenseTransactionCommand(BaseModel):
    """arguments for delete transaction"""

    model_config = ConfigDict(extra="forbid")

    id: int = Field(gt=0)


class GetExpenseTransactionCommand(BaseModel):
    """arguments for filtering expense transaction"""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    category_id: int | None = Field(default=None, gt=0)
    currency_code: str | None = Field(
        default=None,
        min_length=2,
        max_length=16,
        pattern=r"^[A-Za-z0-9]+$",
    )
    date_from: date | None = None
    date_to: date | None = None

    @field_validator("currency_code")
    @classmethod
    def normalize_currency_code(cls, value: str | None) -> str | None:
        return value.upper() if value is not None else None

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        if (
            self.date_from is not None
            and self.date_to is not None
            and self.date_from > self.date_to
        ):
            raise ValueError("date_from cannot be later than date_to")

        return self


class ExpenseTransactionResult(BaseModel):
    """for return from service"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: CategoryDetails
    amount: Decimal
    currency: CurrencyDetails
    created_at: datetime
    updated_at: datetime
