import requests

from ai.memory import ChatMessage
from settings import settings


class AIClient:
    _MAX_TOKENS = 2048
    _MAX_ATTEMPTS = 2

    def __init__(self) -> None:
        self._endpoint = settings.endpoint
        self._api_key = settings.api_key
        self._model = settings.model

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        history: tuple[ChatMessage, ...] = (),
    ) -> str:
        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": system_prompt,
            }
        ]
        messages.extend(
            {
                "role": message.role,
                "content": message.content,
            }
            for message in history
        )
        messages.append(
            {
                "role": "user",
                "content": user_prompt,
            }
        )

        for attempt in range(self._MAX_ATTEMPTS):
            response = requests.post(
                self._endpoint,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "temperature": 0.0,
                    "messages": messages,
                    "response_format": {
                        "type": "json_object",
                    },
                    "thinking": {
                        "type": "disabled",
                    },
                    "max_tokens": self._MAX_TOKENS,
                    "stream": False,
                },
                timeout=45,
            )

            response.raise_for_status()

            provider_data = response.json()
            choice = provider_data["choices"][0]
            content: str | None = choice["message"]["content"]

            if content is not None and content.strip():
                return content

            if attempt + 1 == self._MAX_ATTEMPTS:
                print(
                    "AI вернул пустой content после двух попыток: "
                    f"finish_reason={choice.get('finish_reason')!r}, "
                    f"usage={provider_data.get('usage')!r}",
                    flush=True,
                )
                return content or ""

        raise RuntimeError("AI request attempts exhausted")
