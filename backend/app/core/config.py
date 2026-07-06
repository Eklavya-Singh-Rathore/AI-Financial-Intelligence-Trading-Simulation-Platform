"""Application configuration loaded from environment / `.env`.

All settings are read once and cached. Secrets (DATABASE_URL, HF_TOKEN, LLM keys)
are read from the repository-root `.env` file which is git-ignored.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> parents[3] == repository root
PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Typed application settings."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Runtime ---
    env: str = "development"
    log_level: str = "INFO"

    # --- Database ---
    database_url: str = ""

    # --- Hugging Face / Kronos ---
    hf_token: str | None = None
    kronos_model_id: str = "NeoQuasar/Kronos-small"
    kronos_tokenizer_id: str = "NeoQuasar/Kronos-Tokenizer-base"
    kronos_max_context: int = 512
    kronos_device: str = "cpu"

    # --- Data ingestion / scheduler ---
    default_history_days: int = 1095
    enable_scheduler: bool = True
    daily_ingest_hour: int = 13
    daily_ingest_minute: int = 0

    # --- Forecasting defaults ---
    default_forecaster: str = "kronos"

    # --- Phase 2+ placeholders (unused in Phase 1) ---
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None

    @property
    def async_database_url(self) -> str:
        """Return the DATABASE_URL normalised to the asyncpg driver."""
        url = self.database_url.strip()
        if not url:
            return ""
        if url.startswith("postgresql+asyncpg://"):
            return url
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url

    @property
    def database_configured(self) -> bool:
        return bool(self.database_url.strip())


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor."""
    return Settings()
