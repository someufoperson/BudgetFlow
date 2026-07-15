from enum import StrEnum

from sqlalchemy import String, Enum
from sqlalchemy.orm import Mapped, mapped_column

from domain.enums import CurrencyType
from storage.models.abstract import AbstractModel


class Currency(AbstractModel):
    __tablename__ = "currencies"

    name: Mapped[str] = mapped_column(String(length=64), nullable=False)
    code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    currency_type: Mapped[CurrencyType] = mapped_column(
        Enum(
            CurrencyType,
            name="currency_type",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
