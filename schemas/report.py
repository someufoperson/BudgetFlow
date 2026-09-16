from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from schemas.account import AccountResult


class GetReportCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days: int | None = Field(default=None, ge=1, le=366, strict=True)
    date_from: date | None = None
    date_to: date | None = None
    format: Literal["text", "image"] = "text"

    @model_validator(mode="after")
    def validate_ranges(self) -> Self:
        if self.date_from is not None or self.date_to is not None:
            if self.days is not None or self.date_from is None or self.date_to is None:
                raise ValueError("Use days or both date_from and date_to")
            if not 0 <= (self.date_to - self.date_from).days < 366:
                raise ValueError("Report period must contain 1 to 366 days")
            if self.date_from == date.min:
                raise ValueError("date_from must be later than 0001-01-01")
        return self


class ReportCategoryResult(BaseModel):
    name: str
    amount: Decimal


class ReportPeriodResult(BaseModel):
    date_from: date
    date_to: date
    amount: Decimal = Decimal("0.00")


class ReportAdjustmentResult(BaseModel):
    id: int
    reversal_of_id: int | None
    reversed_by_id: int | None


class ReportCurrencyResult(BaseModel):
    currency_code: str
    income: Decimal = Decimal("0.00")
    expense: Decimal = Decimal("0.00")
    difference: Decimal = Decimal("0.00")
    balance: Decimal = Decimal("0.00")
    count: int = 0
    unassigned_count: int = 0
    adjustment_count: int = 0
    adjustment_increase: Decimal = Decimal("0.00")
    adjustment_decrease: Decimal = Decimal("0.00")
    adjustment_total: Decimal = Decimal("0.00")
    adjustment_links: list[ReportAdjustmentResult] = Field(default_factory=list)
    categories: list[ReportCategoryResult] = Field(default_factory=list)
    periods: list[ReportPeriodResult] = Field(default_factory=list)
    accounts: list[AccountResult] = Field(default_factory=list)


class ReportResult(BaseModel):
    date_from: date
    date_to: date
    balance_at: datetime
    currencies: list[ReportCurrencyResult]
