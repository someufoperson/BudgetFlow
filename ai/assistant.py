import asyncio

from ai.client import AIClient
from ai.models import (
    AIResponseType,
    ClarifyResponse,
    CreateCurrencyResponse,
    CreateTransactionResponse,
    ExpenseTransactionItem,
    IncomingTransactionItem,
    TextResponse,
    ai_response_adapter,
)
from ai.prompts import SYSTEM_PROMPT
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
    ) -> None:
        self._client = client
        self._currency_service = currency_service
        self._expense_service = expense_service
        self._incoming_service = incoming_service

    async def interpret(
        self,
        user_message: str,
    ) -> AIResponseType:
        raw_response = await asyncio.to_thread(
            self._client.complete,
            SYSTEM_PROMPT,
            user_message,
        )

        return ai_response_adapter.validate_json(raw_response)

    async def handle_message(
        self,
        user_message: str,
    ) -> str:
        response = await self.interpret(user_message)

        if isinstance(response, CreateCurrencyResponse):
            return await self._create_currency(response)

        if isinstance(response, CreateTransactionResponse):
            return await self._create_transactions(response)

        if isinstance(response, (ClarifyResponse, TextResponse)):
            return response.message

        raise RuntimeError(f"Unsupported AI response: {type(response).__name__}")

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
