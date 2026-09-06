import asyncio
import json

from pydantic import ValidationError

from ai.client import AIClient
from ai.memory import ConversationMemory, TransactionState
from ai.models import (
    AIResponseType,
    ClarifyResponse,
    ConfirmDeleteTransactionResponse,
    CreateCategoryResponse,
    CreateCurrencyResponse,
    CreateTransactionResponse,
    DeleteTransactionResponse,
    ExpenseTransactionItem,
    IncomingTransactionItem,
    MoreTransactionsResponse,
    SearchTransactionArguments,
    SearchTransactionsResponse,
    SelectTransactionResponse,
    TextResponse,
    UpdateCategoryResponse,
    UpdateTransactionResponse,
    ai_response_adapter,
)
from ai.prompts import build_system_prompt
from domain.enums import CategoryType
from schemas.category import GetAllCategoriesCommand, UpdateCategoryCommand
from schemas.expense_transaction import (
    DeleteExpenseTransactionCommand,
    ExpenseTransactionResult,
    GetExpenseTransactionCommand,
    UpdateExpenseTransactionCommand,
)
from schemas.incoming_transaction import (
    DeleteIncomingTransactionCommand,
    GetIncomingTransactionCommand,
    IncomingTransactionResult,
    UpdateIncomingTransactionCommand,
)
from schemas.transaction import TransactionSnapshot
from services.category_service import CategoryService
from services.currency_service import CurrencyService
from services.expense_transaction_service import ExpenseTransactionService
from services.incoming_transaction_service import IncomingTransactionService
from settings import settings

