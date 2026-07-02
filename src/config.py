"""Centralized, strictly-typed configuration loader."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    langfuse_public_key: str = Field(...)
    langfuse_secret_key: str = Field(...)  # OWASP LLM02:2025 — never hardcode
    langfuse_base_url: str = Field(default="https://cloud.langfuse.com")

    redis_url: str = Field(..., description="rediss:// TCP connection string")
    cache_ttl_seconds: int = Field(default=30)

    # --- Pricing constants (USD / 1M tokens), verified 2026-07 ---
    gemini_flash_input_per_1m: float = Field(default=0.30)
    gemini_flash_output_per_1m: float = Field(default=2.50)

    # GPT-4-class baseline = GPT-4o, "yours vs GPT-4 only"
    gpt4o_input_per_1m: float = Field(default=2.50)
    gpt4o_output_per_1m: float = Field(default=10.00)

    assumed_output_token_ratio: float = Field(default=0.35, ge=0.0, le=1.0)


settings = Settings()  # type: ignore[call-arg]