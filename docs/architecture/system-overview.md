# System Overview

**AI Financial Intelligence Trading Simulation Platform** — a multi-user
decision-support system (NO real trading) for the Indian market: a **curated
Nifty-100 universe** (~100 instruments) that **lazy-loads the rest of NSE/BSE on
demand** (India-only, ~300-instrument cap). It ingests daily OHLCV, computes
technical indicators, forecasts prices with the vendored **Kronos** foundation
model, backtests strategies on **NautilusTrader**, runs a **7-agent LLM
pipeline** producing risk-limited recommendations, **explains** them, lets users
**paper-trade** them (human-in-the-loop) with **portfolio analytics**
(VaR/Monte-Carlo/optimization), serves company **research** (profiles/financials/
earnings), grounds chat (full page + a site-wide floating dock) in market data +
persisted **news with citations**, and **evaluates** its own AI quality. Phase 6
adds a **professional UI** and **external data providers** (Finnhub + Alpha
Vantage). Single-document reference:
[../MASTER_ARCHITECTURE.md](../MASTER_ARCHITECTURE.md).

## Components

| Component | Tech | Responsibility |
|---|---|---|
| Frontend | Next.js 15 (App Router, TS), Tailwind v4 design tokens + `components/ui/*`, TanStack Query, lightweight-charts | Watchlist-aware dashboard, instrument detail (professional `TradingChart` + forecast + backtest + research), Portfolio analytics, simulation, agent transcripts + explanations, insights, chat with citations, site-wide floating assistant, Cmd/Ctrl-K command palette; auth UI; same-origin authenticated proxy to the backend |
| Backend | FastAPI (async), SQLAlchemy 2 + asyncpg, APScheduler | REST APIs, auth/RBAC, forecasting/backtesting orchestration, agent pipeline + explainability, paper-trading engine, portfolio analytics, financial research, news RAG, AI evaluation, catalog sync + whole-market lazy load (durable `ingest_jobs` queue), external-data providers, scheduler |
| Inference | Hugging Face Space (Gradio/ZeroGPU), official Kronos + MiniLM | `POST /forecast`, `POST /embed`, `GET /health` — CPU inference so the backend image ships without torch |
| Database | Supabase Postgres 17 + pgvector | Market data, forecasts/backtests/agent runs/chat (per-user owned), 384-d embeddings |
| Auth | Supabase Auth (email+password, open sign-up, guest) | JWT issuance; backend verifies JWTs (local HS256 or remote) |
| LLM | Gemini (primary) → OpenAI (fallback) → fake (tests) | Agent reasoning + grounded chat |

## Production topology

```
Users ─▶ Vercel (frontend, same-origin proxy /api/backend/*, maxDuration=300)
            │  Supabase Bearer JWT forwarded server-side
            ▼
        Render free web service (slim FastAPI image — no torch)
        auth · agents · RAG · chat · NautilusTrader · APScheduler
          ├─▶ Supabase (Postgres + pgvector, Auth)
          ├─▶ Gemini / OpenAI            ├─▶ NewsAPI / yfinance
          └─▶ HF Space "ai-inference-service" (Kronos + MiniLM)
GitHub Actions cron (*/10) pings /live so Render never sleeps;
the backend scheduler pings the Space /health every 6 h.
```

Detail: [deployment.md](deployment.md).

## Request → data flow (example: a forecast)

1. Browser calls same-origin `/api/backend/instruments/RELIANCE/forecast?model=kronos`.
2. The Next.js proxy route attaches the user's Supabase Bearer JWT and forwards
   to the Render backend.
3. `get_auth` validates the JWT → an `AuthContext` (role `user`, the caller's `user_id`).
4. `forecast_service` loads OHLCV from Postgres into a DataFrame, selects the
   `kronos` forecaster from the registry (remote in production).
5. `RemoteKronosForecaster` POSTs the context window to the HF Space `/forecast`;
   the Space runs official Kronos on CPU and returns close-price predictions.
6. The result is optionally persisted (`forecasts`, owned by `user_id`) and
   returned; the chart overlays it.

The same shape applies to backtests (NautilusTrader in-process), agent runs
(async 7-agent pipeline), and chat (RAG-grounded LLM). See
[backend.md](backend.md), [ai-agents.md](ai-agents.md), [database.md](database.md).

## Key design decisions (ADRs)

- [ADR-0001](../adr/ADR-0001-architecture.md) — modular monolith
- [ADR-0002](../adr/ADR-0002-authentication.md) — Supabase Auth + JWT + API key
- [ADR-0003](../adr/ADR-0003-agent-orchestrator.md) — in-process agent pipeline with coded risk limits
- [ADR-0004](../adr/ADR-0004-deployment.md) — Vercel + Render + HF Space + Supabase
- [ADR-0005](../adr/ADR-0005-ai-inference.md) — remote inference via a Hugging Face Space
- [ADR-0006](../adr/ADR-0006-paper-trading.md) — paper-trading semantics & human-in-the-loop AI

## Non-goals

Real trading/order execution; notifications (permanently out of scope);
document uploads for RAG (news-only corpus, owner decision); multi-tenant RLS
policies (all data access is mediated by the backend, which enforces ownership
in application code). Deferred in Phase 6 (abstractions ready): streaming
assistant responses; Reddit/Twitter-X sentiment + OpenBB providers; correlated
Monte-Carlo; the official TradingView Charting Library. (The durable job queue,
formerly future work, shipped in Phase 6 as `ingest_jobs`.)
