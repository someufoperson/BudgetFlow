from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from domain.enums import CurrencyType


class CurrencyDetails(BaseModel):
    """model for relationship"""

    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    currency_type: CurrencyType


class CurrencyCodeCommand(BaseModel):
    """the general model that accepts the currency code"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: str = Field(min_length=2, max_length=16, pattern=r"^[A-Za-z0-9]+$")

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.upper()


class CreateCurrencyCommand(CurrencyCodeCommand):
    """arguments for create currency"""

    name: str = Field(min_length=1, max_length=64)
    currency_type: CurrencyType


class GetCurrencyByCodeCommand(CurrencyCodeCommand):
    """arguments for get currency"""

    pass


class GetAllCurrenciesCommand(BaseModel):
    """arguments for get all currency"""

    model_config = ConfigDict(extra="forbid")

    currency_type: CurrencyType | None = None


class UpdateCurrencyCommand(CurrencyCodeCommand):
    """
    code - code currency for update
    new_code - new currency code
    """

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
    )
    new_code: str | None = Field(
        default=None, min_length=2, max_length=16, pattern=r"^[A-Za-z0-9]+$"
    )
    currency_type: CurrencyType | None = None

    @field_validator("new_code")
    @classmethod
    def normalize_new_code(cls, value: str | None) -> str | None:
        if value is None:
            return None

        return value.upper()

    @model_validator(mode="after")
    def validate_update_fields(self) -> Self:
        if self.name is None and self.new_code is None and self.currency_type is None:
            raise ValueError("At least one field must be submitted for modification")

        return self


class DeleteCurrencyByCodeCommand(CurrencyCodeCommand):
    """arguments for delete currency"""

    pass


class CurrencyResult(BaseModel):
    """for return from service"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
    currency_type: CurrencyType
    created_at: datetime
    updated_at: datetime