type TransactionResult = ExpenseTransactionResult | IncomingTransactionResult


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
        self._transactions = (
            memory.transactions if memory is not None else TransactionState()
        )

    async def interpret(
        self,
        user_message: str,
    ) -> AIResponseType:
        categories = await self._category_service.get_all(
            GetAllCategoriesCommand(),
        )
        system_prompt = build_system_prompt(categories)
        system_prompt += self._transaction_context()

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

        if not isinstance(
            response,
            (
                DeleteTransactionResponse,
                ConfirmDeleteTransactionResponse,
                MoreTransactionsResponse,
                ClarifyResponse,
            ),
        ):
            self._transactions.choosing_delete = False
            self._transactions.pending_delete = None

        if isinstance(response, DeleteTransactionResponse):
            answer = await self._prepare_transaction_deletion(response)
        elif isinstance(response, ConfirmDeleteTransactionResponse):
            answer = await self._confirm_transaction_deletion(response.confirmed)
        elif isinstance(response, SearchTransactionsResponse):
            self._transactions.pending_changes = None
            await self._find_transactions(response.filters)
            self._transactions.page_size = response.limit
            answer = self._show_next_transactions()
        elif isinstance(response, MoreTransactionsResponse):
            self._transactions.pending_delete = None
            if response.limit is not None:
                self._transactions.page_size = response.limit
            answer = self._show_next_transactions()
        elif isinstance(response, UpdateTransactionResponse):
            answer = await self._update_transaction(response)
        elif isinstance(response, SelectTransactionResponse):
            answer = await self._select_transaction(
                response.selection, apply_changes=response.apply_changes
            )
        elif isinstance(response, CreateCurrencyResponse):
            self._transactions.pending_changes = None
            answer = await self._create_currency(response)
        elif isinstance(response, CreateCategoryResponse):
            self._transactions.pending_changes = None
            answer = await self._create_category(response)
        elif isinstance(response, UpdateCategoryResponse):
            self._transactions.pending_changes = None
            answer = await self._update_category(response)
        elif isinstance(response, CreateTransactionResponse):
            answer = await self._create_transactions(response)
        elif isinstance(response, (ClarifyResponse, TextResponse)):
            if isinstance(response, TextResponse):
                self._transactions.pending_changes = None
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
        self._transactions.results = []
        self._transactions.shown_count = 0
        self._transactions.pending_changes = None

        for item in response.transactions:
            if isinstance(item, ExpenseTransactionItem):
                expense = await self._expense_service.create(
                    item.arguments,
                )
                self._transactions.results.append(expense)
                self._transactions.shown_count += 1

                messages.append(
                    f"Добавлен расход «{expense.name}» "
                    f"на сумму {expense.amount} "
                    f"{expense.currency.code}."
                )

            elif isinstance(item, IncomingTransactionItem):
                income = await self._incoming_service.create(
                    item.arguments,
                )
                self._transactions.results.append(income)
                self._transactions.shown_count += 1

                messages.append(
                    f"Добавлен доход «{income.name}» "
                    f"на сумму {income.amount} "
                    f"{income.currency.code}."
                )

        return "\n".join(messages)

    def _transaction_context(self) -> str:
        displayed = [
            {"selection": index, "description": self._format_transaction(item)}
            for index, item in enumerate(
                self._transactions.results[: self._transactions.shown_count], start=1
            )
        ]
        pending = (
            self._transactions.pending_changes.model_dump_json(exclude_unset=True)
            if self._transactions.pending_changes is not None
            else "нет"
        )
        deletion = (
            self._format_transaction(self._transactions.pending_delete)
            if self._transactions.pending_delete is not None
            else "нет"
        )
        return (
            "\n\nПОКАЗАННЫЕ ИЛИ ТОЛЬКО ЧТО СОЗДАННЫЕ ОПЕРАЦИИ:\n"
            + json.dumps(displayed, ensure_ascii=False)
            + f"\nОЖИДАЮЩИЕ ВЫБОРА ИЗМЕНЕНИЯ: {pending}"
            + f"\nРАЗМЕР ПОРЦИИ ТРАНЗАКЦИЙ: {self._transactions.page_size}"
            + f"\nВЫБОР ОПЕРАЦИИ ДЛЯ УДАЛЕНИЯ: {self._transactions.choosing_delete}"
            + f"\nУДАЛЕНИЕ ОЖИДАЕТ ПОДТВЕРЖДЕНИЯ: {deletion}"
        )

    @staticmethod
    def _format_transaction(transaction: TransactionResult) -> str:
        direction = (
            "Расход" if isinstance(transaction, ExpenseTransactionResult) else "Доход"
        )
        local = transaction.occurred_at.astimezone(settings.timezone_info)
        return (
            f"{local:%d.%m.%Y %H:%M:%S} — {direction} «{transaction.name}» — "
            f"{transaction.amount:.2f} {transaction.currency.code} — "
            f"{transaction.category.name}"
        )

    async def _find_transactions(self, filters: SearchTransactionArguments) -> None:
        self._transactions.results = []
        self._transactions.shown_count = 0
        self._transactions.page_size = 10
        arguments = filters.model_dump(exclude={"direction"})
        if filters.direction != "income":
            self._transactions.results.extend(
                await self._expense_service.get(
                    GetExpenseTransactionCommand.model_validate(arguments)
                )
            )
        if filters.direction != "expense":
            self._transactions.results.extend(
                await self._incoming_service.get(
                    GetIncomingTransactionCommand.model_validate(arguments)
                )
            )
        self._transactions.results.sort(
            key=lambda item: (
                item.occurred_at,
                isinstance(item, ExpenseTransactionResult),
                item.id,
            ),
            reverse=True,
        )

    def _show_next_transactions(self) -> str:
        if not self._transactions.results:
            return (
                "Транзакции по указанным условиям не найдены. Уточните условия поиска."
            )
        if self._transactions.shown_count >= len(self._transactions.results):
            return "Все найденные транзакции уже показаны."
        start = self._transactions.shown_count
        self._transactions.shown_count = min(
            start + self._transactions.page_size, len(self._transactions.results)
        )
        lines = [f"Найдено транзакций: {len(self._transactions.results)}."]
        lines.extend(
            f"{index + 1}. {self._format_transaction(self._transactions.results[index])}"
            for index in range(start, self._transactions.shown_count)
        )
        if self._transactions.shown_count < len(self._transactions.results):
            lines.append("Чтобы продолжить список, скажите «покажи ещё».")
        if self._transactions.pending_changes is not None:
            lines.append(
                "Какую операцию изменить? Можно указать название, время или позицию."
            )
        if self._transactions.choosing_delete:
            lines.append(
                "Какую операцию удалить? Укажите название, время или позицию. "
                "После выбора потребуется подтверждение."
            )
        return "\n".join(lines)

    async def _prepare_transaction_deletion(
        self, response: DeleteTransactionResponse
    ) -> str:
        self._transactions.pending_changes = None
        self._transactions.choosing_delete = False
        self._transactions.pending_delete = None
        selection = response.selection
        if response.filters is not None:
            await self._find_transactions(response.filters)
            if not self._transactions.results:
                return self._show_next_transactions()
            if len(self._transactions.results) != 1:
                self._transactions.choosing_delete = True
                return self._show_next_transactions()
            self._transactions.shown_count = 1
            selection = 1
        if selection is None or selection > self._transactions.shown_count:
            return "Такой позиции нет в показанном списке. Уточните, какую операцию удалить."
        current = self._transactions.results[selection - 1]
        self._transactions.pending_delete = current
        return (
            f"Удалить эту транзакцию?\n{self._format_transaction(current)}\n"
            "Восстановление не предусмотрено. Ответьте «да, удалить» или «отмена»."
        )

    async def _confirm_transaction_deletion(self, confirmed: bool) -> str:
        current = self._transactions.pending_delete
        self._transactions.pending_delete = None
        self._transactions.choosing_delete = False
        if not confirmed:
            return "Удаление отменено."
        if current is None:
            return (
                "Нет транзакции, ожидающей подтверждения удаления. Сначала выберите её."
            )
        expected = TransactionSnapshot(
            name=current.name,
            category_id=current.category.id,
            amount=current.amount,
            currency_code=current.currency.code,
            occurred_at=current.occurred_at,
        )
        if isinstance(current, ExpenseTransactionResult):
            await self._expense_service.delete(
                DeleteExpenseTransactionCommand(id=current.id, expected=expected)
            )
        else:
            await self._incoming_service.delete(
                DeleteIncomingTransactionCommand(id=current.id, expected=expected)
            )
        self._transactions.clear()
        return (
            f"Транзакция удалена: {self._format_transaction(current)}.\n"
            "Для дальнейшей работы со списком выполните поиск заново."
        )

    async def _update_transaction(self, response: UpdateTransactionResponse) -> str:
        self._transactions.pending_changes = None
        if response.filters is not None:
            await self._find_transactions(response.filters)
            if not self._transactions.results:
                return self._show_next_transactions()
            self._transactions.pending_changes = response.changes
            if len(self._transactions.results) != 1:
                return self._show_next_transactions()
            self._transactions.shown_count = 1
            return await self._select_transaction(1, apply_changes=True)
        self._transactions.pending_changes = response.changes
        if response.selection is None:
            raise ValueError("A transaction selection is required")
        return await self._select_transaction(response.selection, apply_changes=True)

    async def _select_transaction(
        self, selection: int, *, apply_changes: bool = False
    ) -> str:
        if not apply_changes:
            self._transactions.pending_changes = None
        if selection > self._transactions.shown_count:
            return "Такой позиции нет в показанном списке. Уточните, какую операцию выбрать."
        current = self._transactions.results[selection - 1]
        changes = self._transactions.pending_changes
        if changes is None:
            return self._format_transaction(current)
        self._transactions.pending_changes = None
        expected = TransactionSnapshot(
            name=current.name,
            category_id=current.category.id,
            amount=current.amount,
            currency_code=current.currency.code,
            occurred_at=current.occurred_at,
        )
        updated: TransactionResult
        if isinstance(current, ExpenseTransactionResult):
            updated = await self._expense_service.update(
                UpdateExpenseTransactionCommand(
                    id=current.id, changes=changes, expected=expected
                )
            )
        else:
            updated = await self._incoming_service.update(
                UpdateIncomingTransactionCommand(
                    id=current.id, changes=changes, expected=expected
                )
            )
        self._transactions.results[selection - 1] = updated
        if current == updated:
            return "Изменений нет. " + self._format_transaction(updated)
        return (
            "Транзакция изменена.\n"
            f"Было: {self._format_transaction(current)}\n"
            f"Стало: {self._format_transaction(updated)}"
        )

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
