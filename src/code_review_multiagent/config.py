from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = Field(default="sqlite:///code_review.db", alias="DATABASE_URL")
    db_pool_size: int = 5
    db_pool_recycle: int = 3600

    # GitHub
    github_webhook_secret: str = Field(default="", alias="GITHUB_WEBHOOK_SECRET")
    github_token: str = Field(default="", alias="GITHUB_TOKEN")

    # LLM
    llm_provider: Literal["claude", "deepseek", "newapi"] = Field(default="claude", alias="LLM_PROVIDER")
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_base_url: str = Field(default="", alias="LLM_BASE_URL")
    llm_model: str = Field(default="claude-sonnet-4-20250514", alias="LLM_MODEL")
    llm_timeout: float = Field(default=120.0, alias="LLM_TIMEOUT")

    # CORS
    cors_allowed_origins: str = Field(default="http://localhost:3000", alias="CORS_ALLOWED_ORIGINS")

    # App
    debug: bool = Field(default=False, alias="APP_DEBUG")
    log_level: str = Field(default="INFO", alias="APP_LOG_LEVEL")
    log_format: Literal["json", "text"] = Field(default="json", alias="APP_LOG_FORMAT")

    # Message Bus
    message_bus_backend: str = Field(default="memory", alias="MESSAGE_BUS_BACKEND")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


_settings: AppSettings | None = None


def get_settings() -> AppSettings:
    global _settings
    if _settings is None:
        _settings = AppSettings()
    return _settings


def override_settings(settings: AppSettings) -> None:
    global _settings
    _settings = settings
