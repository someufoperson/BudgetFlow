from collections import deque
from dataclasses import dataclass
from typing import Literal


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
