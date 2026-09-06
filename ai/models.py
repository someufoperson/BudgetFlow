from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)

from schemas.category import CreateCategoryCommand, UpdateCategoryCommand
from schemas.currency import CreateCurrencyCommand
from schemas.expense_transaction import CreateExpenseTransactionCommand
from schemas.incoming_transaction import CreateIncomingTransactionCommand


class AIResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateCurrencyResponse(AIResponse):
    action: Literal["create_currency"]
    arguments: CreateCurrencyCommand


class CreateCategoryResponse(AIResponse):
    action: Literal["create_category"]
    arguments: CreateCategoryCommand


class UpdateCategoryArguments(AIResponse):
    id: int = Field(gt=0)
    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=512)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return UpdateCategoryCommand.normalize_name(value)

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return UpdateCategoryCommand.normalize_description(value)

    @model_validator(mode="after")
    def validate_update_fields(self) -> Self:
        submitted_fields = self.model_fields_set - {"id"}

        if not submitted_fields or (submitted_fields == {"name"} and self.name is None):
            raise ValueError("At least one field must be submitted for modification")

        return self


class UpdateCategoryResponse(AIResponse):
    action: Literal["update_category"]
    arguments: UpdateCategoryArguments


class ExpenseTransactionItem(AIResponse):
    direction: Literal["expense"]
    arguments: CreateExpenseTransactionCommand


class IncomingTransactionItem(AIResponse):
    direction: Literal["income"]
    arguments: CreateIncomingTransactionCommand


TransactionItem = Annotated[
    ExpenseTransactionItem | IncomingTransactionItem,
    Field(discriminator="direction"),
]


class CreateTransactionResponse(AIResponse):
    action: Literal["create_transactions"]

    transactions: list[TransactionItem] = Field(
        min_length=1,
        max_length=20,
    )


class ClarifyResponse(AIResponse):
    action: Literal["clarify"]
    message: str = Field(min_length=1)


class TextResponse(AIResponse):
    action: Literal["respond"]
    message: str = Field(min_length=1)


AIResponseType = Annotated[
    CreateCurrencyResponse
    | CreateCategoryResponse
    | UpdateCategoryResponse
    | CreateTransactionResponse
    | ClarifyResponse
    | TextResponse,
    Field(discriminator="action"),
]

ai_response_adapter: TypeAdapter[AIResponseType] = TypeAdapter(AIResponseType)
