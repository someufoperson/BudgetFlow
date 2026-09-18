import asyncio
import json
import logging
from copy import deepcopy
from datetime import datetime
from decimal import ROUND_DOWN, Decimal
from hashlib import sha256
from itertools import count

from pydantic import JsonValue, TypeAdapter, ValidationError
from requests import RequestException
from sqlalchemy.exc import SQLAlchemyError

from ai.client import AIClient, request_context
from ai.memory import ConversationMemory, ScreenshotState, TaskState, TransactionState
from ai.models import (
    AIResponseType,
    AllocateSavingsGoalResponse,
    AssignAccountTransactionsResponse,
    ClarifyResponse,
    ConfirmAssignAccountTransactionsResponse,
    ConfirmBalanceAdjustmentResponse,
    ConfirmDeleteDebtResponse,
    ConfirmDeleteTransactionResponse,
    ConfirmDeleteTransferTransactionResponse,
    ConfirmReverseBalanceAdjustmentResponse,
    ConfirmScreenshotTransactionsResponse,
    CreateAccountResponse,
    CreateBalanceAdjustmentResponse,
    CreateCategoryResponse,
    CreateCurrencyResponse,
    CreateDebtResponse,
    CreateSavingsGoalResponse,
    CreateTransactionResponse,
    CreateTransferTransactionResponse,
    DeleteDebtResponse,
    DeleteTransactionResponse,
    DeleteTransferTransactionResponse,
    ExpenseTransactionItem,
    GetAccountResponse,
    GetAccountsResponse,
    GetBalanceAdjustmentResponse,
    GetBalanceAdjustmentsResponse,
    GetDebtResponse,
    GetDebtsResponse,
    GetReportResponse,
    GetSavingsGoalResponse,
    GetSavingsGoalsResponse,
    GetTransferTransactionResponse,
    GetTransferTransactionsResponse,
    IncomingTransactionItem,
    InterpretResponse,
    MoreTransactionsResponse,
    ReconcileAccountResponse,
    ReleaseSavingsGoalResponse,
    ReverseBalanceAdjustmentResponse,
    RouteResponse,
    Scenario,
    SearchTransactionArguments,
    SearchTransactionsResponse,
    SelectTransactionResponse,
    SkipScreenshotTransactionResponse,
    TaskDraft,
    TextResponse,
    UpdateAccountResponse,
    UpdateCategoryResponse,
    UpdateDebtResponse,
    UpdateSavingsGoalResponse,
    UpdateScreenshotTransactionResponse,
    UpdateTransactionResponse,
    UpdateTransferTransactionResponse,
    ai_response_adapter,
)
from ai.prompts import (
    DEBT_INCOME_PROMPT,
    ROUTER_PROMPT,
    build_system_prompt,
)
from domain.enums import AccountType, CategoryType, DebtDirection, SavingsGoalStatus
from schemas.account import (
    AccountBalanceChangeResult,
    AccountHistoryWarning,
    AccountResult,
    AssignAccountTransactionsCommand,
    GetAccountByIdCommand,
    GetAllAccountsCommand,
)
from schemas.balance_adjustment import (
    AccountReconciliationResult,
    BalanceAdjustmentResult,
    BalanceAdjustmentReversalResult,
    CreateBalanceAdjustmentCommand,
    ReconcileAccountCommand,
    ReverseBalanceAdjustmentCommand,
)
from schemas.category import GetAllCategoriesCommand, UpdateCategoryCommand
from schemas.debt import DebtResult, DeleteDebtCommand, GetAllDebtsCommand
from schemas.document import (
    DocumentInput,
    DocumentPage,
    ScreenshotTransactionDraft,
)
from schemas.expense_transaction import (
    CreateExpenseTransactionCommand,
    DeleteExpenseTransactionCommand,
    ExpenseTransactionResult,
    GetExpenseTransactionCommand,
    UpdateExpenseTransactionCommand,
)
from schemas.incoming_transaction import (
    CreateIncomingTransactionCommand,
    DeleteIncomingTransactionCommand,
    GetIncomingTransactionCommand,
    IncomingTransactionResult,
    UpdateIncomingTransactionCommand,
)
from schemas.report import GetReportCommand
from schemas.savings_goal import GetAllSavingsGoalsCommand, SavingsGoalResult
from schemas.transaction import TransactionSnapshot
from schemas.transfer_transaction import (
    DeleteTransferTransactionCommand,
    GetTransferTransactionByIdCommand,
    TransferTransactionDeletionResult,
    TransferTransactionResult,
    UpdateTransferTransactionCommand,
)
from services.account_service import AccountService
from services.balance_adjustment_service import BalanceAdjustmentService
from services.category_service import CategoryService
from services.currency_service import CurrencyService
from services.debt_service import DebtService
from services.document_service import DocumentService
from services.exceptions import (
    AccountBalanceChangedError,
    AccountNotFoundError,
    AccountUnavailableError,
    BalanceAdjustmentReversalChangedError,
    ServiceError,
    TransferTransactionDeletionChangedError,
)
from services.expense_transaction_service import ExpenseTransactionService
from services.incoming_transaction_service import IncomingTransactionService
from services.report_image_service import ReportImageService
from services.report_service import ReportService
from services.savings_goal_service import SavingsGoalService
from services.transaction_time import resolve_occurred_at
from services.transfer_transaction_service import TransferTransactionService
from settings import settings

type TransactionResult = ExpenseTransactionResult | IncomingTransactionResult

