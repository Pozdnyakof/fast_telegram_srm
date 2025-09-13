from functools import lru_cache
from typing import Optional

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Required
    BOT_TOKEN: Optional[str] = None

    # Google Sheets / Service Account
    GOOGLE_SERVICE_ACCOUNT_JSON: Optional[str] = None
    GOOGLE_SPREADSHEET_ID: Optional[str] = None

    # Local DB
    DB_PATH: str = "./data/app.db"

    # Logging / Observability
    LOG_LEVEL: str = "INFO"
    SENTRY_DSN: Optional[str] = None

    # Timezone for timestamps (IANA name)
    TIMEZONE: str = "Europe/Moscow"

    # Optional: log joins even without invite link
    LOG_JOINS_WITHOUT_INVITE: bool = True

    # Optional: run a Google Sheets self-check on startup
    GSHEETS_SELF_CHECK: bool = True


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and cache application settings from environment/.env."""
    return Settings()  # type: ignore[call-arg]
