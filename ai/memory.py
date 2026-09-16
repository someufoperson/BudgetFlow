from collections import deque
from dataclasses import dataclass, field
from typing import Literal

from schemas.balance_adjustment import (
    AccountReconciliationResult,
    BalanceAdjustmentReversalResult,
    CreateBalanceAdjustmentCommand,
    GetBalanceAdjustmentsCommand,
)
from schemas.debt import DebtResult
from schemas.document import ScreenshotTransactionDraft
from schemas.expense_transaction import ExpenseTransactionResult
from schemas.incoming_transaction import IncomingTransactionResult
from schemas.transaction import TransactionChanges
from schemas.transfer_transaction import (
    GetTransferTransactionsCommand,
    TransferTransactionDeletionResult,
    TransferTransactionResult,
)


@dataclass(slots=True)
class TransactionState:
    results: list[ExpenseTransactionResult | IncomingTransactionResult] = field(
        default_factory=list
    )
    shown_count: int = 0
    page_size: int = 10
    pending_changes: TransactionChanges | None = None
    choosing_delete: bool = False
    pending_delete: ExpenseTransactionResult | IncomingTransactionResult | None = None
    pending_account_id: int | None = None
    pending_debt_delete: DebtResult | None = None
    pending_debt_income: DebtResult | None = None
    transfers: dict[int, TransferTransactionResult] = field(default_factory=dict)
    pending_transfer_delete: TransferTransactionDeletionResult | None = None
    reconciliation: AccountReconciliationResult | None = None
    pending_adjustment: CreateBalanceAdjustmentCommand | None = None
    pending_reversal: BalanceAdjustmentReversalResult | None = None
    transfer_filters: GetTransferTransactionsCommand | None = None
    adjustment_filters: GetBalanceAdjustmentsCommand | None = None

    def clear(self) -> None:
        self.results.clear()
        self.shown_count = 0
        self.page_size = 10
        self.pending_changes = None
        self.choosing_delete = False
        self.pending_delete = None
        self.pending_account_id = None
        self.pending_debt_delete = None
        self.pending_debt_income = None
        self.transfers.clear()
        self.pending_transfer_delete = None
        self.reconciliation = None
        self.pending_adjustment = None
        self.pending_reversal = None
        self.transfer_filters = None
        self.adjustment_filters = None


@dataclass(slots=True)
class ScreenshotState:
    drafts: list[ScreenshotTransactionDraft] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    ready: bool = False
    fingerprints: set[str] = field(default_factory=set)
    processed: set[str] = field(default_factory=set)

    def clear(self) -> None:
        self.drafts.clear()
        self.warnings.clear()
        self.ready = False
        self.fingerprints.clear()


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class ConversationPair:
    user_message: str
    assistant_message: str


class ConversationMemory:
    def __init__(self, max_pairs: int) -> None:
        if max_pairs < 0:
            raise ValueError("max_pairs must be greater than or equal to zero")

        self._pairs: deque[ConversationPair] = deque(maxlen=max_pairs)
        self.transactions = TransactionState()
        self.screenshots = ScreenshotState()

    def add(self, user_message: str, assistant_message: str) -> None:
        self._pairs.append(
            ConversationPair(
                user_message=user_message,
                assistant_message=assistant_message,
            )
        )

    def messages(self) -> tuple[ChatMessage, ...]:
        messages: list[ChatMessage] = []

        for pair in self._pairs:
            messages.extend(
                (
                    ChatMessage(role="user", content=pair.user_message),
                    ChatMessage(role="assistant", content=pair.assistant_message),
                )
            )

        return tuple(messages)

    def clear(self) -> None:
        self._pairs.clear()
        self.transactions.clear()
        self.screenshots.clear()
        self.screenshots.processed.clear()