logger = logging.getLogger(__name__)
_request_numbers = count(1)


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
        report_service: ReportService | None = None,
        transfer_service: TransferTransactionService | None = None,
        adjustment_service: BalanceAdjustmentService | None = None,
        savings_goal_service: SavingsGoalService | None = None,
    ) -> None:
        self._client = client
        self._currency_service = currency_service
        self._expense_service = expense_service
        self._incoming_service = incoming_service
        self._category_service = category_service
        self._account_service = account_service
        self._debt_service = debt_service
        self._report_service = report_service
        self._transfer_service = transfer_service
        self._adjustment_service = adjustment_service
        self._savings_goal_service = savings_goal_service
        self.report_images: list[DocumentInput] = []
        self._screenshots = (
            memory.screenshots if memory is not None else ScreenshotState()
        )
        self._memory = memory
        self._transactions = (
            memory.transactions if memory is not None else TransactionState()
        )
        self._dialog = memory if memory is not None else ConversationMemory(0)
        self._dialog.transactions = self._transactions
        self._dialog.screenshots = self._screenshots
        self._last_response: AIResponseType | None = None
        self._command_failed = False
        self._handling_message = False
        self._clarification_pending = False

    def _confirmation_candidates(self) -> dict[str, str]:
        state = self._transactions
        candidates: dict[str, str] = {}
        proposals = {
            "confirm_delete_transaction": state.pending_delete,
            "confirm_delete_debt": state.pending_debt_delete,
            "confirm_delete_transfer_transaction": state.pending_transfer_delete,
            "confirm_balance_adjustment": state.pending_adjustment,
            "confirm_reverse_balance_adjustment": state.pending_reversal,
            "debt_income": state.pending_debt_income,
        }
        for action, proposal in proposals.items():
            if proposal is not None:
                candidates[action] = proposal.model_dump_json()
        if state.pending_account_id is not None:
            candidates["confirm_assign_account_transactions"] = str(
                state.pending_account_id
            )
        if self._screenshots.ready and self._screenshots.drafts:
            candidates["confirm_screenshot_transactions"] = "|".join(
                item.model_dump_json() for item in self._screenshots.drafts
            )
        return {
            action: sha256(content.encode()).hexdigest()
            for action, content in candidates.items()
        }

    def _invalidate_confirmation(self) -> None:
        self._dialog.confirmation = None
        state = self._transactions
        state.pending_delete = None
        state.choosing_delete = False
        state.pending_debt_delete = None
        state.pending_debt_income = None
        state.pending_transfer_delete = None
        state.pending_adjustment = None
        state.pending_reversal = None
        state.pending_account_id = None
        self._screenshots.ready = False

    async def interpret(self, user_message: str) -> AIResponseType:
        self._clarification_pending = False
        dialog = self._dialog
        text = user_message.strip().casefold().rstrip(".!?")
        candidates = self._confirmation_candidates()
        confirmation = dialog.confirmation
        simple_agreement = text in {"да", "нет", "подтверждаю", "всё верно", "сохраняй"}
        active_task = (
            dialog.tasks.get(dialog.active_scenario)
            if dialog.active_scenario is not None
            else None
        )
        if (
            simple_agreement
            and confirmation is not None
            and len(candidates) == 1
            and candidates.get(confirmation[0]) == confirmation[1]
        ):
            if confirmation[0] != "debt_income":
                return ai_response_adapter.validate_python(
                    {"action": confirmation[0], "confirmed": text != "нет"}
                )
            if text == "нет":
                self._invalidate_confirmation()
                return TextResponse(
                    action="respond", message="Получение денег не записано."
                )
            route = RouteResponse(scenario="transactions", continuation=True)
        elif simple_agreement and (
            candidates
            or confirmation is not None
            or active_task is None
            or not active_task.awaiting_answer
        ):
            self._invalidate_confirmation()
            return ClarifyResponse(
                action="clarify",
                message="Уточните, какое действие нужно выполнить; прежнее предложение нужно показать заново.",
            )
        elif text == "теперь картинкой" and dialog.last_report is not None:
            self._invalidate_confirmation()
            dialog.active_scenario = "reports"
            return GetReportResponse(
                action="get_report",
                arguments=dialog.last_report.model_copy(update={"format": "image"}),
            )
        else:
            context = {
                "active_scenario": dialog.active_scenario,
                "tasks": {
                    name: {
                        "question": task.question[:300],
                        "request": task.request[:300],
                        "missing_fields": task.draft.missing_fields,
                    }
                    for name, task in dialog.tasks.items()
                },
                "confirmation": confirmation[0] if confirmation else None,
                "screenshots": bool(self._screenshots.drafts),
                "last_report": dialog.last_report is not None,
            }
            routing_prompt = (
                ROUTER_PROMPT
                + "\nСОСТОЯНИЕ: "
                + json.dumps(context, ensure_ascii=False)
            )
            if self._memory is None:
                raw_route = await asyncio.to_thread(
                    self._client.complete, routing_prompt, user_message
                )
            else:
                raw_route = await asyncio.to_thread(
                    self._client.complete,
                    routing_prompt,
                    user_message,
                    self._memory.messages(max_bytes=2400),
                )
            try:
                route = RouteResponse.model_validate_json(raw_route)
            except ValidationError as error:
                logger.warning(
                    "AI validation turn=%s stage=routing errors=%s",
                    request_context.get(),
                    sorted(
                        {
                            item["type"]
                            for item in error.errors(
                                include_input=False,
                                include_context=False,
                                include_url=False,
                            )
                        }
                    ),
                )
                route = RouteResponse(scenario=None, continuation=False)
        scenario = route.scenario
        if scenario is None:
            self._invalidate_confirmation()
            return ClarifyResponse(
                action="clarify",
                message="Уточните одно действие: записать операцию, найти её, показать отчёт или работать со счетами, долгами, целями либо скриншотами?",
            )
        income_continuation = (
            scenario == "transactions"
            and confirmation is not None
            and confirmation[0] == "debt_income"
            and route.continuation
        )
        if (
            not route.continuation or scenario != dialog.active_scenario
        ) and not income_continuation:
            self._invalidate_confirmation()
        previous_scenario = dialog.active_scenario
        dialog.active_scenario = scenario
        task = dialog.tasks.setdefault(
            scenario,
            TaskState(request=user_message, started_turn=request_context.get()),
        )
        categories = (
            await self._category_service.get_all(GetAllCategoriesCommand())
            if scenario in {"transactions", "categories", "search", "screenshots"}
            else []
        )
        system_prompt = build_system_prompt(categories, scenario=scenario)
        if (
            scenario == "transactions"
            and self._transactions.pending_debt_income is not None
        ):
            # Keep constant instructions before all dynamic context.
            system_prompt = DEBT_INCOME_PROMPT + "\n" + system_prompt
        if scenario == "screenshots":
            system_prompt = (
                "Схема строки черновика: "
                + json.dumps(
                    ScreenshotTransactionDraft.model_json_schema(), ensure_ascii=False
                )
                + "\n"
                + system_prompt
            )
        system_prompt += await self._scenario_context(scenario)
        context_scenarios = {scenario, previous_scenario}
        if scenario in {"transactions", "categories"}:
            context_scenarios.update({"transactions", "categories"})
        system_prompt += (
            "\nКОНТЕКСТ ДИАЛОГА (не разрешение на действие): "
            + json.dumps(
                {
                    name: {
                        "request": item.request,
                        "draft": item.draft.model_dump(
                            mode="json", exclude_defaults=True
                        ),
                        "question": item.question,
                        "reply": item.result,
                        "command": item.last_command.model_dump(mode="json")
                        if item.last_command
                        else None,
                        "command_result": item.command_result,
                        "command_status": item.command_status,
                    }
                    for name, item in dialog.tasks.items()
                    if name in context_scenarios
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        previous_draft = task.draft
        updated_draft = previous_draft
        draft_data: JsonValue = None
        try:
            for attempt in range(2):
                if self._memory is None:
                    raw_response = await asyncio.to_thread(
                        self._client.complete, system_prompt, user_message
                    )
                else:
                    raw_response = await asyncio.to_thread(
                        self._client.complete,
                        system_prompt,
                        user_message,
                        self._memory.messages(),
                    )
                payload = TypeAdapter(dict[str, JsonValue]).validate_json(raw_response)
                draft_data = None
                if "response" in payload:
                    draft_data = payload.pop("draft", None)
                    response = InterpretResponse.model_validate(payload).response
                else:
                    response = ai_response_adapter.validate_python(payload)
                if scenario != "search":
                    break
                if isinstance(response, TextResponse) and text in {
                    "отмена",
                    "отмени",
                    "отменить",
                    "не надо",
                }:
                    self._invalidate_confirmation()
                    self._transactions.pending_changes = None
                    draft_data = None
                    response = TextResponse(action="respond", message="Отменено.")
                    break
                if attempt == 0 and isinstance(response, TextResponse):
                    self._invalidate_confirmation()
                    self._transactions.pending_changes = None
                    logger.warning(
                        "AI validation turn=%s stage=action scenario=search action=respond retry=1",
                        request_context.get(),
                    )
                    system_prompt += (
                        "\nПредыдущий ответ respond не выполнил запрос. "
                        "Верни команду просмотра search_transactions, more_transactions "
                        "или select_transaction без apply_changes=true. "
                        "Сохрани все условия и количество из запроса пользователя. "
                        "Не обещай показать данные и не составляй список сам. "
                        "Если требуется уточнение, отмена или изменение данных, "
                        "верни clarify: повторная попытка разрешает только просмотр."
                    )
                    continue
                if attempt == 1 and not (
                    isinstance(
                        response,
                        (
                            SearchTransactionsResponse,
                            MoreTransactionsResponse,
                            ClarifyResponse,
                        ),
                    )
                    or isinstance(response, SelectTransactionResponse)
                    and not response.apply_changes
                ):
                    logger.warning(
                        "AI validation turn=%s stage=action scenario=search action=%s retry=exhausted",
                        request_context.get(),
                        response.action,
                    )
                    self._invalidate_confirmation()
                    self._command_failed = True
                    return ClarifyResponse(
                        action="clarify",
                        message="Не удалось получить команду просмотра от модели. Список операций не загружен.",
                    )
                break
            if isinstance(response, ClarifyResponse) and task.request != user_message:
                task.request += "\n" + user_message
        except ValidationError as error:
            logger.warning(
                "AI validation turn=%s stage=command scenario=%s errors=%s",
                request_context.get(),
                scenario,
                sorted(
                    {
                        item["type"]
                        for item in error.errors(
                            include_input=False,
                            include_context=False,
                            include_url=False,
                        )
                    }
                ),
            )
            self._invalidate_confirmation()
            self._command_failed = True
            return ClarifyResponse(
                action="clarify",
                message="Модель вернула некорректный ответ. Действие не выполнено. Попробуйте повторить запрос.",
            )
        if draft_data is not None:
            try:
                changes = TaskDraft.model_validate(draft_data)
                fields = deepcopy(previous_draft.fields)
                field_updates: list[
                    tuple[dict[str, JsonValue], dict[str, JsonValue]]
                ] = [(fields, changes.fields)]
                while field_updates:
                    target, updates = field_updates.pop()
                    for key, value in updates.items():
                        existing_value = target.get(key)
                        if isinstance(existing_value, dict) and isinstance(value, dict):
                            field_updates.append((existing_value, value))
                        else:
                            target[key] = value
                updated_draft = TaskDraft(
                    fields=fields,
                    missing_fields=(
                        changes.missing_fields
                        if "missing_fields" in changes.model_fields_set
                        else previous_draft.missing_fields
                    ),
                    selected_entities=previous_draft.selected_entities
                    | changes.selected_entities,
                )
                if len(updated_draft.model_dump_json().encode()) > 16000:
                    raise ValueError("Task draft exceeds context budget")
            except (ValidationError, ValueError) as error:
                logger.warning(
                    "AI validation turn=%s stage=draft scenario=%s errors=%s",
                    request_context.get(),
                    scenario,
                    sorted(
                        {
                            item["type"]
                            for item in error.errors(
                                include_input=False,
                                include_context=False,
                                include_url=False,
                            )
                        }
                    )
                    if isinstance(error, ValidationError)
                    else ["draft_budget_exceeded"],
                )
                updated_draft = previous_draft
                if not isinstance(
                    response,
                    (
                        SearchTransactionsResponse,
                        MoreTransactionsResponse,
                        GetAccountResponse,
                        GetAccountsResponse,
                        GetDebtResponse,
                        GetDebtsResponse,
                        GetSavingsGoalResponse,
                        GetSavingsGoalsResponse,
                        GetTransferTransactionResponse,
                        GetTransferTransactionsResponse,
                        GetBalanceAdjustmentResponse,
                        GetBalanceAdjustmentsResponse,
                        GetReportResponse,
                        ClarifyResponse,
                        TextResponse,
                    ),
                ):
                    self._invalidate_confirmation()
                    self._command_failed = True
                    return ClarifyResponse(
                        action="clarify",
                        message="Модель вернула некорректный ответ. Действие не выполнено. Попробуйте повторить запрос.",
                    )
        allowed: dict[Scenario, set[str]] = {
            "transactions": {"create_transactions"},
            "categories": {"create_category", "update_category"},
            "currencies": {"create_currency"},
            "search": {
                "search_transactions",
                "more_transactions",
                "select_transaction",
                "update_transaction",
                "delete_transaction",
                "confirm_delete_transaction",
            },
            "accounts": {
                "create_account",
                "update_account",
                "get_accounts",
                "get_account",
                "assign_account_transactions",
                "confirm_assign_account_transactions",
            },
            "transfers": {
                "create_transfer_transaction",
                "get_transfer_transactions",
                "get_transfer_transaction",
                "update_transfer_transaction",
                "delete_transfer_transaction",
                "confirm_delete_transfer_transaction",
                "reconcile_account",
                "create_balance_adjustment",
                "confirm_balance_adjustment",
                "get_balance_adjustments",
                "get_balance_adjustment",
                "reverse_balance_adjustment",
                "confirm_reverse_balance_adjustment",
            },
            "debts": {
                "create_debt",
                "update_debt",
                "get_debts",
                "get_debt",
                "delete_debt",
                "confirm_delete_debt",
            },
            "goals": {
                "create_savings_goal",
                "update_savings_goal",
                "get_savings_goals",
                "get_savings_goal",
                "allocate_savings_goal",
                "release_savings_goal",
            },
            "reports": {"get_report"},
            "screenshots": {
                "update_screenshot_transaction",
                "skip_screenshot_transaction",
                "confirm_screenshot_transactions",
            },
            "general": set(),
        }
        if response.action not in allowed[scenario] | {"clarify", "respond"}:
            logger.warning(
                "AI validation turn=%s stage=scenario scenario=%s action=%s",
                request_context.get(),
                scenario,
                response.action,
            )
            self._invalidate_confirmation()
            return ClarifyResponse(
                action="clarify",
                message="Уточните одно действие, которое нужно выполнить.",
            )
        if response.action.startswith("confirm_"):
            current = self._confirmation_candidates()
            if current and (
                dialog.confirmation is None
                or len(current) != 1
                or updated_draft != previous_draft
                or dialog.confirmation
                != (response.action, current.get(response.action))
            ):
                self._invalidate_confirmation()
                return ClarifyResponse(
                    action="clarify",
                    message="Предложение изменилось или устарело. Сначала запросите его повторный показ.",
                )
        task.draft = updated_draft
        self._clarification_pending = isinstance(response, ClarifyResponse)
        return response

    async def _scenario_context(self, scenario: Scenario) -> str:
        parts: list[str] = []
        if (
            scenario not in {"reports", "general", "categories", "currencies"}
            and self._account_service is not None
        ):
            accounts = await self._account_service.get_all(
                GetAllAccountsCommand(include_inactive=True)
            )
            parts.append(
                "АКТУАЛЬНЫЕ СЧЕТА: "
                + json.dumps(
                    [
                        account.model_dump(
                            mode="json",
                            include={
                                "id",
                                "name",
                                "currency_code",
                                "is_active",
                                "is_default",
                                "account_type",
                                "credit_limit",
                            },
                        )
                        for account in accounts
                    ],
                    ensure_ascii=False,
                )
            )
        if scenario == "search":
            parts.append(self._transaction_context())
        if scenario == "accounts":
            parts.append(
                f"PENDING_ACCOUNT_ASSIGNMENT: {self._transactions.pending_account_id}"
            )
        if scenario == "transfers":
            parts.append(
                "ПОКАЗАННЫЕ ПЕРЕВОДЫ: "
                + json.dumps(
                    [
                        self._format_transfer(item)
                        for item in self._transactions.transfers.values()
                    ],
                    ensure_ascii=False,
                )
            )
            state = self._transactions
            for label, value in (
                ("ПОСЛЕДНЯЯ СТРАНИЦА ПЕРЕВОДОВ", state.transfer_filters),
                ("ПОСЛЕДНЯЯ СТРАНИЦА КОРРЕКТИРОВОК", state.adjustment_filters),
                (
                    "УДАЛЕНИЕ ПЕРЕВОДА ОЖИДАЕТ ПОДТВЕРЖДЕНИЯ",
                    state.pending_transfer_delete,
                ),
                ("ПОСЛЕДНЯЯ СВЕРКА", state.reconciliation),
                ("КОРРЕКТИРОВКА ОЖИДАЕТ ПОДТВЕРЖДЕНИЯ", state.pending_adjustment),
                ("ОТМЕНА КОРРЕКТИРОВКИ ОЖИДАЕТ ПОДТВЕРЖДЕНИЯ", state.pending_reversal),
            ):
                parts.append(
                    label
                    + ": "
                    + (value.model_dump_json() if value is not None else "нет")
                )
        if scenario == "debts" and self._debt_service is not None:
            debts = await self._debt_service.get_all(
                GetAllDebtsCommand(include_repaid=True)
            )
            parts.append(
                "АКТУАЛЬНЫЕ ДОЛГИ: "
                + json.dumps(
                    [
                        debt.model_dump(
                            mode="json", exclude={"created_at", "updated_at"}
                        )
                        for debt in debts
                    ],
                    ensure_ascii=False,
                )
            )
            pending = self._transactions.pending_debt_delete
            parts.append(
                "PENDING_DEBT_DELETION: "
                + (pending.model_dump_json() if pending else "нет")
            )
        if (
            scenario == "transactions"
            and self._transactions.pending_debt_income is not None
        ):
            parts.append(
                "PENDING_DEBT_INCOME: "
                + self._transactions.pending_debt_income.model_dump_json()
            )
        if scenario == "goals" and self._savings_goal_service is not None:
            goals = await self._savings_goal_service.get_all(
                GetAllSavingsGoalsCommand()
            )
            parts.append(
                "АКТУАЛЬНЫЕ ЦЕЛИ: "
                + json.dumps(
                    [
                        goal.model_dump(
                            mode="json", exclude={"history", "created_at", "updated_at"}
                        )
                        for goal in goals
                    ],
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
        if scenario == "reports" and self._dialog.last_report is not None:
            parts.append(
                "ПОСЛЕДНИЙ ОТЧЁТ: " + self._dialog.last_report.model_dump_json()
            )
        if scenario == "screenshots":
            parts.append(
                "ЧЕРНОВИКИ ОПЕРАЦИЙ СО СКРИНШОТОВ: "
                + json.dumps(
                    [
                        draft.model_dump(mode="json")
                        for draft in self._screenshots.drafts
                    ],
                    ensure_ascii=False,
                )
            )
            parts.append(f"Список готов: {self._screenshots.ready}")
            if self._screenshots.ready:
                parts.append("Сейчас ожидается его подтверждение или исправления")
        return "\n" + "\n".join(parts)

    async def handle_message(self, user_message: str) -> str:
        self._last_response = None
        self._command_failed = False
        self._clarification_pending = False
        self._handling_message = True
        token = request_context.set(next(_request_numbers))
        try:
            try:
                answer = await self._handle_message(user_message)
            except (ServiceError, SQLAlchemyError, ValidationError, RequestException):
                self._command_failed = True
                self._remember_result(
                    user_message,
                    "Действие не завершено; перед повтором проверьте актуальные данные.",
                )
                self._invalidate_confirmation()
                raise
            self._remember_result(user_message, answer)
            return answer
        finally:
            self._handling_message = False
            request_context.reset(token)

    def _remember_result(self, user_message: str, answer: str) -> None:
        dialog = self._dialog
        response = self._last_response
        outcome = {
            "command": response.model_dump(mode="json") if response else None,
            "status": "failed" if self._command_failed else "handled",
            "result": answer[:1600]
            + ("… [результат сокращён]" if len(answer) > 1600 else ""),
        }
        if self._memory is not None:
            self._memory.add(
                user_message,
                json.dumps(outcome, ensure_ascii=False),
                scenario=dialog.active_scenario,
            )
        if dialog.active_scenario is not None:
            task = dialog.tasks.setdefault(
                dialog.active_scenario, TaskState(started_turn=request_context.get())
            )
            task.result = str(outcome["result"])
            task.awaiting_answer = self._clarification_pending
            if response is not None and not isinstance(
                response, (ClarifyResponse, TextResponse)
            ):
                task.last_command = response
                task.command_result = str(outcome["result"])
                task.command_status = "failed" if self._command_failed else "handled"
            logger.info(
                "AI conversation turn=%s scenario=%s status=%s",
                request_context.get(),
                dialog.active_scenario,
                outcome["status"],
            )
            if isinstance(response, ClarifyResponse):
                task.question = response.message
        candidates = self._confirmation_candidates()
        dialog.confirmation = (
            next(iter(candidates.items())) if len(candidates) == 1 else None
        )

    async def _handle_message(
        self,
        user_message: str,
    ) -> str:
        self.report_images = []
        screenshot_text = user_message.strip().casefold().rstrip(".!?")
        if screenshot_text in {
            "сохранить операции",
            "отмена скриншотов",
            "продолжить скриншоты",
        }:
            self._transactions.clear()
            if screenshot_text == "сохранить операции":
                return await self._confirm_screenshots(user_message)
            if screenshot_text == "отмена скриншотов":
                self._screenshots.clear()
                return "↩️ Несохранённые операции со скриншотов отменены."
            return await self._preview_screenshots(user_message)
        response = await self.interpret(user_message)
        self._last_response = response
        if isinstance(response, ConfirmScreenshotTransactionsResponse):
            self._transactions.clear()
            if response.confirmed:
                return await self._confirm_screenshots(user_message)
            self._screenshots.clear()
            return "↩️ Несохранённые операции со скриншотов отменены."
        if not isinstance(
            response,
            (
                UpdateScreenshotTransactionResponse,
                SkipScreenshotTransactionResponse,
                ClarifyResponse,
                TextResponse,
            ),
        ):
            self._screenshots.ready = False
        if not isinstance(
            response,
            (CreateTransactionResponse, CreateCategoryResponse, ClarifyResponse),
        ):
            self._transactions.pending_debt_income = None
        if self._screenshots.drafts and isinstance(response, CreateTransactionResponse):
            return "Операции со скриншотов ещё не сохранены. Напишите «продолжить скриншоты», проверьте список и подтвердите его."
        if isinstance(
            response,
            (UpdateScreenshotTransactionResponse, SkipScreenshotTransactionResponse),
        ):
            self._transactions.clear()
            index = response.selection - 1
            if index >= len(self._screenshots.drafts):
                return "Такой строки в черновике нет. Напишите «продолжить скриншоты»."
            if isinstance(response, SkipScreenshotTransactionResponse):
                self._screenshots.drafts.pop(index)
            else:
                self._screenshots.drafts[index] = (
                    ScreenshotTransactionDraft.model_validate(
                        self._screenshots.drafts[index].model_dump()
                        | response.changes.model_dump(exclude_unset=True)
                    )
                )
            return await self._preview_screenshots(user_message)

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

        if not isinstance(
            response,
            (
                DeleteTransferTransactionResponse,
                ConfirmDeleteTransferTransactionResponse,
                ClarifyResponse,
            ),
        ):
            self._transactions.pending_transfer_delete = None
        if not isinstance(
            response,
            (
                ReverseBalanceAdjustmentResponse,
                ConfirmReverseBalanceAdjustmentResponse,
                ClarifyResponse,
            ),
        ):
            self._transactions.pending_reversal = None
        if not isinstance(
            response,
            (
                CreateBalanceAdjustmentResponse,
                ConfirmBalanceAdjustmentResponse,
                ClarifyResponse,
            ),
        ):
            self._transactions.pending_adjustment = None
        if not isinstance(
            response,
            (
                ReconcileAccountResponse,
                CreateBalanceAdjustmentResponse,
                ConfirmBalanceAdjustmentResponse,
                ClarifyResponse,
            ),
        ):
            self._transactions.reconciliation = None

        if isinstance(
            response,
            (
                CreateTransferTransactionResponse,
                GetTransferTransactionsResponse,
                GetTransferTransactionResponse,
                UpdateTransferTransactionResponse,
                DeleteTransferTransactionResponse,
                ConfirmDeleteTransferTransactionResponse,
            ),
        ):
            self._transactions.pending_changes = None
            try:
                answer = await self._handle_transfer(response)
            except ServiceError as error:
                self._command_failed = True
                answer = f"⚠️ {error}"
        elif isinstance(
            response,
            (
                ReconcileAccountResponse,
                CreateBalanceAdjustmentResponse,
                ConfirmBalanceAdjustmentResponse,
                GetBalanceAdjustmentsResponse,
                GetBalanceAdjustmentResponse,
                ReverseBalanceAdjustmentResponse,
                ConfirmReverseBalanceAdjustmentResponse,
            ),
        ):
            self._transactions.pending_changes = None
            try:
                answer = await self._handle_adjustment(response)
            except ServiceError as error:
                self._command_failed = True
                answer = f"⚠️ {error}"
        elif isinstance(
            response,
            (
                CreateSavingsGoalResponse,
                GetSavingsGoalsResponse,
                GetSavingsGoalResponse,
                UpdateSavingsGoalResponse,
                AllocateSavingsGoalResponse,
                ReleaseSavingsGoalResponse,
            ),
        ):
            self._transactions.pending_changes = None
            try:
                answer = await self._handle_savings_goal(response)
            except ServiceError as error:
                self._command_failed = True
                answer = f"⚠️ {error}"
        elif isinstance(response, GetReportResponse):
            self._invalidate_confirmation()
            if self._report_service is None:
                raise ServiceError("Отчёты недоступны в этом подключении.")
            report = await self._report_service.get(response.arguments)
            self._dialog.last_report = GetReportCommand(
                date_from=report.date_from,
                date_to=report.date_to,
                format=response.arguments.format,
            )
            answer = ReportService.format_text(report)
            if response.arguments.format == "image":
                try:
                    self.report_images = await asyncio.to_thread(
                        ReportImageService.render, report
                    )
                    answer = (
                        f"Отчёт · {report.date_from:%d.%m.%Y} — "
                        f"{report.date_to:%d.%m.%Y}. "
                        "Валюты показаны раздельно, остатки по счетам — текущие."
                        + "\n"
                        + ReportService.format_adjustment_links(report)
                    )
                except ServiceError as error:
                    answer += f"\n\n{error}"
        elif isinstance(
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
                self._command_failed = True
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
                self._command_failed = True
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
                self._command_failed = True
                answer = f"⚠️ {error}"
        elif isinstance(response, (ClarifyResponse, TextResponse)):
            if isinstance(response, TextResponse):
                self._transactions.pending_changes = None
            answer = response.message
        else:
            raise TypeError(f"Unsupported AI response: {type(response).__name__}")

        return answer

    @staticmethod
    def _format_history_warnings(warnings: list[AccountHistoryWarning]) -> str:
        if not warnings:
            return ""
        lines = ["\n⚠️ Возможно пересечение с ранее принятой корректировкой:"]
        lines.extend(
            f"• Счёт «{item.account_name}»: корректировка № {item.adjustment_id}, {item.amount:+.2f} {item.currency_code}, "
            f"{item.occurred_at.astimezone(settings.timezone_info):%d.%m.%Y %H:%M:%S %z}, остаётся в расчёте."
            for item in warnings
        )
        lines.append(
            "Совпадение сумм не доказывает причину расхождения. Можно просмотреть корректировку, отменить её с подтверждением либо выполнить новую сверку. Старый фактический остаток не является актуальным."
        )
        return "\n".join(lines)

    @staticmethod
    def _format_balance_change(change: AccountBalanceChangeResult) -> str:
        return (
            f"«{change.account.name}»{' [неактивен]' if not change.account.is_active else ''}: "
            f"{change.account.balance:.2f} → {change.resulting_balance:.2f} {change.account.currency_code} "
            f"(изменение {change.amount:+.2f})."
        )

    @classmethod
    def _transfer_deletion_confirmation(
        cls, proposal: TransferTransactionDeletionResult
    ) -> str:
        return (
            cls._format_transfer(proposal.transfer)
            + "\n"
            + "\n".join(
                cls._format_balance_change(item) for item in proposal.balance_changes
            )
            + cls._format_history_warnings(proposal.history_warnings)
            + (
                "\nУдалить перевод? Удаляется только запись BudgetFlow, банковский перевод не отменяется. "
                "Отдельная комиссия остаётся: при необходимости удалите её как расход. "
                "Подтвердите удаление обычным сообщением или откажитесь."
            )
        )

    @staticmethod
    def _format_transfer(transfer: TransferTransactionResult) -> str:
        local = transfer.occurred_at.astimezone(settings.timezone_info)
        return (
            f"Перевод № {transfer.id}: «{transfer.source_account.name}» → "
            f"«{transfer.destination_account.name}» — {transfer.amount:.2f} "
            f"{transfer.currency_code}, {local:%d.%m.%Y %H:%M:%S %z}"
        )

    async def _handle_transfer(
        self,
        response: CreateTransferTransactionResponse
        | GetTransferTransactionsResponse
        | GetTransferTransactionResponse
        | UpdateTransferTransactionResponse
        | DeleteTransferTransactionResponse
        | ConfirmDeleteTransferTransactionResponse,
    ) -> str:
        service = self._transfer_service
        if service is None:
            raise ServiceError("Переводы недоступны в этом подключении.")
        if isinstance(response, CreateTransferTransactionResponse):
            transfer = await service.create(response.arguments)
            self._transactions.transfers[transfer.id] = transfer
            return (
                "✅ Записан совершённый перевод. "
                + self._format_transfer(transfer)
                + self._format_history_warnings(transfer.history_warnings)
            )
        if isinstance(response, GetTransferTransactionsResponse):
            transfers = await service.get_all(response.arguments)
            self._transactions.transfer_filters = response.arguments
            self._transactions.transfers = {item.id: item for item in transfers}
            if not transfers:
                return "Переводы по указанным условиям не найдены."
            return "\n".join(self._format_transfer(item) for item in transfers) + (
                "\nДля следующей страницы скажите «покажи ещё переводы»."
                if len(transfers) == response.arguments.limit
                else ""
            )
        if isinstance(response, GetTransferTransactionResponse):
            transfer = await service.get_by_id(response.arguments)
            self._transactions.transfers[transfer.id] = transfer
            return self._format_transfer(transfer)
        if isinstance(response, UpdateTransferTransactionResponse):
            current = self._transactions.transfers.get(response.id)
            if current is None:
                current = await service.get_by_id(
                    GetTransferTransactionByIdCommand(id=response.id)
                )
                self._transactions.transfers[current.id] = current
                return (
                    self._format_transfer(current)
                    + "\nПроверьте выбранный перевод и повторите нужное изменение."
                )
            updated = await service.update(
                UpdateTransferTransactionCommand(
                    id=current.id, changes=response.changes, expected=current
                )
            )
            self._transactions.transfers[updated.id] = updated
            return (
                "✏️ Перевод изменён.\nБыло: "
                + self._format_transfer(current)
                + "\nСтало: "
                + self._format_transfer(updated)
                + self._format_history_warnings(updated.history_warnings)
            )
        if isinstance(response, DeleteTransferTransactionResponse):
            self._transactions.pending_transfer_delete = None
            target = response.arguments
            if response.filters is not None:
                filters = response.filters.model_copy(update={"offset": 0, "limit": 10})
                candidates = await service.get_all(filters)
                self._transactions.transfer_filters = filters
                self._transactions.transfers = {item.id: item for item in candidates}
                if not candidates:
                    return "Переводы по указанным условиям не найдены."
                if len(candidates) != 1:
                    return (
                        "\n".join(self._format_transfer(item) for item in candidates)
                        + "\nКакой перевод удалить? Укажите номер. Для продолжения списка скажите «ещё переводы»."
                    )
                target = GetTransferTransactionByIdCommand(id=candidates[0].id)
            if target is None:
                raise ServiceError("Укажите перевод для удаления.")
            proposal = await service.prepare_delete(target)
            self._transactions.pending_transfer_delete = proposal
            return self._transfer_deletion_confirmation(proposal)
        deletion = self._transactions.pending_transfer_delete
        self._transactions.pending_transfer_delete = None
        if not response.confirmed:
            return "Удаление перевода отменено."
        if deletion is None:
            return "Нет перевода, ожидающего подтверждения удаления."
        try:
            warnings = await service.delete(
                DeleteTransferTransactionCommand(
                    id=deletion.transfer.id, expected=deletion
                )
            )
        except TransferTransactionDeletionChangedError as error:
            self._transactions.pending_transfer_delete = error.proposal
            return (
                "Перевод или показанное влияние изменились. Ничего не удалено.\n"
                + self._transfer_deletion_confirmation(error.proposal)
            )
        self._transactions.transfers.clear()
        return (
            "🗑️ Удалён "
            + self._format_transfer(deletion.transfer)
            + self._format_history_warnings(warnings)
            + "\nОтдельная комиссия не удалена."
        )

    @staticmethod
    def _format_reconciliation(result: AccountReconciliationResult) -> str:
        local = result.reconciled_at.astimezone(settings.timezone_info)
        return (
            f"Счёт «{result.account.name}» ({result.account.currency_code})\n"
            f"По учёту: {result.calculated_balance:.2f}\n"
            f"Фактически: {result.actual_balance:.2f}\n"
            f"Расхождение: {result.amount:+.2f}\n"
            f"Сверка: {local:%d.%m.%Y %H:%M:%S %z}"
        )

    @classmethod
    def _adjustment_confirmation(
        cls, result: AccountReconciliationResult, description: str
    ) -> str:
        return cls._format_reconciliation(result) + (
            f"\nКорректировка изменит остаток на {result.amount:+.2f} "
            f"до {result.actual_balance:.2f} {result.account.currency_code}. "
            "Начальный остаток, доходы и расходы сохранятся. "
            f"Пояснение: {description}\nЗапись будет видна в корректировках. "
            "Подтвердите применение обычным сообщением или откажитесь."
        )

    @staticmethod
    def _format_adjustment(result: BalanceAdjustmentResult) -> str:
        local = result.occurred_at.astimezone(settings.timezone_info)
        if result.reversal_of_id is not None:
            return (
                f"Отмена № {result.id} корректировки № {result.reversal_of_id}: «{result.account.name}», "
                f"{result.amount:+.2f} {result.currency_code}, {local:%d.%m.%Y %H:%M:%S %z}\n"
                f"Расчётный баланс при отмене: {result.calculated_balance:.2f} → {result.calculated_balance + result.amount:.2f}. "
                f"Пояснение: {result.description}"
            )
        if result.reconciled_at is None or result.actual_balance is None:
            raise ServiceError("В корректировке отсутствуют данные сверки.")
        reconciled = result.reconciled_at.astimezone(settings.timezone_info)
        return (
            f"Корректировка № {result.id}: «{result.account.name}», "
            f"{result.amount:+.2f} {result.currency_code}, {local:%d.%m.%Y %H:%M:%S %z}\n"
            f"По учёту: {result.calculated_balance:.2f}; фактически: {result.actual_balance:.2f}.\n"
            f"Сверка: {reconciled:%d.%m.%Y %H:%M:%S %z}. {result.description}"
            + (
                f"\nОтменена записью № {result.reversed_by_id}."
                if result.reversed_by_id is not None
                else ""
            )
        )

    @classmethod
    def _reversal_confirmation(cls, proposal: BalanceAdjustmentReversalResult) -> str:
        return (
            cls._format_adjustment(proposal.original)
            + "\n"
            + cls._format_balance_change(proposal.balance_change)
            + (
                f"\nПояснение отмены: {proposal.description}\n"
                "Будет добавлена обратная запись. Последующие операции сохранятся; начальный остаток, доходы и расходы не изменятся. "
                "Подтвердите отмену корректировки обычным сообщением или откажитесь."
            )
        )

    async def _handle_adjustment_reversal(
        self,
        response: ReverseBalanceAdjustmentResponse
        | ConfirmReverseBalanceAdjustmentResponse,
    ) -> str:
        service = self._adjustment_service
        if service is None:
            raise ServiceError("Корректировки недоступны в этом подключении.")
        if isinstance(response, ReverseBalanceAdjustmentResponse):
            self._transactions.pending_reversal = None
            prepared = await service.prepare_reverse(response.arguments)
            self._transactions.pending_reversal = prepared
            return self._reversal_confirmation(prepared)
        proposal = self._transactions.pending_reversal
        self._transactions.pending_reversal = None
        if not response.confirmed:
            return "Отмена корректировки не применена."
        if proposal is None:
            return "Нет отмены корректировки, ожидающей подтверждения."
        try:
            result = await service.reverse(
                ReverseBalanceAdjustmentCommand(
                    id=proposal.original.id, expected=proposal
                )
            )
        except BalanceAdjustmentReversalChangedError as error:
            self._transactions.pending_reversal = error.proposal
            return (
                "Состояние изменилось. Ничего не записано.\n"
                + self._reversal_confirmation(error.proposal)
            )
        except ServiceError:
            self._transactions.pending_reversal = proposal
            raise
        return "✅ " + self._format_adjustment(result)

    async def _handle_adjustment(
        self,
        response: ReconcileAccountResponse
        | CreateBalanceAdjustmentResponse
        | ConfirmBalanceAdjustmentResponse
        | GetBalanceAdjustmentsResponse
        | GetBalanceAdjustmentResponse
        | ReverseBalanceAdjustmentResponse
        | ConfirmReverseBalanceAdjustmentResponse,
    ) -> str:
        service = self._adjustment_service
        if service is None:
            raise ServiceError("Сверка остатков недоступна в этом подключении.")
        if isinstance(
            response,
            (ReverseBalanceAdjustmentResponse, ConfirmReverseBalanceAdjustmentResponse),
        ):
            return await self._handle_adjustment_reversal(response)
        if isinstance(response, ReconcileAccountResponse):
            self._transactions.reconciliation = None
            result = await service.reconcile(response.arguments)
            self._transactions.reconciliation = result
            return self._format_reconciliation(result) + (
                "\nОстатки совпадают. Корректировка не нужна."
                if result.amount == 0
                else "\nНичего не записано. Можно внести пропущенную операцию или исправить ошибочную. "
                "Чтобы принять фактический остаток без выяснения причины, скажите «прими остаток»; потребуется подтверждение корректировки."
            )
        if isinstance(response, CreateBalanceAdjustmentResponse):
            previous = self._transactions.reconciliation
            pending = self._transactions.pending_adjustment
            description = (
                pending.description
                if pending is not None
                and "description" not in response.model_fields_set
                else response.description
            )
            self._transactions.pending_adjustment = None
            if previous is None:
                return "Сначала укажите счёт и фактический остаток для сверки."
            result = await service.reconcile(
                ReconcileAccountCommand(
                    account_id=previous.account.id,
                    actual_balance=previous.actual_balance,
                    currency_code=previous.account.currency_code,
                )
            )
            self._transactions.reconciliation = result
            if result.amount == 0:
                return (
                    self._format_reconciliation(result)
                    + "\nОстатки совпадают. Корректировка не нужна."
                )
            self._transactions.pending_adjustment = CreateBalanceAdjustmentCommand(
                expected=result,
                description=description,
            )
            return self._adjustment_confirmation(result, description)
        if isinstance(response, GetBalanceAdjustmentsResponse):
            adjustments = await service.get_all(response.arguments)
            self._transactions.adjustment_filters = response.arguments
            if not adjustments:
                return "Корректировки по указанным условиям не найдены."
            return "\n\n".join(
                self._format_adjustment(item) for item in adjustments
            ) + (
                "\nДля следующей страницы скажите «покажи ещё корректировки»."
                if len(adjustments) == response.arguments.limit
                else ""
            )
        if isinstance(response, GetBalanceAdjustmentResponse):
            return self._format_adjustment(await service.get_by_id(response.arguments))
        command = self._transactions.pending_adjustment
        self._transactions.pending_adjustment = None
        if not response.confirmed:
            self._transactions.reconciliation = None
            return "Корректировка отменена."
        if command is None:
            return (
                "Нет корректировки, ожидающей подтверждения. Сначала выполните сверку."
            )
        try:
            adjustment = await service.create(command)
        except AccountBalanceChangedError as error:
            result = error.reconciliation
            self._transactions.reconciliation = result
            if result.amount == 0:
                return (
                    self._format_reconciliation(result)
                    + "\nОстатки уже совпадают. Корректировка не создана."
                )
            self._transactions.pending_adjustment = CreateBalanceAdjustmentCommand(
                expected=result, description=command.description
            )
            return (
                "Остаток или параметры счёта изменились. Ничего не записано.\n"
                + self._adjustment_confirmation(result, command.description)
            )
        except ServiceError:
            self._transactions.pending_adjustment = command
            raise
        self._transactions.reconciliation = None
        if adjustment is None:
            return "Остатки совпадают. Корректировка не создана."
        return "✅ " + self._format_adjustment(adjustment)

    async def handle_attachments(
        self, documents: list[DocumentInput], user_message: str = ""
    ) -> str:
        token = request_context.set(next(_request_numbers))
        self._dialog.active_scenario = "screenshots"
        task = self._dialog.tasks.setdefault(
            "screenshots", TaskState(started_turn=request_context.get())
        )
        try:
            return await self._handle_attachments(documents, user_message)
        finally:
            logger.info(
                "AI task turn=%s task=%s scenario=screenshots status=recognition",
                request_context.get(),
                task.started_turn,
            )
            request_context.reset(token)

    async def _handle_attachments(
        self, documents: list[DocumentInput], user_message: str = ""
    ) -> str:
        self.report_images = []
        self._invalidate_confirmation()
        self._transactions.clear()
        if (
            not documents
            or len(documents) > 10
            or sum(len(item.data) for item in documents) > DocumentService.MAX_BYTES
        ):
            raise ServiceError("Пришлите от 1 до 10 вложений общим размером до 20 МБ.")
        pages: list[DocumentPage] = []
        for document in documents:
            prepared = await asyncio.to_thread(DocumentService.prepare, document)
            pages.append(prepared[0])
        if self._screenshots.drafts:
            return "Сначала завершите текущий импорт или напишите «отмена скриншотов», затем пришлите новые изображения."
        categories = await self._category_service.get_all(GetAllCategoriesCommand())
        accounts = (
            await self._account_service.get_all(GetAllAccountsCommand())
            if self._account_service is not None
            else []
        )
        context = (
            f"\nЧасовой пояс: {settings.timezone}. "
            f"Текущая дата: {datetime.now(settings.timezone_info):%Y-%m-%d}.\n"
            + "Категории: "
            + json.dumps(
                [item.model_dump(mode="json") for item in categories],
                ensure_ascii=False,
            )
            + "\nСчета: "
            + json.dumps(
                [
                    {
                        "id": item.id,
                        "name": item.name,
                        "currency_code": item.currency_code,
                        "is_default": item.is_default,
                    }
                    for item in accounts
                ],
                ensure_ascii=False,
            )
            + "\nПодпись пользователя: "
            + user_message
        )
        drafts: list[ScreenshotTransactionDraft] = []
        warnings: list[str] = []
        fingerprints: set[str] = set()
        kinds: set[str] = set()
        for document, page in zip(documents, pages, strict=True):
            fingerprint = sha256(document.data).hexdigest()
            if (
                fingerprint in self._screenshots.processed
                or fingerprint in fingerprints
            ):
                warnings.append(
                    "Повторное изображение пропущено: оно уже обработано в этой сессии."
                )
                continue
            result = await asyncio.to_thread(
                self._client.extract_screenshot, page, context
            )
            kinds.add(result.kind)
            drafts.extend(result.transactions)
            warnings.extend(result.warnings)
            fingerprints.add(fingerprint)
        if not fingerprints:
            return "\n".join(warnings)
        if kinds != {"transactions"}:
            return (
                "\n".join(warnings)
                + "\nНе удалось однозначно выделить операции. Пришлите скриншот чека или истории операций."
            )
        if not drafts or len(drafts) > 20:
            return "Нужно от 1 до 20 операций. Пришлите более чёткие скриншоты или разделите список."
        self._screenshots.drafts = drafts
        self._screenshots.warnings = warnings
        self._screenshots.fingerprints = fingerprints
        return await self._preview_screenshots(user_message)

    async def _preview_screenshots(self, user_message: str) -> str:
        state = self._screenshots
        state.ready = False
        if not state.drafts:
            state.clear()
            return "Нет операций со скриншотов для сохранения."
        accounts = (
            await self._account_service.get_all(GetAllAccountsCommand())
            if self._account_service is not None
            else []
        )
        categories = await self._category_service.get_all(GetAllCategoriesCommand())
        account_names = {item.id: item.name for item in accounts}
        category_names = {item.id: item.name for item in categories}
        default_account = next((item for item in accounts if item.is_default), None)
        problems: list[str] = []
        lines = ["Проверьте операции со скриншотов:"]
        for index, draft in enumerate(state.drafts, 1):
            if draft.account_id is None and default_account is not None:
                draft.account_id = default_account.id
            direction = {
                "expense": "Расход",
                "income": "Доход",
                "transfer": "Перевод",
            }.get(draft.direction or "", "направление не указано")
            when = (
                draft.occurred_at.astimezone(settings.timezone_info).strftime(
                    "%d.%m.%Y %H:%M"
                )
                if draft.occurred_at is not None
                else "дата и время не указаны"
            )
            lines.append(
                f"{index}. {direction} · {draft.name or 'название не указано'} · {draft.amount if draft.amount is not None else '?'} {draft.currency_code or '?'} · {when} · счёт: {account_names.get(draft.account_id or 0, 'не выбран')} · категория: {category_names.get(draft.category_id or 0, 'не выбрана')}"
            )
            missing = [
                label
                for field, label in (
                    ("name", "название"),
                    ("amount", "сумму"),
                    ("currency_code", "валюту"),
                    ("occurred_at", "дату и время"),
                    ("direction", "направление"),
                )
                if getattr(draft, field) is None
            ]
            if draft.account_id not in account_names:
                missing.append("активный счёт")
            elif any(
                item.id == draft.account_id
                and draft.currency_code is not None
                and item.currency_code != draft.currency_code
                for item in accounts
            ):
                missing.append("счёт в валюте операции")
            if draft.category_id not in category_names:
                missing.append("категорию")
            if missing:
                problems.append(f"Для строки {index} уточните: {', '.join(missing)}.")
            if draft.direction == "transfer":
                problems.append(
                    f"Строка {index} — перевод между своими счетами. Исключите её: учёт переводов пока не поддерживается."
                )
            if draft.status != "completed":
                problems.append(
                    f"Для строки {index} уточните, выполнена ли операция, или исключите её из импорта."
                )
            if draft.occurred_at is not None:
                try:
                    resolve_occurred_at(draft.occurred_at)
                except ServiceError:
                    problems.append(
                        f"Для строки {index} укажите дату операции, которая уже произошла."
                    )
        lines.extend(f"⚠️ {warning}" for warning in state.warnings)
        if problems:
            lines.extend(problems)
            lines.append(
                "Укажите исправления с номером строки или напишите «отмена скриншотов»."
            )
        else:
            state.ready = True
            lines.append(
                "Добавить эти операции? Подтвердите обычным сообщением "
                "(например, «да» или «сохранить операции»), укажите исправления или отмените импорт."
            )
        answer = "\n".join(lines)
        self._dialog.active_scenario = "screenshots"
        candidates = self._confirmation_candidates()
        self._dialog.confirmation = (
            next(iter(candidates.items())) if len(candidates) == 1 else None
        )
        if self._memory is not None and not self._handling_message:
            self._memory.add(
                user_message or "[Присланы скриншоты операций]",
                ClarifyResponse(action="clarify", message=answer).model_dump_json(),
                scenario="screenshots",
            )
        return answer

    async def _confirm_screenshots(self, user_message: str) -> str:
        state = self._screenshots
        candidates = self._confirmation_candidates()
        if (
            not state.ready
            or not state.drafts
            or len(candidates) != 1
            or self._dialog.confirmation
            != (
                "confirm_screenshot_transactions",
                candidates.get("confirm_screenshot_transactions"),
            )
        ):
            state.ready = False
            return "Сначала проверьте готовый список: напишите «продолжить скриншоты»."
        state.ready = False
        messages: list[str] = []
        while state.drafts:
            draft = state.drafts[0]
            arguments = draft.model_dump(exclude={"direction", "status"})
            try:
                if draft.direction == "expense":
                    saved: TransactionResult = await self._expense_service.create(
                        CreateExpenseTransactionCommand.model_validate(arguments)
                    )
                else:
                    saved = await self._incoming_service.create(
                        CreateIncomingTransactionCommand.model_validate(arguments)
                    )
            except (ServiceError, SQLAlchemyError, ValidationError):
                self._command_failed = True
                return (
                    "\n".join(messages)
                    + f"\n⚠️ Осталось несохранённых операций: {len(state.drafts)}. Проверьте счёт, категорию и валюту: «продолжить скриншоты». Уже добавленные строки повторно не сохранятся."
                )
            state.drafts.pop(0)
            state.processed.update(state.fingerprints)
            self._transactions.results.append(saved)
            self._transactions.shown_count += 1
            messages.append("✅ Добавлено: " + self._format_transaction(saved))
            messages.append(await self._format_transaction_balance(saved))
            if saved.history_warnings:
                messages.append(self._format_history_warnings(saved.history_warnings))
        state.clear()
        answer = "\n".join(messages)
        if self._memory is not None and not self._handling_message:
            self._memory.add(
                user_message,
                TextResponse(action="respond", message=answer).model_dump_json(),
            )
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

    @staticmethod
    def _format_savings_goal(goal: SavingsGoalResult, *, history: bool = False) -> str:
        progress = goal.progress_percent.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        statuses = {
            SavingsGoalStatus.ACTIVE: "Активна",
            SavingsGoalStatus.PAUSED: "Приостановлена",
            SavingsGoalStatus.ACHIEVED: "Достигнута по выделениям",
        }
        lines = [
            f"🎯 {goal.name} · №{goal.id} · {statuses[goal.status]}",
            f"Цель: {goal.target_amount:.2f} {goal.currency_code}",
            (
                f"Выделено: {goal.allocated_amount:.2f} {goal.currency_code} "
                f"({progress:.2f}%)"
            ),
            f"Осталось: {goal.remaining_amount:.2f} {goal.currency_code}",
            f"Приоритет: {goal.priority}/5",
            f"Срок: {goal.due_date:%d.%m.%Y}" if goal.due_date else "Срок не задан",
        ]
        if goal.is_overdue:
            lines.append("⏰ Срок достижения истёк")
        for account in goal.accounts:
            lines.append(
                f"Счёт «{account.account_name}» · №{account.account_id}: "
                f"выделено {account.allocated_amount:.2f} {goal.currency_code}; "
                f"баланс {account.balance:.2f}; всего выделено {account.total_allocated_amount:.2f}; "
                f"доступно {account.available_amount:.2f}"
                + (" · деактивирован" if not account.is_active else "")
            )
            if account.shortfall_amount > 0:
                lines.append(
                    f"⚠️ Нехватка покрытия всех выделений счёта: "
                    f"{account.shortfall_amount:.2f} {goal.currency_code}. "
                    "Обеспеченность этой цели не гарантирована. Пересмотрите выделения."
                )
        if history:
            lines.append("История выделений и освобождений:")
            if not goal.history:
                lines.append("Записей нет.")
            for item in goal.history:
                timestamp = item.created_at.astimezone(settings.timezone_info)
                lines.append(
                    f"№{item.id} · {timestamp:%d.%m.%Y %H:%M:%S} · "
                    f"{item.account_name} (счёт №{item.account_id}): "
                    f"{item.amount:+.2f} {goal.currency_code}"
                )
        return "\n".join(lines)

    async def _handle_savings_goal(
        self,
        response: CreateSavingsGoalResponse
        | GetSavingsGoalsResponse
        | GetSavingsGoalResponse
        | UpdateSavingsGoalResponse
        | AllocateSavingsGoalResponse
        | ReleaseSavingsGoalResponse,
    ) -> str:
        service = self._savings_goal_service
        if service is None:
            return "⚠️ Цели накопления недоступны."
        if isinstance(response, GetSavingsGoalsResponse):
            goals = await service.get_all(response.arguments)
            return (
                "\n\n".join(self._format_savings_goal(goal) for goal in goals)
                or "Целей пока нет."
            )
        if isinstance(response, GetSavingsGoalResponse):
            return self._format_savings_goal(
                await service.get_by_id(response.arguments), history=True
            )
        if isinstance(response, CreateSavingsGoalResponse):
            goal = await service.create(response.arguments)
            message = "✅ Цель создана."
        elif isinstance(response, UpdateSavingsGoalResponse):
            goal = await service.update(response.arguments)
            message = "✏️ Цель обновлена."
        elif isinstance(response, AllocateSavingsGoalResponse):
            goal = await service.allocate(response.arguments)
            message = "✅ Деньги выделены на цель. Баланс счёта не изменён."
        else:
            goal = await service.release(response.arguments)
            message = "✅ Деньги освобождены. Баланс счёта не изменён."
        return message + "\n" + self._format_savings_goal(goal)

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
                "Баланс счёта не изменится.\nПодтвердите удаление обычным сообщением или откажитесь."
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
            debt = await service.create(response.arguments)
            answer = "✅ Долг добавлен.\n" + self._format_debt(debt)
            if debt.direction == DebtDirection.PAYABLE and debt.amount > 0:
                self._transactions.pending_debt_income = debt
                answer += (
                    f"\n\nДобавить получение {debt.amount:.2f} {debt.currency_code} "
                    "отдельной доходной транзакцией в категорию «Взял в долг» "
                    "на счёт по умолчанию? Можно выбрать другой счёт, категорию, "
                    "уточнить сумму и дату или отказаться. "
                    "Если деньги уже учтены в балансе, повторно добавлять их не нужно."
                )
            return answer
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
                "\nПодтвердите привязку обычным сообщением или откажитесь."
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
                if expense.history_warnings:
                    messages.append(
                        self._format_history_warnings(expense.history_warnings)
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
                if income.history_warnings:
                    messages.append(
                        self._format_history_warnings(income.history_warnings)
                    )

            saved = self._transactions.results[-1]
            messages.append(await self._format_transaction_balance(saved))
            self._transactions.pending_debt_income = None

        task = self._dialog.tasks.get("transactions")
        if task is not None:
            task.draft = TaskDraft()
            task.question = ""
        return "\n".join(messages)

    async def _format_transaction_balance(self, transaction: TransactionResult) -> str:
        if transaction.account_id is None:
            return "Расчётный баланс недоступен: операция без счёта."
        if self._account_service is None:
            return "Расчётный баланс счёта недоступен."
        try:
            account = await self._account_service.get_by_id(
                GetAccountByIdCommand(id=transaction.account_id)
            )
        except (ServiceError, SQLAlchemyError):
            return "Операция сохранена, но получить текущий баланс счёта не удалось."
        return (
            f"Расчётный баланс сейчас · {account.name}: "
            f"{account.balance:.2f} {account.currency_code}."
        )

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
            "Восстановление не предусмотрено. Подтвердите удаление обычным сообщением или откажитесь."
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
            warnings = await self._expense_service.delete(
                DeleteExpenseTransactionCommand(id=current.id, expected=expected)
            )
        else:
            warnings = await self._incoming_service.delete(
                DeleteIncomingTransactionCommand(id=current.id, expected=expected)
            )
        self._transactions.clear()
        return (
            f"🗑️ Транзакция удалена: {self._format_transaction(current)}.\n"
            "Для дальнейшей работы со списком выполните поиск заново."
            + self._format_history_warnings(warnings)
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
            + self._format_history_warnings(updated.history_warnings)
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
