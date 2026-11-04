from functools import lru_cache

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    app_name: str = "SafeShift"
    environment: str = "local"

    gemini_api_key: SecretStr | None = None
    gemini_model: str | None = None
    gemini_fallback_model: str | None = None
    gemini_timeout_ms: int = Field(
        default=900,
        gt=0,
        validation_alias=AliasChoices("GEMINI_TIMEOUT_MS", "GEMINI_TIMEOUT"),
    )
    gemini_deadline_ms: int = Field(default=1_700, gt=0)
    gemini_max_retries: int = Field(
        default=1,
        ge=0,
        le=5,
        validation_alias=AliasChoices("GEMINI_MAX_RETRIES", "MAX_RETRIES"),
    )
    gemini_input_cost_per_million_usd: float | None = Field(default=None, ge=0)
    gemini_output_cost_per_million_usd: float | None = Field(default=None, ge=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
