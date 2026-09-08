from datetime import date, datetime, time
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from domain.transaction_time import normalize_occurred_at


class TransactionFilters(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    account_id: int | None = Field(default=None, gt=0)
    category_id: int | None = Field(default=None, gt=0)
    currency_code: str | None = Field(
        default=None, min_length=2, max_length=16, pattern=r"^[A-Za-z0-9]+$"
    )
    date_from: date | None = None
    date_to: date | None = None
    name: str | None = Field(default=None, min_length=1, max_length=128)
    amount: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)
    amount_from: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=2
    )
    amount_to: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=2
    )

    @field_validator("currency_code")
    @classmethod
    def normalize_currency_code(cls, value: str | None) -> str | None:
        return value.upper() if value is not None else None

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
        if self.amount is not None and (
            self.amount_from is not None or self.amount_to is not None
        ):
            raise ValueError("Use either amount or an amount range")
        if (
            self.amount_from is not None
            and self.amount_to is not None
            and self.amount_from > self.amount_to
        ):
            raise ValueError("amount_from cannot exceed amount_to")
        return self


class TransactionChanges(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=128)
    account_id: int | None = Field(default=None, gt=0)
    category_id: int | None = Field(default=None, gt=0)
    amount: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)
    currency_code: str | None = Field(
        default=None, min_length=2, max_length=16, pattern=r"^[A-Za-z0-9]+$"
    )
    occurred_at: datetime | None = None
    occurred_date: date | None = None
    occurred_time: time | None = None

    @field_validator("currency_code")
    @classmethod
    def normalize_currency_code(cls, value: str | None) -> str | None:
        return value.upper() if value is not None else None

    @field_validator("occurred_at")
    @classmethod
    def normalize_transaction_time(cls, value: datetime | None) -> datetime | None:
        return normalize_occurred_at(value) if value is not None else None

    @field_validator("occurred_time")
    @classmethod
    def validate_local_time(cls, value: time | None) -> time | None:
        if value is not None and value.tzinfo is not None:
            raise ValueError("occurred_time must be local time without an offset")
        return value

    @model_validator(mode="after")
    def validate_changes(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one field must be submitted for modification")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Transaction fields cannot be null")
        if self.occurred_at is not None and (
            self.occurred_date is not None or self.occurred_time is not None
        ):
            raise ValueError("Use occurred_at or local date/time fields")
        return self


class TransactionSnapshot(BaseModel):
    account_id: int | None = None
    name: str
    category_id: int
    amount: Decimal
    currency_code: str
    occurred_at: datetime


class UpdateTransactionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(gt=0)
    changes: TransactionChanges
    expected: TransactionSnapshot
