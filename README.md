# AI Financial Intelligence — Trading Simulation Platform

An AI-driven **decision-support** and **paper-trading** platform for the Indian
equity market. It ingests market data, forecasts prices with a transformer
foundation model, runs a multi-agent LLM analysis pipeline, and lets users
paper-trade the resulting ideas on a professional, TradingView-style charting
workstation — all grounded in explainable, cited reasoning.

> **This platform never executes real trades.** Everything is simulated for
> research, learning, and analysis. Nothing here is investment advice.

**Live:**
[Web app](https://ai-financial-intelligence-platf-eklavya-singh-rathores-projects.vercel.app)
· backend on Render · ML inference on a Hugging Face Space · data on Supabase.

---

## What it does

| Capability | Summary |
|---|---|
| **Professional charting** | Lightweight-charts trading workstation: intraday → monthly intervals, 7 chart types (candles, Heikin-Ashi, bar, line, area, baseline, hollow), 15 technical indicators, a canvas **drawing-tools engine** (trend lines, Fibonacci, rectangles, measure, text) with undo/redo and per-symbol persistence, **Volume Profile**, and support/resistance + AI overlays. |
| **AI price forecasting** | The [Kronos](https://github.com/shiyu-coder/Kronos) foundation model forecasts future closes with a confidence horizon; overlaid on the chart by default. A baseline drift model is the always-available fallback. |
| **Multi-agent analysis** | A 7-agent LLM pipeline (technical analyst → news analyst → bull/bear debate → trader → risk manager → portfolio manager) produces a risk-limited recommendation, with a fully **explainable** breakdown of the inputs it saw. |
| **Paper trading** | A simulated portfolio with market / limit / stop / stop-limit orders, average-cost accounting, an equity/drawdown curve, and **human-in-the-loop AI proposals** (the AI proposes; a human accepts or rejects — it never auto-executes). |
| **Portfolio analytics** | Value-at-Risk (historical + parametric), Monte-Carlo simulation, mean-variance optimization, plus a risk/diversification/correlation intelligence digest. |
| **Financial research** | Company profiles, income / balance-sheet / cash-flow statements, and derived QoQ/YoY earnings analysis. |
| **Grounded AI chat** | A retrieval-augmented assistant — a full chat page **and** a site-wide floating dock — grounded in market data, agent decisions, and a persisted news corpus, with numbered citations. |
| **Market coverage** | A curated ~100-instrument Nifty universe, per-user watchlists, and **whole-market lazy loading** — search any NSE/BSE symbol and track it on demand via a durable background backfill queue. |
| **AI evaluation** | The platform measures its own quality: forecast accuracy (MAPE/bias), agent behaviour, recommendation success, and LLM cost/latency. |

---

## Architecture

A modular monolith backend, a Next.js frontend that reaches it only through an
authenticated same-origin proxy, and remote ML inference on a GPU-class Space —
so the always-on API server stays small and cheap.

```
Users ─▶ Vercel (Next.js 15 frontend)
            │   same-origin proxy /api/backend/* forwards the Supabase JWT server-side
            ▼
        Render (FastAPI — slim image, no torch)
        auth · charting/OHLCV · agents · paper trading · research · RAG · chat · analytics
          ├─▶ Supabase (Postgres 17 + pgvector, Auth)
          ├─▶ Hugging Face Space  (Kronos forecasts + MiniLM embeddings, CPU inference)
          ├─▶ Gemini / OpenAI     (agent + chat LLMs, with automatic failover)
          └─▶ yfinance · NewsAPI · Finnhub · Alpha Vantage (market data & news)
```

**Backend layering** (`backend/app/`):

```
api/routers ─▶ services ─▶ (ml | backtesting | llm | agents | providers) ─▶ models/db
```

Routers stay thin; business logic lives in `services`; CPU-bound work (forecasts,
backtests, embeddings) runs off the event loop. Implementation choices — which
forecaster, backtester, LLM, or data provider — come from **registries**, so
swapping one is a configuration change, not a rewrite. The ML forecaster and
embedding model run **in-process locally** (torch) or **remotely on the Space**
via an identical API surface, selected by a single environment flag.

### Tech stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 15 (App Router, TypeScript), Tailwind v4 (CSS-var design tokens), TanStack Query, TradingView Lightweight Charts, next-themes |
| Backend | FastAPI (async), SQLAlchemy 2 + asyncpg, Pydantic, APScheduler, structlog |
| Database | Supabase — Postgres 17 + pgvector, Row-Level Security, Supabase Auth (JWT) |
| ML / AI | Kronos time-series foundation model, sentence-transformers (MiniLM 384-d), Google Gemini + OpenAI, NautilusTrader (backtesting) |
| Infra | Vercel (frontend), Render (backend, Docker), Hugging Face Spaces (ZeroGPU inference), GitHub Actions (CI + keep-alive) |

---

## Getting started

**Requirements:** Python 3.12+, Node 20+, and a Postgres 15+ / Supabase database.

### Backend

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate      # Windows; use bin/activate on Unix
pip install -e ".[dev,local-ml]"                     # local-ml = torch + MiniLM for in-process inference

cp ../.env.example ../.env                            # then fill in DATABASE_URL and the keys you have
alembic upgrade head                                  # apply the migration chain
uvicorn app.main:app --reload                         # Swagger UI at http://localhost:8000/docs
```

The app boots with partial configuration and **degrades explicitly** — missing an
LLM key disables agents but not charts; missing a news key drops citations but
not answers; every external provider falls back to keyless `yfinance`.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local                            # BACKEND_URL + Supabase public keys
npm run dev                                            # http://localhost:3000
```

All API calls go through the authenticated same-origin proxy at
`app/api/backend/[...path]` — the backend API key and any service credentials
never reach the browser.

---

## Project structure

```
backend/            FastAPI application
  app/
    api/routers/    HTTP endpoints (instruments, agents, chat, simulation, market, admin, …)
    services/       business logic (market data, OHLCV resolver, agents, simulation, analytics, research, RAG)
    ml/             Forecaster interface + Kronos (local & remote) + baseline; vendored kronos_src (MIT)
    backtesting/    Backtester interface + NautilusTrader / simple engines
    llm/            LLM client + Gemini/OpenAI failover
    agents/         7-agent orchestrator, prompts, risk limits, explainability
    providers/      capability-based external-data abstraction (yfinance, Finnhub, Alpha Vantage, …)
    catalog/        curated instrument universe
    models/ db/     SQLAlchemy ORM + async engine
  alembic/          database migrations
  tests/            unit + database-integration suites
frontend/           Next.js 15 app
  app/              routes (dashboard, instrument detail, portfolio, simulation, agents, insights, chat, login)
  components/        UI primitive library, charting (chart/), simulation, assistant dock, command palette
  lib/              typed API client + pure logic (indicators, chart math, drawings) with node:test coverage
docs/               MASTER_ARCHITECTURE, per-area architecture, ADRs, deployment runbooks, environment reference
infrastructure/     Docker Compose, the Hugging Face inference Space
```

---

## Security & data model

- **Authentication:** Supabase Auth issues JWTs; the backend verifies them on
  every business route (local HS256 or remote validation with caching). A static
  `X-API-Key` grants a service context for automation. A guest account enables a
  no-signup demo with full per-user isolation.
- **Authorization:** role hierarchy `service` > `admin` > `user`. Each user sees
  only the rows they own (chat, agent runs, backtests, forecasts, portfolios,
  watchlists); cross-user access returns `404`.
- **Database posture:** Row-Level Security is **enabled deny-by-default** on
  every table — the auto-generated REST API is fully locked; all access is
  mediated by the backend, which enforces ownership in application code.
- **Secrets:** all credentials come from environment variables (`.env` is
  git-ignored). See [`docs/environment.md`](docs/environment.md) for every
  variable, where it is set, and whether it is a secret.

---

## Testing & CI

```bash
# backend
pytest -m "not slow and not db"    # fast unit suite
pytest -m db                        # database-integration suite (needs a Postgres/Supabase URL)
ruff check app tests && mypy app && bandit -r app

# frontend
npm run typecheck && npm test && npm run build
```

GitHub Actions runs lint → type-check → security scan → unit tests → pgvector
integration tests → frontend build → Docker builds (full **and** the slim
torch-free production image), and a drift check keeping the vendored Kronos
source byte-identical between the backend and the inference Space.

---

## Documentation

- [`docs/MASTER_ARCHITECTURE.md`](docs/MASTER_ARCHITECTURE.md) — the complete system reference (start here)
- [`docs/architecture/`](docs/architecture/) — per-area deep dives (system, backend, frontend, database, agents, security, deployment)
- [`docs/adr/`](docs/adr/) — architecture decision records
- [`docs/deploy-render.md`](docs/deploy-render.md) · [`docs/deploy-hf-space.md`](docs/deploy-hf-space.md) — deployment runbooks
- [`docs/environment.md`](docs/environment.md) — every environment variable
- [`project_handover.md`](project_handover.md) — living status & handover document

---

## Disclaimer

This project is for **education, research, and simulation only**. It does not
execute real trades, does not connect to a broker, and does not provide
financial advice. Forecasts and AI recommendations are experimental and may be
wrong. Do your own research.
