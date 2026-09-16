from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from domain.enums import SavingsGoalStatus


class CreateSavingsGoalCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=128)
    target_amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency_code: str = Field(min_length=2, max_length=16, pattern=r"^[A-Za-z0-9]+$")
    due_date: date | None = None
    priority: int = Field(default=3, ge=1, le=5, strict=True)

    @field_validator("currency_code")
    @classmethod
    def normalize_currency_code(cls, value: str) -> str:
        return value.upper()

    @field_validator("target_amount", mode="before")
    @classmethod
    def validate_amount_type(cls, value: Decimal | JsonValue) -> Decimal | str | int:
        if isinstance(value, bool) or not isinstance(value, (Decimal, str, int)):
            raise PydanticCustomError(
                "decimal_type", "Передайте сумму точной десятичной строкой."
            )
        return value


class GetSavingsGoalByIdCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(gt=0, strict=True)


class GetAllSavingsGoalsCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UpdateSavingsGoalCommand(GetSavingsGoalByIdCommand):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=128)
    target_amount: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=2
    )
    due_date: date | None = None
    priority: int | None = Field(default=None, ge=1, le=5, strict=True)
    status: Literal[SavingsGoalStatus.ACTIVE, SavingsGoalStatus.PAUSED] | None = None

    @field_validator("target_amount", mode="before")
    @classmethod
    def validate_amount_type(
        cls, value: Decimal | JsonValue
    ) -> Decimal | str | int | None:
        if value is None:
            return None
        return CreateSavingsGoalCommand.validate_amount_type(value)

    @model_validator(mode="after")
    def validate_changes(self) -> Self:
        fields = self.model_fields_set - {"id"}
        if not fields or any(
            getattr(self, field) is None for field in fields - {"due_date"}
        ):
            raise ValueError("Specify non-null savings goal changes")
        return self


class AllocateSavingsGoalCommand(GetSavingsGoalByIdCommand):
    account_id: int = Field(gt=0, strict=True)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency_code: str = Field(min_length=2, max_length=16, pattern=r"^[A-Za-z0-9]+$")

    @field_validator("currency_code")
    @classmethod
    def normalize_currency_code(cls, value: str) -> str:
        return value.upper()

    @field_validator("amount", mode="before")
    @classmethod
    def validate_amount_type(cls, value: Decimal | JsonValue) -> Decimal | str | int:
        return CreateSavingsGoalCommand.validate_amount_type(value)


class ReleaseSavingsGoalCommand(GetSavingsGoalByIdCommand):
    account_id: int | None = Field(default=None, gt=0, strict=True)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency_code: str = Field(min_length=2, max_length=16, pattern=r"^[A-Za-z0-9]+$")

    @field_validator("currency_code")
    @classmethod
    def normalize_currency_code(cls, value: str) -> str:
        return value.upper()

    @field_validator("amount", mode="before")
    @classmethod
    def validate_amount_type(cls, value: Decimal | JsonValue) -> Decimal | str | int:
        return CreateSavingsGoalCommand.validate_amount_type(value)


class SavingsGoalAllocationResult(BaseModel):
    id: int
    account_id: int
    account_name: str
    amount: Decimal
    created_at: datetime


class SavingsGoalAccountResult(BaseModel):
    account_id: int
    account_name: str
    is_active: bool
    allocated_amount: Decimal
    balance: Decimal
    total_allocated_amount: Decimal
    available_amount: Decimal
    shortfall_amount: Decimal


class SavingsGoalResult(BaseModel):
    id: int
    name: str
    target_amount: Decimal
    currency_code: str
    due_date: date | None
    priority: int
    status: SavingsGoalStatus
    allocated_amount: Decimal
    remaining_amount: Decimal
    progress_percent: Decimal
    is_overdue: bool
    accounts: list[SavingsGoalAccountResult]
    history: list[SavingsGoalAllocationResult]
    created_at: datetime
    updated_at: datetime
