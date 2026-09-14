from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from domain.transaction_time import normalize_occurred_at


@dataclass(frozen=True, slots=True)
class DocumentInput:
    name: str
    data: bytes


@dataclass(frozen=True, slots=True)
class DocumentPage:
    name: str
    text: str = ""
    image_url: str | None = None


class ScreenshotTransactionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    direction: Literal["expense", "income", "transfer"] | None = None
    status: Literal["completed", "pending", "failed", "unknown"] = "unknown"
    name: str | None = Field(default=None, min_length=1, max_length=128)
    amount: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)
    currency_code: str | None = Field(
        default=None, min_length=2, max_length=16, pattern=r"^[A-Za-z0-9]+$"
    )
    occurred_at: datetime | None = None
    account_id: int | None = Field(default=None, gt=0)
    category_id: int | None = Field(default=None, gt=0)

    @field_validator("currency_code")
    @classmethod
    def normalize_currency_code(cls, value: str | None) -> str | None:
        return value.upper() if value is not None else None

    @field_validator("occurred_at")
    @classmethod
    def normalize_time(cls, value: datetime | None) -> datetime | None:
        return normalize_occurred_at(value) if value is not None else None


class ScreenshotResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["transactions", "unknown"]
    transactions: list[ScreenshotTransactionDraft] = Field(
        default_factory=list, max_length=20
    )
    warnings: list[str] = Field(default_factory=list, max_length=30)
