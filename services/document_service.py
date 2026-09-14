import asyncio
import base64
from pathlib import PurePath

import requests

from schemas.document import DocumentInput, DocumentPage
from services.exceptions import ServiceError


class DocumentService:
    MAX_BYTES = 20 * 1024 * 1024

    @classmethod
    async def download(cls, url: str, name: str) -> DocumentInput:
        return await asyncio.to_thread(cls._download, url, name)

    @classmethod
    def _download(cls, url: str, name: str) -> DocumentInput:
        if not url.startswith("https://"):
            raise ServiceError("Не удалось получить защищённую ссылку на вложение.")
        with requests.get(
            url, timeout=60, stream=True, allow_redirects=False
        ) as response:
            if response.status_code != 200:
                raise ServiceError("Не удалось скачать вложение Max.")
            data = bytearray()
            for chunk in response.iter_content(chunk_size=65536):
                data.extend(chunk)
                if len(data) > cls.MAX_BYTES:
                    raise ServiceError("Документ больше 20 МБ. Разделите его на части.")
        return DocumentInput(name=name, data=bytes(data))

    @classmethod
    def prepare(cls, document: DocumentInput) -> list[DocumentPage]:
        data = document.data
        if not data or len(data) > cls.MAX_BYTES:
            raise ServiceError("Документ пуст или больше 20 МБ.")
        name = PurePath(document.name).name
        mime: str | None = None
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            mime = "image/png"
        elif data.startswith(b"\xff\xd8\xff"):
            mime = "image/jpeg"
        elif data[:6] in (b"GIF87a", b"GIF89a"):
            mime = "image/gif"
        elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
            mime = "image/webp"
        if mime is not None:
            encoded = base64.b64encode(data).decode("ascii")
            return [DocumentPage(name=name, image_url=f"data:{mime};base64,{encoded}")]
        raise ServiceError(
            "Чтение документов отключено. Пришлите скриншот в формате JPEG/PNG/GIF/WebP."
        )
