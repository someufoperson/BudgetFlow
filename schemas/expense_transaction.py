from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from domain.transaction_time import normalize_occurred_at, occurred_at_from_storage
from schemas.account import AccountDetails
from schemas.category import CategoryDetails
from schemas.currency import CurrencyDetails
from schemas.transaction import (
    TransactionFilters,
    TransactionSnapshot,
    UpdateTransactionCommand,
)


class CreateExpenseTransactionCommand(BaseModel):
    """arguments for create expense transaction"""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    account_id: int | None = Field(default=None, gt=0)
    name: str = Field(min_length=1, max_length=128)
    category_id: int = Field(gt=0)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    occurred_at: datetime | None = None
    currency_code: str = Field(
        min_length=2,
        max_length=16,
        pattern=r"^[A-Za-z0-9]+$",
    )

    @field_validator("currency_code")
    @classmethod
    def normalize_currency_code(cls, value: str) -> str:
        return value.upper()

    @field_validator("occurred_at")
    @classmethod
    def normalize_transaction_time(cls, value: datetime | None) -> datetime | None:
        return normalize_occurred_at(value) if value is not None else None


class DeleteExpenseTransactionCommand(BaseModel):
    """arguments for delete transaction"""

    model_config = ConfigDict(extra="forbid")

    id: int = Field(gt=0)
    expected: TransactionSnapshot | None = None


class GetExpenseTransactionCommand(TransactionFilters):
    pass


class UpdateExpenseTransactionCommand(UpdateTransactionCommand):
    pass


class ExpenseTransactionResult(BaseModel):
    """for return from service"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int | None = None
    account: AccountDetails | None = None
    name: str
    category: CategoryDetails
    amount: Decimal
    currency: CurrencyDetails
    occurred_at: datetime
    created_at: datetime
    updated_at: datetime

    @field_validator("occurred_at", mode="before")
    @classmethod
    def restore_transaction_timezone(cls, value: datetime) -> datetime:
        return occurred_at_from_storage(value)
