# project_handover.md

> Living status document. Update at every sprint / significant change.
> Last updated: **2026-07-06** (Phase 1 backend implemented)

## Project Overview

- **Name:** AI Financial Intelligence Platform
- **Objective:** AI-driven analysis & forecasting for a fixed 16-asset Indian-market
  universe (2 indices, 2 commodity ETFs, 12 blue-chips). Decision-support only — no
  real trading.
- **Working directory:** `D:\Claude Sessions\Stock` (backend code in `backend/`)
- **Database:** Supabase project **`ai-stock-prediction`** (ref `rekoawsoghrjcimknkfz`,
  region ap-south-1, Postgres 17)

## Key architecture decision (2026-07-06)

The Supabase DB already contained a mature schema from prior work ("Modules 0–2"):
`instruments` (16 rows, UUID PKs), `price_bars`, `data_providers` (yfinance/nse/bse),
`instrument_provider_mappings` (46 rows), `exchanges`/`sectors`/`industries`, a
`warehouse_*` subsystem, `agent_embeddings` (pgvector 0.8.2), RLS deny-by-default,
Alembic head `0004_warehouse`. **Decision: adopt & build on it** (confirmed by owner).
This repo's code was written fresh against that live schema; the prior repo that
produced migrations 0001–0004 is not vendored here (a no-op Alembic baseline anchors
the chain instead).

## Completed (Phase 1)

- **Environment:** Python 3.12.10 (installed system-wide), venv at `backend/.venv`,
  all deps installed incl. `nautilus_trader==1.230.0`, `torch 2.12`, pandas 3 / numpy 2.5.
- **Data pipeline:** `services/data_ingest.py` — yfinance (`auto_adjust=False`), retry
  w/ backoff, idempotent `ON CONFLICT DO NOTHING` upserts into `price_bars` keyed on
  (instrument, provider, date, timeframe). Provider tickers resolved via
  `instrument_provider_mappings`.
- **Indicators:** `services/indicators.py` — SMA/EMA/RSI(Wilder)/MACD/Bollinger,
  pure vectorized pandas, unit-tested.
- **Forecasting:** `Forecaster` interface + `BaselineForecaster` (drift) +
  `KronosForecaster` (NeoQuasar/Kronos-small via HF). Kronos source must be vendored
  to `app/ml/kronos_src/` (blocked on owner approval — auto-vendoring external code
  was denied by policy). Baseline fully working meanwhile.
- **Backtesting:** `Backtester` interface + `NautilusBacktester` (NautilusTrader
  1.230 BacktestEngine, CASH account, SMA-crossover strategy, analyzer metrics:
  Sharpe/Sortino/PnL/win-rate/drawdown) + `SimpleBacktester` (vectorized, for fast
  tests). Nautilus path proven end-to-end in tests.
- **API (FastAPI):** `/health`, `/instruments`, `/instruments/{s}/prices|indicators|forecast`,
  `/ingest/run`, `/backtest`. Global JSON-logging exception handler. Swagger at `/docs`.
- **Scheduler:** APScheduler daily ingest (13:00 UTC default), wired into lifespan.
- **Migrations:** `0004_warehouse` no-op baseline + `0005_forecasts_backtests`
  (forecasts, backtests tables, RLS enabled). **Not yet applied to Supabase.**
- **Quality:** 38 tests green (incl. Nautilus e2e), ruff clean, mypy clean, GitHub
  Actions CI (ruff→mypy→fast tests→docker build), Dockerfile + docker-compose.

## Pending / next tasks

1. **Apply migration 0005 to Supabase** and run end-to-end verification
   (needs `DATABASE_URL` with DB password in `.env` — ask owner).
2. **Vendor Kronos source** into `app/ml/kronos_src/` (owner approval needed; then
   `model=kronos` works; add a marked-slow smoke test).
3. **Phase 2:** multi-agent system (TradingAgents-inspired), RAG memory on
   `agent_embeddings`, news/sentiment ingestion.
4. **Phase 3:** Next.js dashboard + chat interface (Vercel), auth.
5. **Deployment:** backend needs a container host (Fly/Render/Cloud Run/ECS) —
   it does not fit Vercel serverless (torch + nautilus + scheduler).

## Known issues & pitfalls

- yfinance must stay `auto_adjust=False` (raw + adjusted closes both stored).
- Local docker-compose Postgres lacks the base schema (owned by the prior repo's
  migrations) — needs a one-time `pg_dump --schema-only` load from Supabase.
- pandas 3.x: yfinance emits deprecation warnings (`Timestamp.utcnow`) via
  nautilus run path — harmless, tracked upstream.
- The original research document leaked live API keys (OpenAI, Google, Alpha
  Vantage, NewsAPI, Twitter, Jupiter) — **rotate them**; none are needed for Phase 1.

## Configuration

`.env` at repo root (see `.env.example`): `DATABASE_URL` (Supabase, asyncpg),
`KRONOS_MODEL_ID`/`KRONOS_TOKENIZER_ID`/`KRONOS_DEVICE`, `ENABLE_SCHEDULER`,
`DAILY_INGEST_HOUR/MINUTE`, optional `HF_TOKEN`. Phase-2 keys (`OPENAI_API_KEY`,
`ANTHROPIC_API_KEY`) are placeholders only.

## Conventions

- Symbols in APIs are registry symbols (`RELIANCE`, `NIFTY50`, `GOLD`), not
  provider tickers (`RELIANCE.NS`, `^NSEI`).
- New tables follow existing DB conventions: UUID PK (`gen_random_uuid()`),
  timestamptz, JSONB, RLS enabled.
- Tests: fast suite must stay network/DB-free; heavy paths are `@pytest.mark.slow`;
  DB-integration tests are `@pytest.mark.db`.
