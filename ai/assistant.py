import asyncio
import json
from datetime import datetime
from decimal import Decimal

from pydantic import ValidationError

from ai.client import AIClient
from ai.memory import ConversationMemory, TransactionState
from ai.models import (
    AIResponseType,
    AssignAccountTransactionsResponse,
    ClarifyResponse,
    ConfirmAssignAccountTransactionsResponse,
    ConfirmDeleteDebtResponse,
    ConfirmDeleteTransactionResponse,
    CreateAccountResponse,
    CreateCategoryResponse,
    CreateCurrencyResponse,
    CreateDebtResponse,
    CreateTransactionResponse,
    DeleteDebtResponse,
    DeleteTransactionResponse,
    ExpenseTransactionItem,
    GetAccountResponse,
    GetAccountsResponse,
    GetDebtResponse,
    GetDebtsResponse,
    IncomingTransactionItem,
    MoreTransactionsResponse,
    SearchTransactionArguments,
    SearchTransactionsResponse,
    SelectTransactionResponse,
    TextResponse,
    UpdateAccountResponse,
    UpdateCategoryResponse,
    UpdateDebtResponse,
    UpdateTransactionResponse,
    ai_response_adapter,
)
from ai.prompts import ACCOUNT_PROMPT, DEBT_PROMPT, build_system_prompt
from domain.enums import AccountType, CategoryType, DebtDirection
from schemas.account import (
    AccountResult,
    AssignAccountTransactionsCommand,
    GetAccountByIdCommand,
    GetAllAccountsCommand,
)
from schemas.category import GetAllCategoriesCommand, UpdateCategoryCommand
from schemas.debt import DebtResult, DeleteDebtCommand, GetAllDebtsCommand
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
from services.account_service import AccountService
from services.category_service import CategoryService
from services.currency_service import CurrencyService
from services.debt_service import DebtService
from services.exceptions import (
    AccountNotFoundError,
    AccountUnavailableError,
    ServiceError,
)
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
        account_service: AccountService | None = None,
        debt_service: DebtService | None = None,
    ) -> None:
        self._client = client
        self._currency_service = currency_service
        self._expense_service = expense_service
        self._incoming_service = incoming_service
        self._category_service = category_service
        self._account_service = account_service
        self._debt_service = debt_service
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
        if self._account_service is not None:
            accounts = await self._account_service.get_all(
                GetAllAccountsCommand(include_inactive=True)
            )
            system_prompt += (
                ACCOUNT_PROMPT
                + "\n"
                + json.dumps(
                    [account.model_dump(mode="json") for account in accounts],
                    ensure_ascii=False,
                )
            )
            system_prompt += (
                f"\nPENDING_ACCOUNT_ASSIGNMENT: {self._transactions.pending_account_id}"
            )

        if self._debt_service is not None:
            debts = await self._debt_service.get_all(
                GetAllDebtsCommand(include_repaid=True)
            )
            system_prompt += DEBT_PROMPT + json.dumps(
                [debt.model_dump(mode="json") for debt in debts], ensure_ascii=False
            )
            pending_debt = self._transactions.pending_debt_delete
            system_prompt += "\nPENDING_DEBT_DELETION: " + (
                pending_debt.model_dump_json() if pending_debt is not None else "нет"
            )

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
            response, (DeleteDebtResponse, ConfirmDeleteDebtResponse, ClarifyResponse)
        ):
            self._transactions.pending_debt_delete = None

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

        if not isinstance(
            response,
            (
                AssignAccountTransactionsResponse,
                ConfirmAssignAccountTransactionsResponse,
                ClarifyResponse,
            ),
        ):
            self._transactions.pending_account_id = None

        if isinstance(
            response,
            (
                CreateAccountResponse,
                UpdateAccountResponse,
                GetAccountsResponse,
                GetAccountResponse,
                AssignAccountTransactionsResponse,
                ConfirmAssignAccountTransactionsResponse,
            ),
        ):
            self._transactions.pending_changes = None
            try:
                answer = await self._handle_account(response)
            except ServiceError as error:
                answer = f"⚠️ {error}"
        elif isinstance(
            response,
            (
                CreateDebtResponse,
                UpdateDebtResponse,
                GetDebtsResponse,
                GetDebtResponse,
                DeleteDebtResponse,
                ConfirmDeleteDebtResponse,
            ),
        ):
            self._transactions.pending_changes = None
            try:
                answer = await self._handle_debt(response)
            except ServiceError as error:
                answer = f"⚠️ {error}"
        elif isinstance(response, DeleteTransactionResponse):
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
            try:
                answer = await self._create_transactions(response)
            except (AccountNotFoundError, AccountUnavailableError) as error:
                answer = f"⚠️ {error}"
        elif isinstance(response, (ClarifyResponse, TextResponse)):
            if isinstance(response, TextResponse):
                self._transactions.pending_changes = None
            answer = response.message
        else:
            raise TypeError(f"Unsupported AI response: {type(response).__name__}")

        if self._memory is not None:
            self._memory.add(user_message, response.model_dump_json())

        return answer

    @staticmethod
    def _format_account(account: AccountResult, *, compact: bool = False) -> str:
        symbol = "₽" if account.currency_code == "RUB" else account.currency_code
        balance = f"{account.balance:,.2f}".replace(",", " ").replace(".", ",")
        opening = f"{account.opening_balance:,.2f}".replace(",", " ").replace(".", ",")
        icon = "💳" if account.is_active else "💤"
        started = account.opening_balance_at.astimezone(settings.timezone_info)
        credit = ""
        if (
            account.account_type is AccountType.CREDIT
            and account.credit_limit is not None
        ):
            credit = f"{account.credit_limit:,.2f}".replace(",", " ").replace(".", ",")
        if compact:
            line = f"{icon} {account.name} — {balance} {symbol}"
            if account.is_default:
                line += " ⭐"
            if credit:
                line += f" · лимит {credit} {symbol}"
            if not account.is_active:
                line += " · деактивирован"
            return line
        lines = [
            f"{icon} {account.name} · {account.currency_code}",
            f"💰 Расчётный остаток: {balance} {symbol}",
            f"📍 Начальный остаток: {opening} {symbol} на {started:%d.%m.%Y, %H:%M:%S}",
        ]
        if credit:
            lines.append(f"🏦 Кредитный лимит: {credit} {symbol}")
        if account.is_default:
            lines.append("⭐ По умолчанию")
        if not account.is_active:
            lines.append("💤 Деактивирован")
        return "\n".join(lines)

    @staticmethod
    def _format_debt(debt: DebtResult) -> str:
        direction = (
            "🔴 Я должен"
            if debt.direction is DebtDirection.PAYABLE
            else "🟢 Мне должны"
        )
        priorities = {
            1: "⚪ Очень низкий",
            2: "🔵 Низкий",
            3: "🟡 Обычный",
            4: "🟠 Высокий",
            5: "🔴 Критический",
        }
        amount = f"{debt.amount:,.2f}".replace(",", " ").replace(".", ",")
        symbol = "₽" if debt.currency_code == "RUB" else debt.currency_code
        lines = [
            f"📋 {debt.name} · №{debt.id}",
            f"{direction} · 💰 Остаток: {amount} {symbol}",
            f"{priorities[debt.priority]} · приоритет {debt.priority}/5",
            f"📅 Остаток актуален на {debt.as_of_date:%d.%m.%Y}",
        ]
        if debt.amount == 0:
            lines.append("✅ Погашен")
        elif (
            debt.due_date is not None
            and debt.due_date < datetime.now(settings.timezone_info).date()
        ):
            lines.append("⏰ Срок возврата истёк")
        if debt.counterparty:
            lines.append(f"👤 Контрагент: {debt.counterparty}")
        if debt.account is not None:
            lines.append(f"💳 Счёт: {debt.account.name} · справочно")
        if debt.due_date is not None:
            lines.append(f"🗓️ Срок возврата: {debt.due_date:%d.%m.%Y}")
        if debt.description:
            lines.append(f"📝 {debt.description}")
        return "\n".join(lines)

    async def _handle_debt(
        self,
        response: CreateDebtResponse
        | UpdateDebtResponse
        | GetDebtsResponse
        | GetDebtResponse
        | DeleteDebtResponse
        | ConfirmDeleteDebtResponse,
    ) -> str:
        service = self._debt_service
        if service is None:
            return "⚠️ Учёт долгов недоступен."
        if isinstance(response, DeleteDebtResponse):
            self._transactions.pending_debt_delete = None
            debt = await service.get_by_id(response.arguments)
            self._transactions.pending_debt_delete = debt
            return (
                "⚠️ Удалить это долговое обязательство?\n"
                + self._format_debt(debt)
                + "\n\nКарточка будет удалена без возможности восстановления. "
                "Баланс счёта не изменится.\nОтветьте «да, удалить» или «отмена»."
            )
        if isinstance(response, ConfirmDeleteDebtResponse):
            pending_debt = self._transactions.pending_debt_delete
            self._transactions.pending_debt_delete = None
            if not response.confirmed:
                return "↩️ Удаление долга отменено."
            if pending_debt is None:
                return "⚠️ Нет долга, ожидающего подтверждения удаления. Сначала выберите карточку."
            await service.delete(
                DeleteDebtCommand(id=pending_debt.id, expected=pending_debt)
            )
            return f"🗑️ Долговое обязательство «{pending_debt.name}» удалено."
        if isinstance(response, CreateDebtResponse):
            return "✅ Долг добавлен.\n" + self._format_debt(
                await service.create(response.arguments)
            )
        if isinstance(response, UpdateDebtResponse):
            return "✏️ Долг обновлён.\n" + self._format_debt(
                await service.update(response.arguments)
            )
        if isinstance(response, GetDebtResponse):
            return self._format_debt(await service.get_by_id(response.arguments))
        debts = await service.get_all(response.arguments)
        summary = service.get_summary(debts)
        lines = ["💰 Общая сумма долговых обязательств"]
        totals: tuple[tuple[str, dict[str, Decimal]], ...] = (
            ("🔴 Я должен", summary.payable),
            ("🟢 Мне должны", summary.receivable),
        )
        for label, amounts in totals:
            if not amounts:
                lines.append(f"{label}: нет непогашенных долгов")
                continue
            lines.append(f"{label}:")
            for currency_code, amount in sorted(amounts.items()):
                formatted = f"{amount:,.2f}".replace(",", " ").replace(".", ",")
                symbol = "₽" if currency_code == "RUB" else currency_code
                lines.append(f"  • {formatted} {symbol}")
        if debts:
            lines.append(f"\n📋 Карточек: {len(debts)} · по убыванию приоритета")
            lines.extend("\n" + self._format_debt(debt) for debt in debts)
        else:
            lines.append("\n📭 Долгов для показа нет.")
        if not response.arguments.include_repaid:
            lines.append(
                "\n💡 Погашенные скрыты. Скажите «покажи все долги» для полного списка."
            )
        return "\n".join(lines)

    async def _handle_account(
        self,
        response: CreateAccountResponse
        | UpdateAccountResponse
        | GetAccountsResponse
        | GetAccountResponse
        | AssignAccountTransactionsResponse
        | ConfirmAssignAccountTransactionsResponse,
    ) -> str:
        service = self._account_service
        if service is None:
            return "⚠️ Управление счетами недоступно."
        if isinstance(response, CreateAccountResponse):
            return "✅ Счёт создан.\n" + self._format_account(
                await service.create(response.arguments)
            )
        if isinstance(response, UpdateAccountResponse):
            account = await service.update(response.arguments)
            self._transactions.clear()
            return f"✏️ Счёт «{account.name}» обновлён.\n" + self._format_account(
                account
            )
        if isinstance(response, GetAccountsResponse):
            accounts = await service.get_all(response.arguments)
            return (
                "\n".join(
                    self._format_account(account, compact=True) for account in accounts
                )
                or "💳 Счетов пока нет."
            )
        if isinstance(response, GetAccountResponse):
            return self._format_account(await service.get_by_id(response.arguments))
        if isinstance(response, AssignAccountTransactionsResponse):
            self._transactions.pending_account_id = None
            account = await service.get_by_id(
                GetAccountByIdCommand(id=response.arguments.id)
            )
            if not account.is_active:
                return "⚠️ Сначала восстановите счёт."
            self._transactions.pending_account_id = account.id
            return (
                f"🔗 Привязать все операции без счёта в валюте {account.currency_code} "
                f"к счёту «{account.name}»? Другие валюты останутся без счёта. "
                "Операции до точки отсчёта и в сам момент отсчёта не меняют остаток. "
                "\nОтветьте «да, привязать» или «отмена»."
            )
        account_id = self._transactions.pending_account_id
        self._transactions.pending_account_id = None
        if not response.confirmed:
            return "↩️ Привязка отменена."
        if account_id is None:
            return "⚠️ Нет привязки, ожидающей подтверждения. Сначала выберите счёт."
        count = await service.assign_transactions(
            AssignAccountTransactionsCommand(id=account_id)
        )
        self._transactions.clear()
        account = await service.get_by_id(GetAccountByIdCommand(id=account_id))
        return (
            f"✅ К счёту «{account.name}» привязано операций: {count}.\n"
            + self._format_account(account)
        )

    async def _create_category(
        self,
        response: CreateCategoryResponse,
    ) -> str:
        category = await self._category_service.create(response.arguments)
        direction_name = {
            CategoryType.income: "Доходы",
            CategoryType.expense: "Расходы",
        }[category.direction]
        return f"✅ Добавлена категория «{category.name}» для направления «{direction_name}»."

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
            return f"✏️ Категория «{category.name}» обновлена, описание удалено."

        return f"✏️ Категория «{category.name}» обновлена."

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
                    f"🔴 Добавлен расход «{expense.name}» "
                    f"на сумму {expense.amount} "
                    f"{expense.currency.code} — {expense.account.name if expense.account else 'без счёта'}."
                )

            elif isinstance(item, IncomingTransactionItem):
                income = await self._incoming_service.create(
                    item.arguments,
                )
                self._transactions.results.append(income)
                self._transactions.shown_count += 1

                messages.append(
                    f"🟢 Добавлен доход «{income.name}» "
                    f"на сумму {income.amount} "
                    f"{income.currency.code} — {income.account.name if income.account else 'без счёта'}."
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
            "🔴 Расход"
            if isinstance(transaction, ExpenseTransactionResult)
            else "🟢 Доход"
        )
        local = transaction.occurred_at.astimezone(settings.timezone_info)
        return (
            f"{local:%d.%m.%Y %H:%M:%S} — {direction} «{transaction.name}» — "
            f"{transaction.amount:.2f} {transaction.currency.code} — "
            f"{transaction.category.name} — "
            f"{transaction.account.name if transaction.account is not None else 'без счёта'}"
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
        lines = [f"🔎 Найдено транзакций: {len(self._transactions.results)}."]
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
            f"⚠️ Удалить эту транзакцию?\n{self._format_transaction(current)}\n"
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
            account_id=current.account_id,
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
            f"🗑️ Транзакция удалена: {self._format_transaction(current)}.\n"
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
            account_id=current.account_id,
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
            "✏️ Транзакция изменена.\n"
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
            f"✅ Добавлена валюта «{currency.name}» "
            f"с кодом {currency.code} и типом {currency.currency_type.value}."
        )
