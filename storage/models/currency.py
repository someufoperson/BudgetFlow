from enum import Enum

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from storage.models.abstract import AbstractModel


class CurrencyType(Enum):
    fiat = "FIAT"
    crypto = "CRYPTO"


class Currency(AbstractModel):
    __tablename__ = "currencies"

    name: Mapped[str] = mapped_column(String(length=64), nullable=False)
    code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    currency_type: Mapped[CurrencyType] = mapped_column(nullable=False)
