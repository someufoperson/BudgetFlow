from datetime import datetime
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from domain.enums import AccountType
from domain.transaction_time import normalize_occurred_at, occurred_at_from_storage


class AccountDetails(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    currency_code: str
    is_active: bool
    is_default: bool
    account_type: AccountType = AccountType.STANDARD
    credit_limit: Decimal | None = None


class CreateAccountCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=64)
    currency_code: str = Field(min_length=2, max_length=16, pattern=r"^[A-Za-z0-9]+$")
    opening_balance: Decimal = Field(max_digits=18, decimal_places=2)
    opening_balance_at: datetime | None = None
    account_type: AccountType = AccountType.STANDARD
    credit_limit: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=2
    )

    @model_validator(mode="after")
    def validate_credit_limit(self) -> Self:
        if self.account_type is AccountType.CREDIT and self.credit_limit is None:
            raise ValueError("Для кредитного счёта укажите кредитный лимит.")
        if self.account_type is AccountType.STANDARD and self.credit_limit is not None:
            raise ValueError("Кредитный лимит допустим только для кредитного счёта.")
        return self

    @field_validator("currency_code")
    @classmethod
    def normalize_currency_code(cls, value: str) -> str:
        return value.upper()

    @field_validator("opening_balance_at")
    @classmethod
    def normalize_balance_time(cls, value: datetime | None) -> datetime | None:
        return normalize_occurred_at(value) if value is not None else None


class GetAccountByIdCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int = Field(gt=0)


class GetAllAccountsCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    include_inactive: bool = False


class UpdateAccountCommand(GetAccountByIdCommand):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=64)
    opening_balance: Decimal | None = Field(
        default=None, max_digits=18, decimal_places=2
    )
    is_active: bool | None = Field(default=None, strict=True)
    is_default: bool | None = Field(default=None, strict=True)
    account_type: AccountType | None = None
    credit_limit: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=2
    )

    @model_validator(mode="after")
    def validate_changes(self) -> Self:
        fields = self.model_fields_set - {"id"}
        if not fields or any(
            getattr(self, field) is None for field in fields - {"credit_limit"}
        ):
            raise ValueError("Specify non-null account changes")
        if self.is_active is False and self.is_default is True:
            raise ValueError("An inactive account cannot be the default")
        return self


class AssignAccountTransactionsCommand(GetAccountByIdCommand):
    pass


class AccountResult(AccountDetails):
    opening_balance: Decimal
    opening_balance_at: datetime
    balance: Decimal = Decimal("0.00")
    created_at: datetime
    updated_at: datetime

    @field_validator("opening_balance_at", mode="before")
    @classmethod
    def restore_balance_timezone(cls, value: datetime) -> datetime:
        return occurred_at_from_storage(value)
