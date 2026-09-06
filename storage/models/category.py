from sqlalchemy import Enum, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, validates

from domain.category import normalize_category_name
from domain.enums import CategoryType
from storage.models.abstract import AbstractModel


class Category(AbstractModel):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("name", "direction", name="uq_category_name_direction"),
    )

    name: Mapped[str] = mapped_column(String(length=64), nullable=False)
    direction: Mapped[CategoryType] = mapped_column(
        Enum(
            CategoryType,
            name="category_type",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        String(length=512),
        nullable=True,
    )

    @validates("name")
    def normalize_name(self, _key: str, name: str) -> str:
        return normalize_category_name(name)
