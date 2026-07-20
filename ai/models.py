from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from schemas.currency import CreateCurrencyCommand
from schemas.expense_transaction import CreateExpenseTransactionCommand
from schemas.incoming_transaction import CreateIncomingTransactionCommand


class AIResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateCurrencyResponse(AIResponse):
    action: Literal["create_currency"]
    arguments: CreateCurrencyCommand


class CreateExpenseResponse(AIResponse):
    action: Literal["create_expense"]
    arguments: CreateExpenseTransactionCommand


class CreateIncomingResponse(AIResponse):
    action: Literal["create_income"]
    arguments: CreateIncomingTransactionCommand


class ClarifyResponse(AIResponse):
    action: Literal["clarify"]
    message: str = Field(min_length=1)


class TextResponse(AIResponse):
    action: Literal["respond"]
    message: str = Field(min_length=1)


AIResponseType = Annotated[
    CreateCurrencyResponse
    | CreateExpenseResponse
    | CreateIncomingResponse
    | ClarifyResponse
    | TextResponse,
    Field(discriminator="action"),
]

ai_response_adapter: TypeAdapter[AIResponseType] = TypeAdapter(AIResponseType)
