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

    # --- API security (Phase 2.5 hardening) ---
    # When api_key is set, every route except /live, /health, /docs, /openapi.json
    # requires the X-API-Key header. Empty = auth disabled (development only).
    api_key: str = ""
    rate_limit_per_minute: int = 120
    cors_origins: str = ""  # comma-separated origins; empty = CORS disabled
    expose_error_details: bool = False  # include internal error text in API responses

    # --- Database ---
    database_url: str = ""
    # asyncpg prepared-statement cache size. None = auto: disabled (0) when the
    # URL looks like a PgBouncer/Supabase pooler (transaction mode breaks named
    # prepared statements), default cache otherwise.
    db_statement_cache_size: int | None = None

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

    # --- LLM providers (Phase 2 agents) ---
    llm_provider: str = "gemini"  # gemini | openai | fake
    llm_fallback_provider: str | None = "openai"
    google_ai_studio_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str | None = None
    llm_timeout_seconds: float = 90.0

    # --- News (Phase 2) ---
    newsapi_key: str | None = None
    news_lookback_days: int = 7
    news_max_headlines: int = 12

    # --- Agents (Phase 2) ---
    agents_debate_rounds: int = 1
    max_position_pct: float = 10.0
    risk_max_drawdown_veto_pct: float = 40.0
    enable_agent_memory: bool = True
    embedding_model_id: str = "sentence-transformers/all-MiniLM-L6-v2"
    agent_memory_top_k: int = 3

    # --- Agent execution hardening (Phase 2.5) ---
    max_concurrent_agent_runs: int = 2
    agent_run_timeout_seconds: float = 600.0
    agent_run_stale_minutes: int = 30  # startup sweep marks older running runs failed
    memory_ttl_days: int = 90  # embeddings older than this are purged

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
