import asyncio
import json
from datetime import datetime
from decimal import Decimal
from hashlib import sha256

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from ai.client import AIClient
from ai.memory import ConversationMemory, ScreenshotState, TransactionState
from ai.models import (
    AIResponseType,
    AssignAccountTransactionsResponse,
    ClarifyResponse,
    ConfirmAssignAccountTransactionsResponse,
    ConfirmBalanceAdjustmentResponse,
    ConfirmDeleteDebtResponse,
    ConfirmDeleteTransactionResponse,
    ConfirmDeleteTransferTransactionResponse,
    CreateAccountResponse,
    CreateBalanceAdjustmentResponse,
    CreateCategoryResponse,
    CreateCurrencyResponse,
    CreateDebtResponse,
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
    GetTransferTransactionResponse,
    GetTransferTransactionsResponse,
    IncomingTransactionItem,
    MoreTransactionsResponse,
    ReconcileAccountResponse,
    SearchTransactionArguments,
    SearchTransactionsResponse,
    SelectTransactionResponse,
    SkipScreenshotTransactionResponse,
    TextResponse,
    UpdateAccountResponse,
    UpdateCategoryResponse,
    UpdateDebtResponse,
    UpdateScreenshotTransactionResponse,
    UpdateTransactionResponse,
    UpdateTransferTransactionResponse,
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
from schemas.balance_adjustment import (
    AccountReconciliationResult,
    BalanceAdjustmentResult,
    CreateBalanceAdjustmentCommand,
    ReconcileAccountCommand,
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
from schemas.transaction import TransactionSnapshot
from schemas.transfer_transaction import (
    DeleteTransferTransactionCommand,
    GetTransferTransactionByIdCommand,
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
    ServiceError,
)
from services.expense_transaction_service import ExpenseTransactionService
from services.incoming_transaction_service import IncomingTransactionService
from services.report_image_service import ReportImageService
from services.report_service import ReportService
from services.transaction_time import resolve_occurred_at
from services.transfer_transaction_service import TransferTransactionService
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
        report_service: ReportService | None = None,
        transfer_service: TransferTransactionService | None = None,
        adjustment_service: BalanceAdjustmentService | None = None,
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
        self.report_images: list[DocumentInput] = []
        self._screenshots = (
            memory.screenshots if memory is not None else ScreenshotState()
        )
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
        system_prompt += (
            "\nСоздание и ведение банковских кредитных обязательств, импорт договоров "
            "и графиков платежей отключены. На такие запросы объясни это через text; "
            "не заменяй банковскую карточку созданием долга или счёта. Реестр долгов "
            "перед людьми и явно запрошенные кредитные счета с лимитом доступны."
        )
        system_prompt += self._transaction_context()
        system_prompt += "\nПОКАЗАННЫЕ ПЕРЕВОДЫ: " + json.dumps(
            [
                self._format_transfer(item)
                for item in self._transactions.transfers.values()
            ],
            ensure_ascii=False,
        )
        pending_transfer = self._transactions.pending_transfer_delete
        transfer_filters = self._transactions.transfer_filters
        adjustment_filters = self._transactions.adjustment_filters
        system_prompt += "\nПОСЛЕДНЯЯ СТРАНИЦА ПЕРЕВОДОВ: " + (
            transfer_filters.model_dump_json()
            if transfer_filters is not None
            else "нет"
        )
        system_prompt += "\nПОСЛЕДНЯЯ СТРАНИЦА КОРРЕКТИРОВОК: " + (
            adjustment_filters.model_dump_json()
            if adjustment_filters is not None
            else "нет"
        )
        system_prompt += "\nУДАЛЕНИЕ ПЕРЕВОДА ОЖИДАЕТ ПОДТВЕРЖДЕНИЯ: " + (
            self._format_transfer(pending_transfer)
            if pending_transfer is not None
            else "нет"
        )
        reconciliation = self._transactions.reconciliation
        system_prompt += "\nПОСЛЕДНЯЯ СВЕРКА: " + (
            self._format_reconciliation(reconciliation)
            if reconciliation is not None
            else "нет"
        )
        pending_adjustment = self._transactions.pending_adjustment
        system_prompt += "\nКОРРЕКТИРОВКА ОЖИДАЕТ ПОДТВЕРЖДЕНИЯ: " + (
            self._format_reconciliation(pending_adjustment.expected)
            if pending_adjustment is not None
            else "нет"
        )
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

        if self._screenshots.drafts:
            system_prompt += (
                "\nЧЕРНОВИКИ ОПЕРАЦИЙ СО СКРИНШОТОВ (нумерация с 1): "
                + json.dumps(
                    [item.model_dump(mode="json") for item in self._screenshots.drafts],
                    ensure_ascii=False,
                )
                + "\nУточнения пользователя вноси только через "
                '{"action":"update_screenshot_transaction","selection":1,"changes":{...}}. '
                "changes содержит только явно изменённые поля. Для исключения строки: "
                '{"action":"skip_screenshot_transaction","selection":1}. '
                "После исключения нумерация меняется. Не вызывай create_transactions "
                "для этих черновиков. Сохранение выполняет приложение только по фразе "
                "«сохранить операции» после показа готового списка. "
                "«отмена скриншотов» отменяет импорт; «продолжить скриншоты» показывает список. "
                "Не выдумывай дату, время, направление или статус. Суммы в строках. "
                "Переводы между своими счетами не поддерживаются. Поля черновика: "
                + json.dumps(
                    ScreenshotTransactionDraft.model_json_schema(), ensure_ascii=False
                )
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
            if not self._screenshots.drafts:
                print(f"Некорректный ответ AI: {raw_response!r}", flush=True)
            else:
                print(
                    "Некорректный ответ AI; содержимое скриншотов не записано в лог.",
                    flush=True,
                )
            raise

    async def handle_message(
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
                return await self._confirm_screenshots()
            if screenshot_text == "отмена скриншотов":
                self._screenshots.clear()
                return "↩️ Несохранённые операции со скриншотов отменены."
            return await self._preview_screenshots()
        self._screenshots.ready = False
        response = await self.interpret(user_message)
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
            return await self._preview_screenshots()

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
                answer = f"⚠️ {error}"
        elif isinstance(
            response,
            (
                ReconcileAccountResponse,
                CreateBalanceAdjustmentResponse,
                ConfirmBalanceAdjustmentResponse,
                GetBalanceAdjustmentsResponse,
                GetBalanceAdjustmentResponse,
            ),
        ):
            self._transactions.pending_changes = None
            try:
                answer = await self._handle_adjustment(response)
            except ServiceError as error:
                answer = f"⚠️ {error}"
        elif isinstance(response, GetReportResponse):
            self._transactions.clear()
            if self._report_service is None:
                raise ServiceError("Отчёты недоступны в этом подключении.")
            report = await self._report_service.get(response.arguments)
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
            return "✅ Записан совершённый перевод. " + self._format_transfer(transfer)
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
            )
        if isinstance(response, DeleteTransferTransactionResponse):
            self._transactions.pending_transfer_delete = None
            transfer = await service.get_by_id(response.arguments)
            self._transactions.pending_transfer_delete = transfer
            return (
                self._format_transfer(transfer)
                + "\nУдалить перевод? Его влияние на оба счёта будет отменено с учётом их начальных остатков. Ответьте «да, удалить перевод» или «отмена»."
            )
        current = self._transactions.pending_transfer_delete
        self._transactions.pending_transfer_delete = None
        if not response.confirmed:
            return "Удаление перевода отменено."
        if current is None:
            return "Нет перевода, ожидающего подтверждения удаления."
        await service.delete(
            DeleteTransferTransactionCommand(id=current.id, expected=current)
        )
        self._transactions.transfers.clear()
        return "🗑️ Удалён " + self._format_transfer(current)

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
    def _adjustment_confirmation(cls, result: AccountReconciliationResult) -> str:
        return cls._format_reconciliation(result) + (
            f"\nКорректировка изменит остаток на {result.amount:+.2f} "
            f"до {result.actual_balance:.2f} {result.account.currency_code}. "
            "Начальный остаток, доходы и расходы сохранятся. "
            "Причина расхождения не установлена; запись будет видна в корректировках. "
            "Ответьте «да, применить корректировку» или «отмена»."
        )

    @staticmethod
    def _format_adjustment(result: BalanceAdjustmentResult) -> str:
        local = result.occurred_at.astimezone(settings.timezone_info)
        reconciled = result.reconciled_at.astimezone(settings.timezone_info)
        return (
            f"Корректировка № {result.id}: «{result.account.name}», "
            f"{result.amount:+.2f} {result.currency_code}, {local:%d.%m.%Y %H:%M:%S %z}\n"
            f"По учёту: {result.calculated_balance:.2f}; фактически: {result.actual_balance:.2f}.\n"
            f"Сверка: {reconciled:%d.%m.%Y %H:%M:%S %z}. {result.description}"
        )

    async def _handle_adjustment(
        self,
        response: ReconcileAccountResponse
        | CreateBalanceAdjustmentResponse
        | ConfirmBalanceAdjustmentResponse
        | GetBalanceAdjustmentsResponse
        | GetBalanceAdjustmentResponse,
    ) -> str:
        service = self._adjustment_service
        if service is None:
            raise ServiceError("Сверка остатков недоступна в этом подключении.")
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
                description="Принят фактический остаток, указанный пользователем. Причина расхождения не установлена.",
            )
            return self._adjustment_confirmation(result)
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
                + self._adjustment_confirmation(result)
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
        self.report_images = []
        self._screenshots.ready = False
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
        return await self._preview_screenshots()

    async def _preview_screenshots(self) -> str:
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
                "Напишите «сохранить операции», укажите исправления или «отмена скриншотов»."
            )
        return "\n".join(lines)

    async def _confirm_screenshots(self) -> str:
        state = self._screenshots
        if not state.ready or not state.drafts:
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
                return (
                    "\n".join(messages)
                    + f"\n⚠️ Осталось несохранённых операций: {len(state.drafts)}. Проверьте счёт, категорию и валюту: «продолжить скриншоты». Уже добавленные строки повторно не сохранятся."
                )
            state.drafts.pop(0)
            state.processed.update(state.fingerprints)
            self._transactions.results.append(saved)
            self._transactions.shown_count += 1
            messages.append("✅ Добавлено: " + self._format_transaction(saved))
        state.clear()
        return "\n".join(messages)

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
