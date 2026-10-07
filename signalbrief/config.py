from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)
    database_path: Path = Path("data/signalbrief.sqlite3")
    competitors_path: Path = Path("competitors.json")
    admin_password: SecretStr = SecretStr("")
    webhook_api_key: SecretStr = SecretStr("")
    session_secret: SecretStr = SecretStr("")
    public_base_url: str = "http://localhost:8000"
    secure_cookies: bool = False
    llm_provider: str = "groq"
    llm_model: str = "openai/gpt-oss-120b"
    llm_api_key: SecretStr = SecretStr("")
    groq_api_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")
    zapier_hook_url: SecretStr = SecretStr("")
    source_timeout_seconds: int = 20
    model_timeout_seconds: int = 75
    lease_seconds: int = 180
    max_attempts: int = 3
    worker_poll_seconds: float = 2.0
    max_daily_runs: int = 20
    max_sources: int = 4
    max_source_chars: int = 14000

    @field_validator("llm_provider")
    @classmethod
    def provider_valid(cls, value: str) -> str:
        if value not in {"groq", "openai"}:
            raise ValueError("LLM_PROVIDER must be groq or openai")
        return value

    @field_validator("source_timeout_seconds", "model_timeout_seconds", "lease_seconds", "max_attempts",
                     "max_daily_runs", "max_sources", "max_source_chars")
    @classmethod
    def positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("Limits must be positive")
        return value

    @property
    def model_key(self) -> str:
        return self.llm_api_key.get_secret_value() or (
            self.groq_api_key if self.llm_provider == "groq" else self.openai_api_key
        ).get_secret_value()

    @property
    def model_base_url(self) -> str:
        return "https://api.groq.com/openai/v1" if self.llm_provider == "groq" else "https://api.openai.com/v1"

    def require_auth(self) -> None:
        if len(self.admin_password.get_secret_value()) < 12:
            raise ValueError("Set ADMIN_PASSWORD (at least 12 characters); run python -m signalbrief.setup")
        if min(len(self.webhook_api_key.get_secret_value()), len(self.session_secret.get_secret_value())) < 32:
            raise ValueError("Set WEBHOOK_API_KEY and SESSION_SECRET (at least 32 characters)")


@lru_cache
def get_settings() -> Settings:
    return Settings()
