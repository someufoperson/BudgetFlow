from datetime import date, datetime
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from domain.transaction_time import normalize_occurred_at, occurred_at_from_storage
from schemas.account import (
    AccountBalanceChangeResult,
    AccountDetails,
    AccountHistoryWarning,
)


class CreateTransferTransactionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_account_id: int = Field(gt=0)
    destination_account_id: int = Field(gt=0)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency_code: str = Field(min_length=2, max_length=16, pattern=r"^[A-Za-z0-9]+$")
    occurred_at: datetime | None = None

    @field_validator("currency_code")
    @classmethod
    def normalize_currency_code(cls, value: str) -> str:
        return value.upper()

    @field_validator("occurred_at")
    @classmethod
    def normalize_transaction_time(cls, value: datetime | None) -> datetime | None:
        return normalize_occurred_at(value) if value is not None else None

    @model_validator(mode="after")
    def validate_accounts(self) -> Self:
        if self.source_account_id == self.destination_account_id:
            raise ValueError("Для перевода нужны разные счета.")
        return self


class GetTransferTransactionByIdCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(gt=0)


class GetTransferTransactionsCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: int | None = Field(default=None, gt=0)
    source_account_id: int | None = Field(default=None, gt=0)
    destination_account_id: int | None = Field(default=None, gt=0)
    amount: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)
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


class TransferTransactionChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_account_id: int | None = Field(default=None, gt=0)
    destination_account_id: int | None = Field(default=None, gt=0)
    amount: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)
    occurred_at: datetime | None = None

    @field_validator("occurred_at")
    @classmethod
    def normalize_transaction_time(cls, value: datetime | None) -> datetime | None:
        return normalize_occurred_at(value) if value is not None else None

    @model_validator(mode="after")
    def validate_changes(self) -> Self:
        if not self.model_fields_set or any(
            getattr(self, field) is None for field in self.model_fields_set
        ):
            raise ValueError("Specify non-null transfer changes")
        return self


class TransferTransactionResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_account_id: int
    destination_account_id: int
    source_account: AccountDetails
    destination_account: AccountDetails
    amount: Decimal
    currency_code: str
    occurred_at: datetime
    created_at: datetime
    updated_at: datetime
    history_warnings: list[AccountHistoryWarning] = Field(default_factory=list)

    @field_validator("occurred_at", mode="before")
    @classmethod
    def restore_transaction_timezone(cls, value: datetime) -> datetime:
        return occurred_at_from_storage(value)


class UpdateTransferTransactionCommand(GetTransferTransactionByIdCommand):
    changes: TransferTransactionChanges
    expected: TransferTransactionResult


class TransferTransactionDeletionResult(BaseModel):
    transfer: TransferTransactionResult
    balance_changes: list[AccountBalanceChangeResult]
    history_warnings: list[AccountHistoryWarning]


class DeleteTransferTransactionCommand(GetTransferTransactionByIdCommand):
    expected: TransferTransactionDeletionResult
