from datetime import timedelta
from datetime import timezone as datetime_timezone
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    api_key: str
    endpoint: str
    model: str
    db_name: str
    context_max_pairs: int = Field(default=5, ge=0)
    timezone: str = Field(default="+08:00", pattern=r"^[+-]\d{2}:\d{2}$")

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        hours, minutes = (int(part) for part in value[1:].split(":"))
        if hours > 23 or minutes > 59:
            raise ValueError("Timezone offset must be between -23:59 and +23:59")

        return value

    @property
    def timezone_info(self) -> datetime_timezone:
        sign = 1 if self.timezone.startswith("+") else -1
        hours, minutes = (int(part) for part in self.timezone[1:].split(":"))
        return datetime_timezone(sign * timedelta(hours=hours, minutes=minutes))

    @property
    def database_path(self) -> Path:
        path = Path(self.db_name)

        if path.is_absolute():
            return path

        return BASE_DIR / path

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
