from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    bot_token: str = Field(default="", alias="BOT_TOKEN")
    api_token: str = Field(default="", alias="API_TOKEN")
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-flash-latest", alias="GEMINI_MODEL")
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    groq_model: str = Field(default="openai/gpt-oss-20b", alias="GROQ_MODEL")
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field(default="openrouter/free", alias="OPENROUTER_MODEL")
    openrouter_site_url: str = Field(default="", alias="OPENROUTER_SITE_URL")
    openrouter_app_name: str = Field(default="Asnwero Reply Assistant", alias="OPENROUTER_APP_NAME")
    xai_api_key: str = Field(default="", alias="XAI_API_KEY")
    xai_model: str = Field(default="grok-4-fast-non-reasoning", alias="XAI_MODEL")
    xai_enabled: bool = Field(default=False, alias="XAI_ENABLED")
    allow_paid_models: bool = Field(default=False, alias="ALLOW_PAID_MODELS")
    database_path: Path = Field(default=Path("bot.sqlite3"), alias="DATABASE_PATH")
    request_timeout_seconds: float = Field(default=20, alias="REQUEST_TIMEOUT_SECONDS")
    max_source_chars: int = Field(default=4000, alias="MAX_SOURCE_CHARS")
    max_context_chars: int = Field(default=1000, alias="MAX_CONTEXT_CHARS")
    rate_limit_per_hour: int = Field(default=10, alias="RATE_LIMIT_PER_HOUR")
    task_ttl_hours: int = Field(default=24, alias="TASK_TTL_HOURS")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @model_validator(mode="after")
    def fill_telegram_token_aliases(self) -> "Settings":
        if not self.telegram_bot_token:
            self.telegram_bot_token = self.bot_token or self.api_token
        return self

    def validate_runtime(self) -> None:
        if not self.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN or BOT_TOKEN is required")


@lru_cache
def get_settings() -> Settings:
    return Settings()
