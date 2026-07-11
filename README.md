# AI Financial Intelligence Platform

AI-driven **decision-support** system for a fixed 16-asset Indian-market universe
(NIFTY 50, Sensex, gold/silver ETFs, and 12 blue-chip NSE stocks). It ingests
market data, computes technical indicators, forecasts prices with the
[Kronos](https://github.com/shiyu-coder/Kronos) foundation model, and backtests
strategies on [NautilusTrader](https://nautilustrader.io). **No real trading** —
simulation and analytics only.

## Status: Phase 4.5 — production deployment (Render + Hugging Face Space)

Production architecture: **Vercel** (frontend) → **Render free tier** (slim
FastAPI backend, no torch) → **Hugging Face Space** (`ai-inference-service`:
official Kronos + MiniLM behind `POST /forecast` / `POST /embed`) →
**Supabase** (Postgres + Auth). `KRONOS_MODE` / `EMBEDDINGS_MODE` switch
between in-process models (`local`, the dev default) and the Space (`remote`,
production) — same models, same API surface, same persisted `model_name`.
Earlier phases: Supabase Auth + RBAC + per-user isolation (4), Next.js
dashboard/chat (3), agents + RAG (2), audit hardening (2.5 — see
`AUDIT_REPORT.md`), core platform (1).

| Capability | State |
|---|---|
| OHLCV ingestion (yfinance → Supabase `price_bars`) | ✅ |
| Technical indicators (SMA/EMA/RSI/MACD/Bollinger) | ✅ |
| Forecasting — baseline drift model | ✅ |
| Forecasting — Kronos (NeoQuasar/Kronos-small) | ✅ vendored + verified end-to-end (baseline stays as fallback) |
| Remote inference — Kronos + MiniLM on a HF Space (`KRONOS_MODE`/`EMBEDDINGS_MODE=remote`) | ✅ |
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
├── services/        # market_data, data_ingest, indicators, forecast/backtest, space_client
├── ml/              # Forecaster interface, baseline + Kronos (local & remote), registry
├── backtesting/     # Backtester interface, NautilusTrader + simple engines, strategies
└── scheduler/       # APScheduler: daily ingest + inference-Space keep-warm ping
```

### Production topology (Phase 4.5)

```
Users ──► Vercel (Next.js frontend, same-origin proxy /api/backend/*)
              │
              ▼
      Render free web service (backend/Dockerfile.render - no torch)
      FastAPI · auth · agents · RAG · chat · NautilusTrader · APScheduler
        │             │              │            │
        ▼             ▼              ▼            ▼
    Supabase     Gemini/OpenAI    NewsAPI    HF Space "ai-inference-service"
   (PG+Auth)                                 (official Kronos + MiniLM,
                                              /forecast /embed /health)
```

A GitHub Actions cron (`.github/workflows/keepalive.yml`) pings the backend
every 10 minutes (Render free instances sleep after 15 idle minutes); the
backend's scheduler pings the Space every 6 h so it never hits the ~48 h
free-tier idle shutdown.

## Getting started

Requirements: Python 3.12+, a Supabase (or Postgres 15+) database with the
pre-existing market-data schema.

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate    # Windows; use bin/activate on Unix
pip install -e ".[dev,local-ml]"                  # local-ml = torch/MiniLM for local inference

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

### Kronos forecaster modes

`model=kronos` resolves through `KRONOS_MODE`:

- **`local`** (dev default): the vendored official implementation
  (`backend/app/ml/kronos_src/`, MIT) runs in-process; weights download
  automatically from Hugging Face (`NeoQuasar/Kronos-small` +
  `NeoQuasar/Kronos-Tokenizer-base`) on first use. Requires the `local-ml`
  extra (torch).
- **`remote`** (production): `RemoteKronosForecaster` POSTs the same context
  window to the inference Space (`INFERENCE_SPACE_URL`) — see
  [docs/deploy-hf-space.md](docs/deploy-hf-space.md). The Render image ships
  without torch entirely. `EMBEDDINGS_MODE` does the same for MiniLM semantic
  memory.

Either way `model=baseline` always works, and a Kronos failure returns a clear
503 (agent runs fall back to baseline automatically).

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

CI (GitHub Actions) runs ruff → mypy → bandit → fast tests → pgvector
integration tests → frontend tsc/build → Docker builds (full image **and** the
slim Render image, asserting the latter boots torch-free) → a drift check
keeping `infrastructure/hf-space/kronos_src` byte-identical to
`backend/app/ml/kronos_src`.

### Local Postgres (optional)

`infrastructure/docker-compose.yml` provides pgvector Postgres + the backend.
Note: the base market-data schema is owned by earlier migrations that live in the
prior repository, so a fresh local DB needs a one-time schema load, e.g.
`pg_dump --schema-only` from Supabase, before `alembic upgrade head` applies the
`forecasts`/`backtests` tables on top. Day-to-day development targets Supabase.

## Deployment

- **Frontend → Vercel** (root directory `frontend/`). Env vars:
  `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `BACKEND_URL`
  (the Render URL; leave `BACKEND_API_KEY` empty in production — users
  authenticate with their own sessions).
- **Backend → Render free tier** (Docker, `backend/Dockerfile.render`,
  blueprint `render.yaml`) — runbook: [docs/deploy-render.md](docs/deploy-render.md).
  The slim image has no torch (~idle 230 MB, fits the 512 MB instance); a
  GitHub Actions cron keeps it awake so the daily ingest fires.
- **ML inference → Hugging Face Space** `ai-inference-service` (private
  Gradio-SDK Space on ZeroGPU hardware — HF's 2026 policy gates Docker/cpu-basic
  Spaces behind PRO; inference itself runs on CPU and consumes no GPU quota)
  serving the official Kronos + MiniLM — runbook:
  [docs/deploy-hf-space.md](docs/deploy-hf-space.md). Weights load from the
  Hub; nothing is re-uploaded to the Space repo.
- **Every environment variable** (what, where, secret-or-not):
  [docs/environment.md](docs/environment.md).
- **Self-hosting alternative:** the full image (`backend/Dockerfile`, torch
  included, `KRONOS_MODE=local`) still runs on any ≥2 GB Docker host via
  `infrastructure/docker-compose.prod.yml` (API behind Caddy auto-HTTPS).
- **Before production:** rotate every development credential and create the
  least-privilege DB role (checklist in [docs/deploy-render.md](docs/deploy-render.md)).

## Security

- All secrets come from `.env` (git-ignored). See `.env.example` for the keys.
- **Never commit API keys.** Keys previously exposed in planning documents must
  be treated as compromised and rotated.
- The database has RLS enabled deny-by-default; the backend connects as the
  owner role.

## Documents

- `docs/deploy-render.md` — backend deployment runbook (Render)
- `docs/deploy-hf-space.md` — inference Space runbook (Hugging Face)
- `docs/environment.md` — every environment variable, grouped, with where-to-set
- `deep-research-report (1).md` — original planning/research document
- `project_handover.md` — living status/handover document (kept current)
