from collections import deque
from dataclasses import dataclass, field
from typing import Literal

from schemas.expense_transaction import ExpenseTransactionResult
from schemas.incoming_transaction import IncomingTransactionResult
from schemas.transaction import TransactionChanges


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

    def clear(self) -> None:
        self.results.clear()
        self.shown_count = 0
        self.page_size = 10
        self.pending_changes = None
        self.choosing_delete = False
        self.pending_delete = None


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
