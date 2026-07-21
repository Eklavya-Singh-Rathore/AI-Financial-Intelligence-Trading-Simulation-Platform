# FinIntel — AI Financial Intelligence

An AI-driven **decision-support** and **paper-trading** platform for the Indian
equity market. FinIntel ingests market data, forecasts prices with a
transformer foundation model, runs a multi-agent LLM analysis pipeline, and lets
users paper-trade the resulting ideas on a professional, TradingView-style
charting workstation — all grounded in explainable, cited reasoning.

> **FinIntel never executes real trades.** Everything is simulated for research,
> learning, and analysis. Nothing here is investment advice.

**Live:**
[Web app](https://ai-financial-intelligence-platf-eklavya-singh-rathores-projects.vercel.app)
· backend on Render · ML inference on a Hugging Face Space · data on Supabase.

---

## Table of contents

[Overview](#overview) · [Features](#features) · [Architecture](#architecture) ·
[Technology stack](#technology-stack) · [AI architecture](#ai-architecture) ·
[News intelligence](#news-intelligence) · [Forecasting](#forecasting) ·
[Paper trading](#paper-trading) · [Portfolio analytics](#portfolio-analytics) ·
[Authentication](#authentication) · [Installation](#installation) ·
[Environment variables](#environment-variables) ·
[Local development](#local-development) · [Deployment](#deployment) ·
[Project structure](#project-structure) · [API overview](#api-overview) ·
[Testing](#testing) · [Security](#security) · [Roadmap](#roadmap) ·
[Contributing](#contributing) · [License](#license) ·
[Acknowledgements](#acknowledgements)

---

## Overview

FinIntel is a full-stack platform that turns raw market data into
decision-ready, explainable intelligence. A Next.js frontend reaches an async
FastAPI backend through an authenticated same-origin proxy; heavy ML inference
runs remotely on a GPU-class Hugging Face Space so the always-on API server
stays small and inexpensive. Every recommendation is traceable to the data and
reasoning that produced it, and every user works in a fully isolated workspace.

The platform is deliberately honest about uncertainty: components **degrade
explicitly** rather than fail. Missing an LLM key disables the agent pipeline but
not the charts; missing a news key drops citations but not answers; every
external data provider falls back to keyless `yfinance`.

## Features

| Capability | Summary |
|---|---|
| **Professional charting** | A Lightweight-Charts trading workstation: intraday → monthly intervals, 7 chart types (candles, Heikin-Ashi, bar, line, area, baseline, hollow), 15 technical indicators, a canvas **drawing-tools engine** (trend lines, rays, Fibonacci, rectangles, measure, text) with select/move/delete, undo/redo, and per-symbol persistence, **Volume Profile**, and support/resistance + forecast overlays. |
| **AI price forecasting** | The [Kronos](https://github.com/shiyu-coder/Kronos) time-series foundation model forecasts future closes across every interval (daily and intraday); overlaid on the chart by default. A baseline drift model is the always-available fallback. |
| **Multi-agent analysis** | A 7-agent LLM pipeline (technical analyst → news analyst → bull/bear debate → trader → risk manager → portfolio manager) produces a risk-limited recommendation with a fully **explainable** breakdown of the inputs it saw. |
| **Consolidated news intelligence** | News is aggregated across NewsAPI, Finnhub, Yahoo Finance, and Alpha Vantage, normalized to one schema, de-duplicated, merged, and ranked by relevance and recency — then fed to both the agents and the retrieval-augmented chat. |
| **Paper trading** | A simulated portfolio with market / limit / stop / stop-limit orders, average-cost accounting, an equity/drawdown curve, and **human-in-the-loop AI proposals** (the AI proposes; a human accepts or rejects — it never auto-executes). |
| **Portfolio analytics** | Value-at-Risk (historical + parametric), Monte-Carlo simulation, mean-variance optimization, plus a risk / diversification / correlation intelligence digest. |
| **Financial research** | Company profiles, income / balance-sheet / cash-flow statements, and derived QoQ/YoY earnings analysis. |
| **Grounded AI chat** | A retrieval-augmented assistant — a full chat page **and** a site-wide floating dock — grounded in market data, agent decisions, and a persisted news corpus, with numbered citations. |
| **Market coverage** | A curated ~100-instrument Nifty universe, per-user watchlists with search/reorder, and **whole-market lazy loading** — search any NSE/BSE symbol and track it on demand via a durable background backfill queue. |
| **Self-evaluation** | The platform measures its own quality: forecast accuracy (MAPE/bias), agent behaviour, recommendation success, and LLM cost/latency. |

## Architecture

A modular-monolith backend, a Next.js frontend that reaches it only through an
authenticated same-origin proxy, and remote ML inference on a GPU-class Space.

```
Users ─▶ Vercel (Next.js frontend)
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
through an identical API surface, selected by a single environment flag.

## Technology stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 15 (App Router, React 19, TypeScript), Tailwind v4 (CSS-variable design tokens), TanStack Query, TradingView Lightweight Charts, next-themes |
| Backend | FastAPI (async), SQLAlchemy 2 + asyncpg, Pydantic, Alembic, APScheduler, structlog |
| Database | Supabase — Postgres 17 + pgvector, Row-Level Security, Supabase Auth (JWT) |
| ML / AI | Kronos time-series foundation model, sentence-transformers (MiniLM, 384-d), Google Gemini + OpenAI, NautilusTrader (backtesting) |
| Infra | Vercel (frontend), Render (backend, Docker), Hugging Face Spaces (ZeroGPU inference), GitHub Actions (CI + keep-alive) |

## AI architecture

FinIntel's intelligence is a pipeline of specialized LLM agents inspired by the
TradingAgents pattern. For a given instrument the orchestrator first gathers a
deterministic context — price summary, technical indicators, a Kronos forecast,
backtest evidence, consolidated news, and relevant memory of past conclusions —
then runs the agents in sequence:

1. **Technical analyst** — reads indicators, trend, and the forecast.
2. **News analyst** — reads the consolidated multi-source news feed.
3. **Bull vs. bear researchers** — a structured multi-round debate.
4. **Trader** — proposes a concrete BUY / SELL / HOLD stance.
5. **Risk manager** — applies coded hard limits on top of its judgement.
6. **Portfolio manager** — issues the final risk-adjusted recommendation.

Each step is persisted as it completes, so even a failed run leaves a usable
transcript, and an **explainability** view exposes exactly which inputs the
agents saw. LLM calls fail over automatically between providers, and a
pgvector-backed **agent memory** recalls similar past conclusions for the same
symbol (strictly symbol-scoped — no cross-instrument contamination).

## News intelligence

News is a first-class, multi-provider pipeline rather than a single feed:

- **Providers.** NewsAPI and Yahoo Finance are queried by company name;
  Finnhub and Alpha Vantage (NEWS_SENTIMENT) by ticker. Each provider is
  best-effort and degrades to empty independently, so one outage or an exhausted
  quota never sinks the rest.
- **Normalization.** Every source is mapped to one common schema (title, source,
  timestamp, description, URL), preserving publisher attribution.
- **De-duplication & merge.** Overlapping stories reported by multiple providers
  are merged by normalized title, keeping the richest copy and recording every
  contributing source.
- **Ranking.** The consolidated set is ranked by query/ticker **relevance** and
  then **recency** within the look-back window.
- **Consumption.** The ranked corpus feeds both the agent news analyst and the
  retrieval-augmented chat, and is embedded into a pgvector store so chat
  citations grow with every analysis run.

## Forecasting

Price forecasts come from **Kronos**, an open time-series foundation model,
served through a forecaster registry with an identical local/remote API. In
production the model runs remotely on a Hugging Face Space (CPU inference); for
local development it runs in-process with torch. Forecasts are available on every
interval, daily through intraday, and are overlaid on the chart by default. A
lightweight **baseline drift model** is always available as a fallback, and
forecast quality is tracked over time (MAPE / directional bias) by the
self-evaluation subsystem.

## Paper trading

The simulation engine mirrors a real trading workflow without any broker
connection:

- Market, limit, stop, and stop-limit order types, with resting orders swept by
  a scheduled job.
- Average-cost position accounting, realized/unrealized P&L, and an
  equity/drawdown curve.
- **Human-in-the-loop AI proposals** — an agent run can propose an order, but a
  human must explicitly accept or reject it; nothing auto-executes.

## Portfolio analytics

A numpy-only analytics layer (no heavyweight dependencies) computes:

- **Value-at-Risk** — historical and parametric, over a configurable horizon.
- **Monte-Carlo simulation** — a distribution of projected portfolio outcomes.
- **Allocation optimizer** — mean-variance efficient-frontier weights.
- **Intelligence digest** — concentration, diversification, and correlation
  signals in plain language.

## Authentication

- **Supabase Auth** issues JWTs; the backend verifies them on every business
  route (local HS256 or remote validation with caching).
- A static **`X-API-Key`** grants a service context for automation and scheduled
  jobs.
- A **guest account** enables a no-signup demo. Every guest session starts from a
  clean workspace, and per-user ownership isolation applies to guests exactly as
  to registered users.
- **Row-Level Security** is enabled deny-by-default on every table, so the
  auto-generated REST surface is fully locked; all access is mediated by the
  backend, which enforces ownership in application code.

## Installation

**Requirements:** Python 3.12+, Node 20+, and a Postgres 15+ / Supabase database.

```bash
git clone https://github.com/Eklavya-Singh-Rathore/AI-Financial-Intelligence-Trading-Simulation-Platform.git
cd AI-Financial-Intelligence-Trading-Simulation-Platform
cp .env.example .env      # then fill in DATABASE_URL and the keys you have
```

### Backend

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate      # Windows; use bin/activate on Unix
pip install -e ".[dev,local-ml]"                     # local-ml = torch + MiniLM for in-process inference
alembic upgrade head                                 # apply the migration chain
uvicorn app.main:app --reload                        # Swagger UI at http://localhost:8000/docs
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local                           # BACKEND_URL + Supabase public keys
npm run dev                                           # http://localhost:3000
```

## Environment variables

All configuration comes from environment variables; `.env` is git-ignored and
every value is treated as a secret. Copy `.env.example` and fill in what you
have — the app boots with partial configuration and degrades explicitly.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres / Supabase connection string (async `postgresql+asyncpg://…`). |
| `SUPABASE_JWT_SECRET` / `SUPABASE_URL` | Auth token verification. |
| `BACKEND_API_KEY` | Service-context key for the frontend proxy and automation. |
| `GOOGLE_AI_STUDIO_API_KEY` / `OPENAI_API_KEY` | Agent + chat LLMs (with failover). |
| `NEWSAPI_KEY` / `FINNHUB_API_KEY` / `ALPHA_VANTAGE_API_KEY` | News + market-data providers. |
| `KRONOS_MODE` / `EMBEDDINGS_MODE` | `local` (in-process torch) or `remote` (Hugging Face Space). |
| `GUEST_EMAIL` / `GUEST_PASSWORD` | Credentials for the shared guest demo account (server-only). |

See [`docs/environment.md`](docs/environment.md) for the complete reference —
every variable, where it is set, and whether it is a secret.

## Local development

- API calls go through the authenticated same-origin proxy at
  `app/api/backend/[...path]`, so the backend API key and service credentials
  never reach the browser.
- The backend can run entirely local ML (`KRONOS_MODE=local`,
  `EMBEDDINGS_MODE=local`) with the `local-ml` extra installed, or point at the
  remote Space with `remote`.
- Database migrations are managed with Alembic (`alembic upgrade head` /
  `alembic revision --autogenerate`).

## Deployment

| Component | Platform | Notes |
|---|---|---|
| Frontend | Vercel | Auto-deploys on push to `main`; root directory `frontend`. |
| Backend | Render (Docker) | Slim, torch-free production image; deploy via the Render dashboard or API. |
| ML inference | Hugging Face Space | Kronos + MiniLM, CPU/ZeroGPU; kept byte-identical to the backend's vendored source. |
| Database | Supabase | Postgres 17 + pgvector; migrations applied with Alembic. |

Deployment runbooks live in [`docs/deploy-render.md`](docs/deploy-render.md) and
[`docs/deploy-hf-space.md`](docs/deploy-hf-space.md).

## Project structure

```
backend/            FastAPI application
  app/
    api/routers/    HTTP endpoints (instruments, agents, chat, simulation, market, watchlists, guest, admin, …)
    services/       business logic (market data, OHLCV resolver, agents, simulation, analytics, research, RAG)
    ml/             Forecaster interface + Kronos (local & remote) + baseline; vendored kronos_src (MIT)
    backtesting/    Backtester interface + NautilusTrader / simple engines
    llm/            LLM client + Gemini/OpenAI failover
    agents/         7-agent orchestrator, prompts, risk limits, explainability
    providers/      capability-based external-data abstraction (yfinance, Finnhub, Alpha Vantage, NewsAPI)
    catalog/        curated instrument universe
    models/ db/     SQLAlchemy ORM + async engine
  alembic/          database migrations
  tests/            unit + database-integration suites
frontend/           Next.js app
  app/              routes (dashboard, instrument detail, portfolio, simulation, agents, insights, chat, login)
  components/        UI primitive library, charting (chart/), simulation, assistant dock, command palette
  lib/              typed API client + pure logic (indicators, chart math, drawings) with node:test coverage
docs/               MASTER_ARCHITECTURE, per-area architecture, ADRs, deployment runbooks, environment reference
infrastructure/     Docker Compose, the Hugging Face inference Space
```

## API overview

The backend is a REST API documented by an interactive OpenAPI/Swagger UI at
`/docs`. Business routes require a Supabase JWT (or the service `X-API-Key`);
health probes are open. Representative groups:

| Area | Endpoints |
|---|---|
| Instruments & charting | `/instruments/summary`, `/instruments/{symbol}/prices`, `/indicators`, `/forecast` |
| Agents | `POST /agents/run`, `/agents/runs/{id}`, `/agents/runs/{id}/explanation` |
| Simulation | `/simulation/portfolio`, `/simulation/orders`, `/simulation/analytics/{risk,montecarlo,optimization}` |
| Watchlists | `/watchlists`, `/watchlists/{id}/items`, `/watchlists/{id}/order` |
| Chat | `/chat/sessions`, `/chat/sessions/{id}/messages` |
| Market | `/market/search`, `/market/track` |

The frontend never calls these directly — it uses the same-origin proxy at
`/api/backend/*`, which attaches the caller's JWT server-side.

## Testing

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
torch-free production image), plus a drift check keeping the vendored Kronos
source byte-identical between the backend and the inference Space.

## Security

- **Authentication & authorization.** JWT-verified routes, a `service > admin >
  user` role hierarchy, and per-user ownership on every workspace table (chat,
  agent runs, backtests, forecasts, portfolios, watchlists); cross-user access
  returns `404`.
- **Row-Level Security.** Enabled deny-by-default on every table; the public REST
  surface is locked and all access flows through the backend.
- **Secret hygiene.** All credentials are environment-provided; the frontend
  proxy keeps the backend key and service credentials off the browser; `.env` is
  git-ignored.
- **Guest isolation.** The shared guest workspace is reset on entry, so no
  session ever sees another's data.

## Roadmap

- Options and derivatives analytics.
- Additional exchanges and asset classes beyond the Indian equity universe.
- Richer agent tooling (scenario analysis, portfolio-level agent runs).
- Expanded self-evaluation dashboards and backtested strategy libraries.
- Mobile-optimized layouts for the charting workstation.

## Contributing

1. Fork and branch from `main`.
2. Make focused changes with tests.
3. Ensure all gates pass — backend `ruff` / `mypy` / `pytest`, frontend
   `typecheck` / `test` / `build`.
4. Open a pull request describing the change and its rationale.

## License

Released under the **MIT License** — see [`LICENSE`](LICENSE). The vendored
Kronos model source (`backend/app/ml/kronos_src/`) is distributed under its own
MIT license; see that directory's `LICENSE`.

## Acknowledgements

- [Kronos](https://github.com/shiyu-coder/Kronos) — time-series foundation model.
- [NautilusTrader](https://nautilustrader.io/) — event-driven backtesting engine.
- The TradingAgents research pattern — inspiration for the multi-agent pipeline.
- [Supabase](https://supabase.com/), [Vercel](https://vercel.com/),
  [Render](https://render.com/), and [Hugging Face](https://huggingface.co/) —
  the hosting and data platform.
- `yfinance`, NewsAPI, Finnhub, and Alpha Vantage — market data and news.

---

## Disclaimer

FinIntel is for **education, research, and simulation only**. It does not execute
real trades, does not connect to a broker, and does not provide financial
advice. Forecasts and AI recommendations are experimental and may be wrong. Do
your own research.
