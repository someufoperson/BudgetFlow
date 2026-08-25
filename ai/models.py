from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from schemas.category import CreateCategoryCommand
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
    | CreateTransactionResponse
    | ClarifyResponse
    | TextResponse,
    Field(discriminator="action"),
]

ai_response_adapter: TypeAdapter[AIResponseType] = TypeAdapter(AIResponseType)
