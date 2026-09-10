from datetime import date, datetime
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from domain.enums import DebtDirection
from schemas.account import AccountDetails


class CreateDebtCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=128)
    direction: DebtDirection
    amount: Decimal = Field(ge=0, max_digits=15, decimal_places=2)
    currency_code: str = Field(min_length=2, max_length=16, pattern=r"^[A-Za-z0-9]+$")
    as_of_date: date | None = None
    priority: int = Field(default=3, ge=1, le=5, strict=True)
    account_id: int | None = Field(default=None, gt=0)
    counterparty: str | None = Field(default=None, min_length=1, max_length=128)
    due_date: date | None = None
    description: str | None = Field(default=None, max_length=512)

    @field_validator("currency_code")
    @classmethod
    def normalize_currency_code(cls, value: str) -> str:
        return value.upper()


class GetDebtByIdCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(gt=0)


class GetAllDebtsCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    include_repaid: bool = False


class UpdateDebtCommand(GetDebtByIdCommand):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=128)
    direction: DebtDirection | None = None
    amount: Decimal | None = Field(default=None, ge=0, max_digits=15, decimal_places=2)
    currency_code: str | None = Field(
        default=None, min_length=2, max_length=16, pattern=r"^[A-Za-z0-9]+$"
    )
    as_of_date: date | None = None
    priority: int | None = Field(default=None, ge=1, le=5, strict=True)
    account_id: int | None = Field(default=None, gt=0)
    counterparty: str | None = Field(default=None, min_length=1, max_length=128)
    due_date: date | None = None
    description: str | None = Field(default=None, max_length=512)

    @field_validator("currency_code")
    @classmethod
    def normalize_currency_code(cls, value: str | None) -> str | None:
        return value.upper() if value is not None else None

    @model_validator(mode="after")
    def validate_changes(self) -> Self:
        fields = self.model_fields_set - {"id"}
        nullable = {"account_id", "counterparty", "due_date", "description"}
        if not fields or any(
            getattr(self, field) is None for field in fields - nullable
        ):
            raise ValueError("Specify non-null debt changes")
        return self


class DebtResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    direction: DebtDirection
    amount: Decimal
    currency_code: str
    as_of_date: date
    priority: int
    account_id: int | None
    account: AccountDetails | None
    counterparty: str | None
    due_date: date | None
    description: str | None
    created_at: datetime
    updated_at: datetime


class DebtSummaryResult(BaseModel):
    payable: dict[str, Decimal] = Field(default_factory=dict)
    receivable: dict[str, Decimal] = Field(default_factory=dict)


class DeleteDebtCommand(GetDebtByIdCommand):
    expected: DebtResult
