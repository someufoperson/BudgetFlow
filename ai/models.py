from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    TypeAdapter,
    field_validator,
    model_validator,
)

from schemas.account import (
    AssignAccountTransactionsCommand,
    CreateAccountCommand,
    GetAccountByIdCommand,
    GetAllAccountsCommand,
    UpdateAccountCommand,
)
from schemas.category import CreateCategoryCommand, UpdateCategoryCommand
from schemas.currency import CreateCurrencyCommand
from schemas.debt import (
    CreateDebtCommand,
    GetAllDebtsCommand,
    GetDebtByIdCommand,
    UpdateDebtCommand,
)
from schemas.expense_transaction import CreateExpenseTransactionCommand
from schemas.incoming_transaction import CreateIncomingTransactionCommand
from schemas.transaction import TransactionChanges, TransactionFilters


class AIResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateCurrencyResponse(AIResponse):
    action: Literal["create_currency"]
    arguments: CreateCurrencyCommand


class CreateAccountResponse(AIResponse):
    action: Literal["create_account"]
    arguments: CreateAccountCommand


class CreateDebtResponse(AIResponse):
    action: Literal["create_debt"]
    arguments: CreateDebtCommand


class UpdateDebtResponse(AIResponse):
    action: Literal["update_debt"]
    arguments: UpdateDebtCommand


class GetDebtsResponse(AIResponse):
    action: Literal["get_debts"]
    arguments: GetAllDebtsCommand


class GetDebtResponse(AIResponse):
    action: Literal["get_debt"]
    arguments: GetDebtByIdCommand


class DeleteDebtResponse(AIResponse):
    action: Literal["delete_debt"]
    arguments: GetDebtByIdCommand


class ConfirmDeleteDebtResponse(AIResponse):
    action: Literal["confirm_delete_debt"]
    confirmed: bool = Field(strict=True)


class UpdateAccountResponse(AIResponse):
    action: Literal["update_account"]
    arguments: UpdateAccountCommand


class GetAccountsResponse(AIResponse):
    action: Literal["get_accounts"]
    arguments: GetAllAccountsCommand


class GetAccountResponse(AIResponse):
    action: Literal["get_account"]
    arguments: GetAccountByIdCommand


class AssignAccountTransactionsResponse(AIResponse):
    action: Literal["assign_account_transactions"]
    arguments: AssignAccountTransactionsCommand


class ConfirmAssignAccountTransactionsResponse(AIResponse):
    action: Literal["confirm_assign_account_transactions"]
    confirmed: bool = Field(strict=True)


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


class SearchTransactionArguments(TransactionFilters):
    direction: Literal["expense", "income"] | None = None


class SearchTransactionsResponse(AIResponse):
    action: Literal["search_transactions"]
    filters: SearchTransactionArguments
    limit: int = Field(default=10, ge=1, le=10, strict=True)

    @field_validator("limit", mode="before")
    @classmethod
    def normalize_limit(cls, value: JsonValue) -> JsonValue:
        return 10 if value is None else value


class MoreTransactionsResponse(AIResponse):
    action: Literal["more_transactions"]
    limit: int | None = Field(default=None, ge=1, le=10, strict=True)


class SelectTransactionResponse(AIResponse):
    action: Literal["select_transaction"]
    selection: int = Field(gt=0)
    apply_changes: bool = False


class UpdateTransactionResponse(AIResponse):
    action: Literal["update_transaction"]
    filters: SearchTransactionArguments | None = None
    selection: int | None = Field(default=None, gt=0)
    changes: TransactionChanges

    @field_validator("changes", mode="before")
    @classmethod
    def omit_null_changes(
        cls, value: JsonValue | TransactionChanges
    ) -> JsonValue | TransactionChanges:
        if isinstance(value, dict):
            return {
                name: change
                for name, change in value.items()
                if change is not None or name not in TransactionChanges.model_fields
            }
        return value

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        if (self.filters is None) == (self.selection is None):
            raise ValueError("Specify either search filters or a displayed selection")
        if self.filters is not None and not any(
            value is not None for value in self.filters.model_dump().values()
        ):
            raise ValueError("Specify at least one search condition for an update")
        return self


class TextResponse(AIResponse):
    action: Literal["respond"]
    message: str = Field(min_length=1)


class DeleteTransactionResponse(AIResponse):
    action: Literal["delete_transaction"]
    filters: SearchTransactionArguments | None = None
    selection: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        if (self.filters is None) == (self.selection is None):
            raise ValueError("Specify either search filters or a displayed selection")
        if self.filters is not None and not any(
            value is not None for value in self.filters.model_dump().values()
        ):
            raise ValueError("Specify at least one search condition for deletion")
        return self


class ConfirmDeleteTransactionResponse(AIResponse):
    action: Literal["confirm_delete_transaction"]
    confirmed: bool = Field(strict=True)


AIResponseType = Annotated[
    CreateCurrencyResponse
    | CreateDebtResponse
    | UpdateDebtResponse
    | GetDebtsResponse
    | GetDebtResponse
    | DeleteDebtResponse
    | ConfirmDeleteDebtResponse
    | CreateAccountResponse
    | UpdateAccountResponse
    | GetAccountsResponse
    | GetAccountResponse
    | AssignAccountTransactionsResponse
    | ConfirmAssignAccountTransactionsResponse
    | CreateCategoryResponse
    | UpdateCategoryResponse
    | CreateTransactionResponse
    | SearchTransactionsResponse
    | MoreTransactionsResponse
    | SelectTransactionResponse
    | UpdateTransactionResponse
    | DeleteTransactionResponse
    | ConfirmDeleteTransactionResponse
    | ClarifyResponse
    | TextResponse,
    Field(discriminator="action"),
]

ai_response_adapter: TypeAdapter[AIResponseType] = TypeAdapter(AIResponseType)
