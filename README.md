# AI Financial Intelligence Platform

AI-driven **decision-support** system for a fixed 16-asset Indian-market universe
(NIFTY 50, Sensex, gold/silver ETFs, and 12 blue-chip NSE stocks). It ingests
market data, computes technical indicators, forecasts prices with the
[Kronos](https://github.com/shiyu-coder/Kronos) foundation model, and backtests
strategies on [NautilusTrader](https://nautilustrader.io). **No real trading** —
simulation and analytics only.

## Status: Phase 2.5 (hardening & audit remediation) complete

All Critical and High findings from `AUDIT_REPORT.md` are remediated in code:
API-key auth + rate limiting + run-concurrency caps, CPU/model work off the
event loop, session-rollback discipline, orphan-run recovery + per-run
timeouts, normalized LLM failover with retry classification, pooler-safe DB
config, pinned dependencies (`backend/requirements.lock`), hardened non-root
Docker image, prompt trust boundaries, fail-closed risk defaults, sanitized
errors, request-ID logging, Prometheus `/metrics`, and a DB-integration test
suite that runs in CI against a bootstrapped Postgres
(`scripts/base_schema.sql`).

| Capability | State |
|---|---|
| OHLCV ingestion (yfinance → Supabase `price_bars`) | ✅ |
| Technical indicators (SMA/EMA/RSI/MACD/Bollinger) | ✅ |
| Forecasting — baseline drift model | ✅ |
| Forecasting — Kronos (NeoQuasar/Kronos-small) | ✅ vendored + verified end-to-end (baseline stays as fallback) |
| Backtesting — NautilusTrader 1.230 + simple vectorized engine | ✅ |
| Daily scheduler (APScheduler) | ✅ |
| LLM layer — Gemini primary + OpenAI fallback + fake (tests) | ✅ (Gemini live-verified) |
| News/sentiment feed (NewsAPI) | ✅ (live-verified) |
| Multi-agent pipeline (analysts → debate → trader → risk → PM) | ✅ |
| Semantic memory (MiniLM 384 + pgvector `agent_embeddings`) | ✅ |
| Web dashboard (Next.js 15): universe table, candle charts + forecast overlay, backtest UI | ✅ live-verified |
| Agent-run UI (live-polling transcript + decision card) | ✅ |
| Chat UI (persisted sessions, grounded answers, context chips) | ✅ live-verified |

### Agents API

`POST /agents/run {"symbol": "RELIANCE"}` → `202` with a run id; the pipeline
executes in the background (typically 7 LLM calls). Poll `GET /agents/runs/{id}`
until `completed`, then read the full transcript at
`GET /agents/runs/{id}/messages`. Every decision passes coded risk limits
(position-size cap, drawdown veto) that the LLMs cannot loosen.

## Architecture

Modular monolith: FastAPI backend (this repo, `backend/`) + Supabase Postgres
(pre-existing schema: `instruments`, `price_bars`, `data_providers`,
`instrument_provider_mappings`, pgvector). This project **adopts** that schema —
Alembic continues from the existing head (`0004_warehouse`) and adds only
`forecasts` and `backtests` (revision `0005_forecasts_backtests`).

```
backend/app/
├── api/routers/     # health, instruments (prices/indicators/forecast), ingest, backtest
├── core/            # settings (pydantic-settings), structlog config, domain constants
├── db/              # async SQLAlchemy engine/session
├── models/          # ORM: existing tables (read) + forecasts/backtests (owned)
├── services/        # market_data, data_ingest, indicators, forecast/backtest orchestration
├── ml/              # Forecaster interface, baseline + Kronos adapters, registry
├── backtesting/     # Backtester interface, NautilusTrader + simple engines, strategies
└── scheduler/       # APScheduler daily ingest job
```

## Getting started

Requirements: Python 3.12+, a Supabase (or Postgres 15+) database with the
pre-existing market-data schema.

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate    # Windows; use bin/activate on Unix
pip install -e ".[dev]"

# configure
cp ../.env.example ../.env                        # then fill in DATABASE_URL

# migrate (adds forecasts/backtests to the existing schema)
alembic upgrade head

# run
uvicorn app.main:app --reload                     # Swagger at http://localhost:8000/docs
```

### Security model (Phases 2.5 + 4)

- **User auth (Phase 4):** Supabase Auth issues JWTs; the backend accepts
  `Authorization: Bearer <token>` on every business route. Verification is
  local HS256 when `SUPABASE_JWT_SECRET` is set, otherwise validated against
  Supabase `/auth/v1/user` (cached). Roles: `admin` (granted automatically to
  the owner emails at sign-up via a DB trigger) sees everything; `user` sees
  only rows they own (`user_id` on chat sessions, agent runs, backtests,
  forecasts — cross-user access returns 404). Sign-up is open.
- **Service auth:** set `API_KEY` in `.env`; the `X-API-Key` header grants an
  admin-equivalent service context (automation, tests, local-dev proxy
  fallback). With neither configured the API runs open (development only,
  loudly warned at startup).
- Per-client rate limiting (`RATE_LIMIT_PER_MINUTE`), agent-run concurrency cap
  (`MAX_CONCURRENT_AGENT_RUNS`, 429 on saturation), one in-flight run per
  symbol (409), and `Idempotency-Key` support on `POST /agents/run`.
- Routes are also mounted under `/api/v1` (canonical going forward); root
  paths remain for backward compatibility.
- `GET /live` = pure liveness; `GET /health` = readiness (DB check);
  `GET /metrics` = Prometheus (API-key protected).

### Key endpoints

| Endpoint | Purpose |
|---|---|
| `GET /health` | liveness + DB connectivity |
| `GET /instruments` | the 16-asset universe |
| `POST /ingest/run` | fetch & upsert OHLCV (idempotent) |
| `GET /instruments/{symbol}/prices` | stored OHLCV |
| `GET /instruments/{symbol}/indicators?names=sma,rsi` | computed indicators |
| `GET /instruments/{symbol}/forecast?horizon=5&model=kronos` | price forecast |
| `POST /backtest` | run SMA-crossover backtest (nautilus or simple engine) |

Symbols are the internal registry symbols (e.g. `RELIANCE`, `NIFTY50`, `GOLD`) —
provider tickers like `RELIANCE.NS` are resolved via `instrument_provider_mappings`.

### Enabling the Kronos forecaster

The Kronos runtime classes are not on PyPI. Copy `model/__init__.py`,
`model/kronos.py`, `model/module.py` (and LICENSE) from
[shiyu-coder/Kronos](https://github.com/shiyu-coder/Kronos) (MIT) into
`backend/app/ml/kronos_src/`. Weights download automatically from Hugging Face
(`NeoQuasar/Kronos-small` + `NeoQuasar/Kronos-Tokenizer-base`) on first use.
Until then, `model=baseline` works and `model=kronos` returns a clear 503.

### Frontend (Phase 3)

```bash
cd frontend
npm install
cp .env.example .env.local    # BACKEND_URL + BACKEND_API_KEY (server-side only)
npm run dev                   # http://localhost:3000 (backend must run on :8000)
```

Next.js 15 (App Router, TS) + Tailwind v4 + TanStack Query + TradingView
lightweight-charts + next-themes (system-adaptive light/dark). All API calls go
through the authenticated same-origin proxy at `app/api/backend/[...path]` —
the backend API key never reaches the browser.

## Development

```bash
pytest -m "not slow" -q      # fast suite (no model downloads / heavy engines)
pytest -q                    # full suite incl. NautilusTrader end-to-end
ruff check app tests
mypy app
```

CI (GitHub Actions) runs ruff → mypy → fast tests → Docker build on every push/PR.

### Local Postgres (optional)

`infrastructure/docker-compose.yml` provides pgvector Postgres + the backend.
Note: the base market-data schema is owned by earlier migrations that live in the
prior repository, so a fresh local DB needs a one-time schema load, e.g.
`pg_dump --schema-only` from Supabase, before `alembic upgrade head` applies the
`forecasts`/`backtests` tables on top. Day-to-day development targets Supabase.

## Deployment

- **Frontend:** Vercel (root directory `frontend/`). Env vars:
  `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `BACKEND_URL`
  (the backend's public URL once hosted; leave `BACKEND_API_KEY` empty in
  production — users authenticate with their own sessions).
- **Backend:** any Docker host; the maintained runbook targets Oracle Cloud —
  see [docs/deploy-oracle.md](docs/deploy-oracle.md)
  (`infrastructure/docker-compose.prod.yml` runs the API behind Caddy with
  automatic HTTPS). Not Vercel-deployable (multi-GB torch/nautilus image).
- **Before production:** rotate every development credential (list in
  docs/deploy-oracle.md) and create the least-privilege DB role.

## Security

- All secrets come from `.env` (git-ignored). See `.env.example` for the keys.
- **Never commit API keys.** Keys previously exposed in planning documents must
  be treated as compromised and rotated.
- The database has RLS enabled deny-by-default; the backend connects as the
  owner role.

## Documents

- `deep-research-report (1).md` — original planning/research document
- `project_handover.md` — living status/handover document (kept current)
