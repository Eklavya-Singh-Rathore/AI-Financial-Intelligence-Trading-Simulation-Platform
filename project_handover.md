# project_handover.md

> Living status document. Update at every sprint / significant change.
> Last updated: **2026-07-07** (Phase 2 multi-agent system implemented)

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
  (forecasts, backtests tables, RLS enabled). **Applied to Supabase 2026-07-06**
  (via Supabase MCP; `alembic_version` stamped to `0005_forecasts_backtests`).
- **Quality:** 38 tests green (incl. Nautilus e2e), ruff clean, mypy clean, GitHub
  Actions CI (ruff→mypy→fast tests→docker build), Dockerfile + docker-compose.

## Completed (Phase 2, 2026-07-07) — multi-agent system

- **LLM layer (`app/llm/`):** provider abstraction with **Gemini primary**
  (`gemini-2.5-flash`, google-genai SDK) and **OpenAI fallback** (`gpt-4o-mini`),
  plus a deterministic `FakeLLMClient` for tests. `FailoverLLMClient` retries the
  primary once then falls back. JSON-schema-constrained outputs, token usage +
  latency logged per call. **Live-verified:** Gemini answers correctly (~1.7 s);
  the doc's **OpenAI key has NO quota (429)** — fallback is dead until a funded
  key is supplied (failover logic itself is unit-tested).
- **News (`services/news.py`):** NewsAPI headlines per instrument, graceful
  degradation. **Live-verified** (5 headlines for Reliance Industries).
- **Agents (`app/agents/`):** TradingAgents-inspired custom pipeline —
  gather (prices/indicators/forecast/backtest/news/memory, all deterministic) →
  technical analyst → news analyst → bull/bear debate (configurable rounds) →
  trader → risk manager → portfolio manager. All outputs are pydantic-validated
  JSON. **Coded hard limits** (`agents/risk.py:apply_hard_limits`) bind every LLM
  decision: size cap `MAX_POSITION_PCT`, drawdown veto, LLM can only shrink sizes.
- **Memory:** local MiniLM embeddings (384-dim, matches pre-existing
  `agent_embeddings` table) via sentence-transformers; key reports embedded after
  each run; top-k recall injected into the next run's context. Degrades to
  memory-off when the model is unavailable.
- **API:** `POST /agents/run` (202 + background execution), `GET /agents/runs`,
  `GET /agents/runs/{id}`, `GET /agents/runs/{id}/messages`.
- **DB:** migration `0006_agent_runs` (agent_runs, agent_messages; RLS enabled)
  **applied to Supabase**, `alembic_version = 0006_agent_runs`.
- **Quality:** 70 fast tests green (agents pipeline with scripted FakeLLM,
  failover, hard limits, news parsing, LLM JSON parsing), ruff + mypy clean.

## Pending / next tasks

1. **Runtime verification against Supabase** — ingest real OHLCV, then run the
   full agent pipeline end-to-end (needs `DATABASE_URL` with DB password in
   `.env`, which only the owner can provide — the research doc has a placeholder).
2. **Vendor Kronos source** into `app/ml/kronos_src/` — **twice blocked** by the
   permission classifier (untrusted external code). Owner must either copy
   `model/{__init__,kronos,module}.py` + LICENSE from shiyu-coder/Kronos manually
   or add a Bash permission rule and ask again. Baseline forecaster active
   meanwhile.
3. **OpenAI fallback key** — current key has no quota (429 insufficient_quota);
   supply a funded key if a working fallback is wanted.
4. **Phase 3:** Next.js dashboard + chat interface (Vercel), auth, alerts.
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

`.env` at repo root (see `.env.example`): `DATABASE_URL` (Supabase, asyncpg —
STILL EMPTY, owner must fill), `LLM_PROVIDER=gemini` + `GOOGLE_AI_STUDIO_API_KEY`,
`LLM_FALLBACK_PROVIDER=openai` + `OPENAI_API_KEY`, `NEWSAPI_KEY`,
`KRONOS_MODEL_ID`/`KRONOS_TOKENIZER_ID`/`KRONOS_DEVICE`, `ENABLE_SCHEDULER`,
`DAILY_INGEST_HOUR/MINUTE`, agent knobs (`AGENTS_DEBATE_ROUNDS`,
`MAX_POSITION_PCT`, `RISK_MAX_DRAWDOWN_VETO_PCT`, `ENABLE_AGENT_MEMORY`).
Dev keys are the ones from the research doc (owner-authorized for development);
**rotate every key before deployment**.

## Conventions

- Symbols in APIs are registry symbols (`RELIANCE`, `NIFTY50`, `GOLD`), not
  provider tickers (`RELIANCE.NS`, `^NSEI`).
- New tables follow existing DB conventions: UUID PK (`gen_random_uuid()`),
  timestamptz, JSONB, RLS enabled.
- Tests: fast suite must stay network/DB-free; heavy paths are `@pytest.mark.slow`;
  DB-integration tests are `@pytest.mark.db`.
