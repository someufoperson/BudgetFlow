import asyncio

from ai.client import AIClient
from ai.models import (
    AIResponseType,
    ClarifyResponse,
    CreateExpenseResponse,
    CreateIncomingResponse,
    TextResponse,
    ai_response_adapter,
)
from ai.prompts import SYSTEM_PROMPT
from services.expense_transaction_service import ExpenseTransactionService
from services.incoming_transaction_service import IncomingTransactionService


class Assistant:
    def __init__(
        self,
        client: AIClient,
        expense_service: ExpenseTransactionService,
        incoming_service: IncomingTransactionService,
    ) -> None:
        self._client = client
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

        if isinstance(response, CreateExpenseResponse):
            return await self._create_expense(response)

        if isinstance(response, CreateIncomingResponse):
            return await self._create_income(response)

        if isinstance(response, (ClarifyResponse, TextResponse)):
            return response.message

        raise RuntimeError(f"Unsupported AI response: {type(response).__name__}")

    async def _create_expense(
        self,
        response: CreateExpenseResponse,
    ) -> str:
        transaction = await self._expense_service.create(
            response.arguments,
        )

        return (
            f"Добавлен расход «{transaction.name}» "
            f"на сумму {transaction.amount} "
            f"{response.arguments.currency_code}."
        )

    async def _create_income(
        self,
        response: CreateIncomingResponse,
    ) -> str:
        transaction = await self._incoming_service.create(
            response.arguments,
        )

        return (
            f"Добавлен доход «{transaction.name}» "
            f"на сумму {transaction.amount} "
            f"{response.arguments.currency_code}."
        )
