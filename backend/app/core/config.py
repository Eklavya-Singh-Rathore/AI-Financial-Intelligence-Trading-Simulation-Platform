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

    # --- Supabase Auth (Phase 4 user authentication) ---
    # supabase_url + supabase_anon_key enable Bearer-JWT user auth. JWT
    # verification is local HS256 when supabase_jwt_secret is set (dashboard ->
    # Settings -> API -> JWT Secret), otherwise remote via /auth/v1/user.
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_jwt_secret: str = ""
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
    # Model selection is variant-driven (see app/ml/kronos_variants.py).
    # KRONOS_VARIANT picks mini|small|base; empty = automatic by ENV (base for
    # local dev, small in production - the free-tier inference budget). The three
    # fields below are optional low-level overrides (empty/0 = derive from the
    # variant) kept for back-compat with deployments that pin Hub ids directly.
    kronos_variant: str = ""
    kronos_model_id: str = ""
    kronos_tokenizer_id: str = ""
    kronos_max_context: int = 0
    kronos_device: str = "cpu"

    # --- Remote inference (Phase 4.5: Hugging Face Space) ---
    # "local" runs Kronos/MiniLM in-process (dev default); "remote" calls the
    # inference Space at inference_space_url (POST /forecast, POST /embed).
    # hf_token (above) authenticates against a private Space;
    # inference_space_api_key is an optional shared-secret X-API-Key header
    # (public-Space option). Both may be set together.
    kronos_mode: str = "local"  # local | remote
    embeddings_mode: str = "local"  # local | remote
    inference_space_url: str = ""
    inference_space_api_key: str = ""
    inference_connect_timeout_seconds: float = 10.0
    inference_read_timeout_seconds: float = 120.0
    inference_max_retries: int = 2  # extra attempts after the first
    inference_retry_backoff_seconds: float = 1.5
    inference_wake_max_wait_seconds: float = 180.0  # budget while a slept Space wakes

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
    # gemini-flash-latest is Google's stable alias that always tracks the current
    # Flash tier; pinned versions (e.g. gemini-2.5-flash) get retired for new API
    # keys and then 404. Using the alias keeps the flash price tier and avoids
    # that recurring breakage. Override with GEMINI_MODEL if a pin is required.
    gemini_model: str = "gemini-flash-latest"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str | None = None
    llm_timeout_seconds: float = 90.0

    # --- News (Phase 2) ---
    newsapi_key: str | None = None
    news_lookback_days: int = 7
    news_max_headlines: int = 12

    # --- Data providers (Phase 6, all optional; each degrades when keyless) ---
    finnhub_api_key: str | None = None
    alpha_vantage_api_key: str | None = None
    alpha_vantage_daily_cap: int = 20  # free tier hard limit is 25/day
    # Aggregate ordering by provider code (first available wins per capability).
    provider_priority: str = "yfinance,finnhub,alpha_vantage,newsapi"
    # Whole-market lazy loading: hard cap on total tracked instruments.
    max_tracked_instruments: int = 300

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

    # --- Paper trading / research / evaluation (Phase 5) ---
    sim_starting_cash: float = 1_000_000.0  # paper portfolio starting cash (INR)
    fundamentals_ttl_hours: int = 24  # yfinance fundamentals cache TTL
    enable_news_ingest: bool = True  # daily scheduler job persisting news into RAG
    news_rag_top_k: int = 5  # news headlines retrieved per chat message
    news_retention_days: int = 180  # news documents older than this are purged
    # Phase 6 market expansion: keep free-tier quotas honest at ~100 instruments.
    news_ingest_daily_cap: int = 60  # max NewsAPI requests per daily news job
    ingest_pause_seconds: float = 0.3  # sleep between per-instrument OHLCV fetches
    # Cost estimation only (per 1M tokens, USD) - configurable per provider price list.
    llm_cost_input_per_1m: float = 0.30
    llm_cost_output_per_1m: float = 2.50

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
