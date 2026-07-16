import requests

from settings import settings


class AIClient:
    def __init__(self) -> None:
        self._endpoint = settings.endpoint
        self._api_key = settings.api_key

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        response = requests.post(
            self._endpoint,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={
                "messages": [
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {
                        "role": "user",
                        "content": user_prompt,
                    },
                ]
            },
            timeout=30,
        )

        response.raise_for_status()

        provider_data = response.json()

        return provider_data["choices"][0]["message"]["content"]
