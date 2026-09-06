import asyncio

from pydantic import ValidationError

from ai.client import AIClient
from ai.memory import ConversationMemory
from ai.models import (
    AIResponseType,
    ClarifyResponse,
    CreateCategoryResponse,
    CreateCurrencyResponse,
    CreateTransactionResponse,
    ExpenseTransactionItem,
    IncomingTransactionItem,
    TextResponse,
    UpdateCategoryResponse,
    ai_response_adapter,
)
from ai.prompts import build_system_prompt
from domain.enums import CategoryType
from schemas.category import GetAllCategoriesCommand, UpdateCategoryCommand
from services.category_service import CategoryService
from services.currency_service import CurrencyService
from services.expense_transaction_service import ExpenseTransactionService
from services.incoming_transaction_service import IncomingTransactionService


class Assistant:
    def __init__(
        self,
        client: AIClient,
        currency_service: CurrencyService,
        expense_service: ExpenseTransactionService,
        incoming_service: IncomingTransactionService,
        category_service: CategoryService,
        memory: ConversationMemory | None = None,
    ) -> None:
        self._client = client
        self._currency_service = currency_service
        self._expense_service = expense_service
        self._incoming_service = incoming_service
        self._category_service = category_service
        self._memory = memory

    async def interpret(
        self,
        user_message: str,
    ) -> AIResponseType:
        categories = await self._category_service.get_all(
            GetAllCategoriesCommand(),
        )
        system_prompt = build_system_prompt(categories)

        if self._memory is None:
            raw_response = await asyncio.to_thread(
                self._client.complete,
                system_prompt,
                user_message,
            )
        else:
            raw_response = await asyncio.to_thread(
                self._client.complete,
                system_prompt,
                user_message,
                self._memory.messages(),
            )

        try:
            return ai_response_adapter.validate_json(raw_response)
        except ValidationError:
            print(f"Некорректный ответ AI: {raw_response!r}", flush=True)
            raise

    async def handle_message(
        self,
        user_message: str,
    ) -> str:
        response = await self.interpret(user_message)

        if isinstance(response, CreateCurrencyResponse):
            answer = await self._create_currency(response)
        elif isinstance(response, CreateCategoryResponse):
            answer = await self._create_category(response)
        elif isinstance(response, UpdateCategoryResponse):
            answer = await self._update_category(response)
        elif isinstance(response, CreateTransactionResponse):
            answer = await self._create_transactions(response)
        elif isinstance(response, (ClarifyResponse, TextResponse)):
            answer = response.message
        else:
            raise TypeError(f"Unsupported AI response: {type(response).__name__}")

        if self._memory is not None:
            self._memory.add(user_message, response.model_dump_json())

        return answer

    async def _create_category(
        self,
        response: CreateCategoryResponse,
    ) -> str:
        category = await self._category_service.create(response.arguments)
        direction_name = {
            CategoryType.income: "Доходы",
            CategoryType.expense: "Расходы",
        }[category.direction]
        return (
            f"Добавлена категория «{category.name}» для направления «{direction_name}»."
        )

    async def _update_category(
        self,
        response: UpdateCategoryResponse,
    ) -> str:
        arguments = response.arguments

        if arguments.name is not None and "description" in arguments.model_fields_set:
            command = UpdateCategoryCommand(
                id=arguments.id,
                name=arguments.name,
                description=arguments.description,
            )
        elif arguments.name is not None:
            command = UpdateCategoryCommand(id=arguments.id, name=arguments.name)
        else:
            command = UpdateCategoryCommand(
                id=arguments.id,
                description=arguments.description,
            )

        category = await self._category_service.update(command)

        if (
            "description" in arguments.model_fields_set
            and arguments.description is None
        ):
            return f"Категория «{category.name}» обновлена, описание удалено."

        return f"Категория «{category.name}» обновлена."

    async def _create_transactions(
        self,
        response: CreateTransactionResponse,
    ) -> str:
        messages: list[str] = []

        for item in response.transactions:
            if isinstance(item, ExpenseTransactionItem):
                expense = await self._expense_service.create(
                    item.arguments,
                )

                messages.append(
                    f"Добавлен расход «{expense.name}» "
                    f"на сумму {expense.amount} "
                    f"{expense.currency.code}."
                )

            elif isinstance(item, IncomingTransactionItem):
                income = await self._incoming_service.create(
                    item.arguments,
                )

                messages.append(
                    f"Добавлен доход «{income.name}» "
                    f"на сумму {income.amount} "
                    f"{income.currency.code}."
                )

        return "\n".join(messages)

    async def _create_currency(
        self,
        response: CreateCurrencyResponse,
    ) -> str:
        currency = await self._currency_service.create(
            response.arguments,
        )

        return (
            f"Добавлена валюта «{currency.name}» "
            f"с кодом {currency.code} и типом {currency.currency_type.value}."
        )
