from datetime import date, datetime
from decimal import Decimal
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from domain.transaction_time import normalize_occurred_at, occurred_at_from_storage
from schemas.account import AccountBalanceChangeResult, AccountDetails


class ReconcileAccountCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    account_id: int = Field(gt=0)
    actual_balance: Decimal = Field(max_digits=18, decimal_places=2)
    currency_code: str = Field(min_length=2, max_length=16, pattern=r"^[A-Za-z0-9]+$")

    @field_validator("currency_code")
    @classmethod
    def normalize_currency_code(cls, value: str) -> str:
        return value.upper()


class AccountReconciliationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account: AccountDetails
    calculated_balance: Decimal = Field(max_digits=18, decimal_places=2)
    actual_balance: Decimal = Field(max_digits=18, decimal_places=2)
    amount: Decimal = Field(max_digits=18, decimal_places=2)
    reconciled_at: datetime
    opening_balance: Decimal = Field(max_digits=18, decimal_places=2)
    opening_balance_at: datetime
    confirmation_id: UUID

    @field_validator("reconciled_at", "opening_balance_at")
    @classmethod
    def normalize_reconciliation_time(cls, value: datetime) -> datetime:
        return normalize_occurred_at(value)

    @model_validator(mode="after")
    def validate_amount(self) -> Self:
        if self.amount != self.actual_balance - self.calculated_balance:
            raise ValueError("Корректировка должна равняться разнице остатков.")
        return self


class CreateBalanceAdjustmentCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expected: AccountReconciliationResult
    description: str = Field(min_length=1, max_length=512)


class GetBalanceAdjustmentByIdCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(gt=0)


class GetBalanceAdjustmentsCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: int | None = Field(default=None, gt=0)
    date_from: date | None = None
    date_to: date | None = None
    offset: int = Field(default=0, ge=0, strict=True)
    limit: int = Field(default=10, ge=1, le=10, strict=True)

    @model_validator(mode="after")
    def validate_ranges(self) -> Self:
        if self.date_to == date.max:
            raise ValueError("date_to must be earlier than 9999-12-31")
        if (
            self.date_from is not None
            and self.date_to is not None
            and self.date_from > self.date_to
        ):
            raise ValueError("date_from cannot be later than date_to")
        return self


class BalanceAdjustmentResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    account: AccountDetails
    currency_code: str
    amount: Decimal
    calculated_balance: Decimal
    actual_balance: Decimal | None
    reconciled_at: datetime | None
    reversal_of_id: int | None = None
    reversed_by_id: int | None = None
    occurred_at: datetime
    description: str
    confirmation_id: UUID
    created_at: datetime
    updated_at: datetime

    @field_validator("occurred_at", mode="before")
    @classmethod
    def restore_adjustment_timezone(cls, value: datetime) -> datetime:
        return occurred_at_from_storage(value)

    @field_validator("reconciled_at", mode="before")
    @classmethod
    def restore_reconciliation_timezone(cls, value: datetime | None) -> datetime | None:
        return occurred_at_from_storage(value) if value is not None else None


class PrepareBalanceAdjustmentReversalCommand(GetBalanceAdjustmentByIdCommand):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    description: str = Field(
        default="Отмена ошибочной корректировки по запросу пользователя.",
        min_length=1,
        max_length=512,
    )


class BalanceAdjustmentReversalResult(BaseModel):
    original: BalanceAdjustmentResult
    balance_change: AccountBalanceChangeResult
    description: str
    confirmation_id: UUID


class ReverseBalanceAdjustmentCommand(GetBalanceAdjustmentByIdCommand):
    expected: BalanceAdjustmentReversalResult
