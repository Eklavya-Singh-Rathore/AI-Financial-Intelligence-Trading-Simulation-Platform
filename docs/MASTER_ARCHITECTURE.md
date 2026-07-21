# Master Architecture

**AI Financial Intelligence Trading Simulation Platform** — the complete
system reference as of Phase 6.5. One document, top to bottom; per-area deep
dives live in [`docs/architecture/`](architecture/) and decisions in
[`docs/adr/`](adr/).

A multi-user **decision-support** system (NO real trading) for the Indian
market: a **curated Nifty-100 universe** (~100 instruments) that **lazy-loads
the rest of the NSE/BSE market on demand** (India-only, ~300-instrument cap).
It ingests daily OHLCV, computes indicators, forecasts prices with the vendored
**Kronos** foundation model, backtests on **NautilusTrader**, runs a **7-agent
LLM pipeline** producing risk-limited recommendations, explains those
recommendations, lets users **paper-trade** them (human-in-the-loop, never
auto-executed), computes **portfolio analytics** (VaR / Monte-Carlo /
optimization), grounds a chat assistant (full page + a site-wide floating dock)
in market data + persisted news with citations, and measures its own AI
quality. Phase 6 brings a **professional UI redesign** (design tokens +
component library, TradingView-grade charting) and **external data providers**
(Finnhub + Alpha Vantage behind a capability abstraction). **Phase 6.5** turns
the chart into a trading workstation: intraday intervals (yfinance, on-demand),
7 chart types, 15 indicators + Volume Profile, a canvas drawing-tools engine
(trend/ray/rectangle/fib/measure/text + persistence), a chart-docked order
ticket (incl. stop-limit), and support/resistance + AI-recommendation overlays.

## 1. Production topology

```
Users ─▶ Vercel (Next.js 15 frontend; same-origin proxy /api/backend/*)
            │  Supabase Bearer JWT forwarded server-side; maxDuration=300
            ▼
        Render free web service (slim FastAPI image - no torch)
        auth · agents · paper trading · research · RAG · chat · evaluation
        NautilusTrader · APScheduler
          ├─▶ Supabase (Postgres 17 + pgvector, Auth)
          ├─▶ Gemini / OpenAI (LLM, failover)
          ├─▶ NewsAPI · yfinance (headlines · OHLCV + fundamentals)
          └─▶ HF Space "ai-inference-service" (Kronos forecasts + MiniLM embeddings)
GitHub Actions cron (*/10 min) pings /live so Render never sleeps;
the backend scheduler pings the Space /health every 6 h.
```

| Surface | Where | Live URL |
|---|---|---|
| Frontend | Vercel `ai-financial-intelligence-platform` | `https://ai-financial-intelligence-platf-eklavya-singh-rathores-projects.vercel.app` |
| Backend | Render `srv-d995r0faqgkc73fpjfsg` (Singapore) | `https://stock-ai-backend-gv17.onrender.com` |
| Inference | HF Space `Eklavya73/ai-inference-service` (private, ZeroGPU, CPU-only) | `https://eklavya73-ai-inference-service.hf.space` |
| DB/Auth | Supabase `ai-stock-prediction` (`rekoawsoghrjcimknkfz`, ap-south-1) | — |

Render↔Supabase uses the **aws-1 pooler URL** (Render egress is IPv4-only;
direct DB hosts are IPv6-only). Runbooks: [deploy-render.md](deploy-render.md),
[deploy-hf-space.md](deploy-hf-space.md).

## 2. Backend layering

```
api/routers ─▶ services ─▶ (ml | backtesting | llm | agents) ─▶ models / db
```

Routers stay thin; business logic lives in `services`; CPU-bound work runs off
the event loop via `asyncio.to_thread`; implementation choices (forecaster,
backtester, LLM) come from **registries** so switching is a config change.

| Package | Contents |
|---|---|
| `app/api/routers/` | `health`, `instruments` (prices/indicators/forecast/**profile/financials/earnings**), `ingest`, `backtest`, `agents` (+**explanation**), `chat`, **`simulation`**, **`evaluation`** |
| `app/services/` | `market_data`, `data_ingest`, `indicators`, `forecast_service`, `backtest_service`, `news`, `embeddings`, `space_client`, `chat_service`, **`simulation`**, **`research`**, **`news_rag`**, **`evaluation`** |
| `app/ml/` | `Forecaster` + registry; `baseline`, `kronos` (local torch), `remote_kronos` (HF Space); vendored `kronos_src/` (MIT) |
| `app/backtesting/` | `Backtester` + registry; NautilusTrader + simple vectorized engine |
| `app/llm/` | `LLMClient` + failover registry; Gemini / OpenAI / fake |
| `app/agents/` | 7-agent orchestrator, prompts, coded risk limits, **`explain.py`** |
| `app/scheduler/` | APScheduler jobs: daily ingest, **sim order sweep**, **news ingest**, Space keep-warm |

## 3. Feature architecture

### 3.1 Market data & indicators (Phase 1)

yfinance → `price_bars` (idempotent upserts), daily scheduler refresh, and a
pandas indicator engine (`sma`, `ema`, `rsi`, `macd`, `bollinger`) computed
on demand.

### 3.2 Forecasting (Phases 1–4.5, intraday in 6.1)

`GET /instruments/{s}/forecast?model=kronos|baseline&horizon=1..60&interval=1D`.
The registry maps `kronos` to in-process torch (`KRONOS_MODE=local`, dev) or the
HF Space (`remote`, production) — same public name, same persisted
`model_name`. Failures normalize to `ForecasterError` → HTTP 503; agent runs
fall back to `baseline`. Forecasts persist per point (`forecasts` table) with
owner stamping. Kronos is the default forecaster (`DEFAULT_FORECASTER=kronos`)
and, as of Phase 6, is shown by default on the instrument chart.

**Intraday forecasting (Phase 6.1).** The service is interval-aware: it sources
bars through the `ohlcv` resolver (daily `price_bars`; 1m–1H on-demand yfinance)
and generates interval-correct future timestamps — business days for daily,
session-aware NSE steps (09:15–15:30 IST, weekends skipped) for intraday, the
resample anchor for weekly/monthly. Those timestamps are passed into the
forecaster (`resolve_target_timestamps`) so Kronos sees the right temporal
context — Kronos is a candlestick model and forecasts any grain. Persistence
gained `interval` + `target_ts` columns (migration `0017`); intraday/weekly/
monthly rows are excluded from the daily accuracy metric (`interval='1D'`
filter in evaluation). The instrument-page overlay now renders on every interval
(the chart maps `target_time` for intraday, `target_date` otherwise); the UI
requests `persist=false` for display, the same as daily.

#### Kronos model audit (Phase 6)

The platform uses the **official Kronos** foundation model (github.com/shiyu-coder/Kronos,
MIT), vendored at `backend/app/ml/kronos_src/` for local inference and mirrored
byte-identically at `infrastructure/hf-space/kronos_src/` for the Space (a CI
`diff -r` drift check enforces this). The vendored `Kronos`/`KronosTokenizer`
are generic `PyTorchModelHubMixin` classes — every hyperparameter (d_model,
layers, heads, context) comes from the loaded Hub checkpoint's config, so the
**deployed variant is entirely determined by the configured model id**, not by
code.

| Variant | Params | Context | Deployed? |
|---|---|---|---|
| Kronos-mini | ~4.1M | 2048 | no |
| **Kronos-small** | **~24.7M** | **512** | **yes — production (remote Space)** |
| **Kronos-base** | **~102.3M** | **512** | **yes — local dev (in-process, Phase 6.1)** |

**Variant selection (Phase 6.1).** Model choice is a data lookup in
`app/ml/kronos_variants.py` (`KRONOS_VARIANTS`: mini/small/base — the only
published NeoQuasar checkpoints; "tiny"/"large" belong to a different model
family and are intentionally absent). `KRONOS_VARIANT` picks one; empty =
**automatic by `ENV`** — `base` for local development (a dev box has the RAM),
`small` in production (the free-tier inference budget). `resolve_kronos_config`
lets the low-level `KRONOS_MODEL_ID`/`KRONOS_TOKENIZER_ID`/`KRONOS_MAX_CONTEXT`
still override per-field for back-compat. `/health` echoes the resolved ids +
`kronos_variant`. `KRONOS_DEVICE=cpu`; production runs `KRONOS_MODE=remote`
(Render slim image ships without torch), so the HF Space (still Kronos-small,
its own `app.py` config) serves inference — local dev on base and prod on small
need no Space change.

**Live verification.** Backend `GET /health` reports the configured ids
(`kronos_model_id`, `kronos_tokenizer_id`, `kronos_max_context`,
`default_forecaster`) and, in remote mode, a `remote_inference` block echoing
what the Space last reported loaded (populated from the 6-hourly keepalive
ping's cached `/health` — never a blocking request). Cross-check directly
against the Space's own `GET /health` (`kronos_model_id`, `embedding_model_id`,
`device`, `app_version`). A forecast response's `meta.model_id` is a third
confirmation. Embeddings use `all-MiniLM-L6-v2` (384-d), same local/remote split.

### 3.3 Backtesting (Phase 1)

`POST /backtest` — SMA-crossover on NautilusTrader (or the `simple` vectorized
engine), returning total return, Sharpe, max drawdown, win rate, volatility,
fills; persisted with the caller's `user_id`.

### 3.4 Multi-agent pipeline (Phase 2) + Explainability (Phase 5)

`POST /agents/run` (202, fire-and-poll): gather (prices, indicators, forecast,
backtest, news, memory) → technical analyst → news analyst → bull/bear debate
→ trader → risk manager (coded hard limits: `MAX_POSITION_PCT`, drawdown veto)
→ portfolio manager. Every step persists an `agent_messages` row with
structured JSON.

**Phase 5:** the gather-time inputs are persisted on the run
(`agent_runs.context_snapshot`) so `GET /agents/runs/{id}/explanation` can
compose a faithful, deterministic explanation — why (decision summary, trader
rationale, risk rationale), stances, sentiment, debate points, risk concerns,
and the indicators/forecast/backtest **as the agents saw them** — with zero
LLM calls. Pre-snapshot runs degrade to message-derived sections.

### 3.5 Paper trading simulation (Phase 5)

Engine: `app/services/simulation.py`; API: `/simulation/*`; UI: `/simulation`.

- One portfolio per owner (unique index incl. NULL service owner), starting
  cash `SIM_STARTING_CASH` (default ₹10,00,000).
- **Daily-bar execution semantics** (the platform is daily-bar): market orders
  fill at the latest close; limit/stop orders rest and are evaluated against
  each new bar (buy limit fills at `min(open, limit)` when `low <= limit`,
  etc.). Resting orders are swept lazily on portfolio reads and by a daily
  scheduler job after ingest.
- **Average-cost accounting**; realized P&L on sells; cash/share sufficiency
  enforced (rejected orders roll back).
- **Equity curve reconstructed on demand** from trades + close-price series
  (no snapshot table to drift); performance metrics: total return, CAGR,
  Sharpe, Sortino, volatility, max drawdown, win rate + **AI-vs-manual**
  split.
- **AI proposals are human-in-the-loop by design**: "Send to Simulation" on a
  completed run creates a `proposed` order sized from the final decision
  (`size_pct` × equity, SELL capped at held qty); the human must accept
  (fills) or reject. Nothing auto-executes. HOLD/veto/zero-size decisions are
  not proposable.
- Portfolio intelligence (`GET /simulation/intelligence`): risk score, sector
  exposure, HHI/effective positions, concentration flags, correlation matrix,
  rebalancing suggestions.

See [ADR-0006](adr/ADR-0006-paper-trading.md).

### 3.6 Financial research (Phase 5)

`app/services/research.py` fetches yfinance fundamentals (`Ticker.info`,
income/balance/cashflow statements) in a worker thread, serializes them to
plain JSON, and caches them in `instrument_fundamentals` with a TTL
(`FUNDAMENTALS_TTL_HOURS`). Failures degrade: fresh cache → stale cache →
DB-only profile (instruments + sectors/industries tables) — never an error.
Earnings analysis (QoQ/YoY revenue & net-income growth) is **derived** from
the quarterly income statement. Endpoints:
`GET /instruments/{s}/profile | /financials | /earnings`; UI: the Research
section on the instrument page.

### 3.7 News RAG & grounded chat (Phases 3 + 5)

Chat (`/chat/*`) grounds each answer deterministically: detected symbols →
live market stats; recent agent decisions; semantic memory
(`agent_embeddings`, MiniLM 384-d, cosine KNN); conversation history; and
(Phase 5) **retrieved news with numbered citations**. Headlines are persisted
into `research_documents` (content-hash dedupe, embedded, `doc_type='news'`)
two ways: opportunistically on every agent run, and by a daily
`news_ingest` scheduler job (gated by `ENABLE_NEWS_INGEST`, retention
`NEWS_RETENTION_DAYS`). The model is instructed to cite `[n]`; citations
(title/url/date) persist in the message context and render as links in the
chat UI. All retrieved content renders inside the `<untrusted-data>` prompt
boundary.

### 3.8 AI evaluation (Phase 5)

`GET /evaluation/summary` — deterministic quality/cost metrics over persisted
data: **forecast accuracy** (MAPE + signed bias per model over matured
forecast points joined to actual closes), **agent stats** (status counts,
action mix, average confidence, technical-vs-news stance agreement),
**recommendation success** (directional return of completed BUY/SELL runs
from snapshot entry price vs latest close), and **usage & cost** (token
totals, estimated USD via `LLM_COST_INPUT_PER_1M`/`LLM_COST_OUTPUT_PER_1M`,
run wall time, per-step latency). UI: `/insights`.

### 3.9 Market expansion & catalog (Phase 6)

The universe grows in three tiers. **Curated catalog** — `app/catalog/curated.py`
holds a `CatalogEntry` tuple (~100 Nifty-100 names); `POST /admin/catalog/sync`
(privileged) idempotently creates any missing instruments + provider mappings
(per-entry commit under advisory lock `815005`; never mutates existing rows) and
`GET /admin/catalog` previews the plan. **Watchlists** — per-user lists
(`/watchlists` CRUD) surfaced as dashboard tabs and star toggles. **Whole-market
lazy load** — `GET /market/search` finds any NSE/BSE symbol; `POST /market/track`
normalizes it, inserts the instrument, and enqueues an `ingest_jobs` row;
`GET /market/track/{symbol}/status` reports progress. The durable queue survives
restarts and is drained both opportunistically (BackgroundTasks) and by a
5-minute scheduler tick (lock `815004`). `MAX_TRACKED_INSTRUMENTS` (default 300)
caps total instruments. `GET /instruments/summary` is paginated/searchable
(`q`, `types`, `watchlist_id`, `limit`, `offset`) returning `{items, total}`.

### 3.10 External data providers (Phase 6)

`app/providers/` — a capability-based abstraction. `BaseProvider` declares a
`frozenset[Capability]` and never-raising methods (`search_symbols`,
`get_quote`, `fetch_news`, `fetch_fundamentals`); `registry.py` orders providers
by `PROVIDER_PRIORITY` and tries them left-to-right per capability. Providers:
keyless **yfinance** (always the baseline), **Finnhub**, **Alpha Vantage**
(daily-cap guarded). Every provider degrades to empty when its key is absent, so
the platform runs fully keyless. News ingest is quota-guarded
(`NEWS_INGEST_DAILY_CAP`): held/watched symbols first, then the rest rotated by
day index.

### 3.11 Portfolio analytics (Phase 6)

`app/services/portfolio_analytics.py` — **numpy-only** (no scipy) quantitative
finance over the paper portfolio's holdings and stored daily bars:
**historical + parametric Value-at-Risk** (inverse-normal via Acklam's rational
approximation), **Monte-Carlo GBM** simulation (`np.random.default_rng`), and
**long-only mean-variance optimization** (Dirichlet-sampled efficient frontier,
avoiding a QP-solver dependency). Exposed at
`GET /simulation/analytics/{risk,montecarlo,optimization}`; UI: `/portfolio`.

### 3.12 UI system & floating assistant (Phase 6)

A design-token system (Tailwind v4 CSS vars, the 9 original brand colors
preserved) + a hand-built primitive library (`components/ui/*`). A professional
`TradingChart` (persisted lightweight-charts instance, MA overlays, forecast
band, trade markers) replaces the prior rebuild-on-every-render chart. A
**site-wide floating assistant** (`components/assistant/AssistantDock.tsx`) talks
to a dedicated chat session (persisted in localStorage, validated against the
server); on an instrument page it prefixes messages with `[viewing SYMBOL]` so
the existing chat RAG grounds the answer — no backend change. A Cmd/Ctrl-K
**command palette** searches the universe and tracks new symbols.

## 4. Database

Supabase Postgres 17 + pgvector; async SQLAlchemy 2 + asyncpg. Alembic head:
**`0017_intraday_forecasts`**. RLS is enabled deny-by-default on every public table
(locks the auto-generated REST API); the backend connects as `postgres` and
enforces ownership in application code.

| Group | Tables |
|---|---|
| Market data (adopted) | `instruments` (curated Nifty-100 + on-demand, + `sector_id`/`industry_id`), `price_bars`, `data_providers`, `instrument_provider_mappings`, `exchanges`, warehouse tables |
| AI core (owned) | `forecasts` (+`interval`/`target_ts`, Phase 6.1), `backtests`, `agent_runs` (+`context_snapshot`), `agent_messages`, `chat_sessions`, `chat_messages`, `agent_embeddings` (vector 384) |
| Paper trading (owned, Phase 5) | `sim_portfolios`, `sim_orders`, `sim_trades`, `sim_positions` |
| Research (owned, Phase 5) | `instrument_fundamentals` (JSONB cache), `research_documents` (news corpus, vector 384) |
| Market expansion (owned, Phase 6) | `watchlists`, `watchlist_items` (`0014`), `ingest_jobs` durable queue (`0015`) |

Migration chain: `0004_warehouse` → … → **`0011_simulation`** →
**`0012_research`** → **`0013_run_context`** → **`0014_watchlists`** →
**`0016_stop_limit`** → **`0017_intraday_forecasts`** (adds `forecasts.interval`
+ `forecasts.target_ts`). Applied manually (`alembic upgrade head`); CI proves
the full chain on vanilla Postgres (`pgvector/pgvector:pg17`).

## 5. Auth & multi-user isolation

- **Users:** Supabase Auth (email+password, open sign-up); cookie sessions
  via `@supabase/ssr`; `middleware.ts` guards all routes except `api/backend`
  and `api/guest`. **Guest:** server-side `/api/guest` signs in a dedicated
  pre-provisioned account (server-only credentials, normal `user` role, no
  bypass).
- **Backend:** `X-API-Key` → `service`; `Bearer <jwt>` verified locally
  (HS256) or remotely with a 60 s cache. Roles: `service` > `admin` > `user`.
- **Ownership:** `user_id` on chat sessions, agent runs, backtests, forecasts,
  and sim portfolios/orders/trades. Non-privileged reads are owner-filtered;
  cross-user access → `404`. News documents are deliberately a shared corpus
  (public headlines).

## 6. Scheduler

APScheduler in-process (single-flight via Postgres advisory locks):

| Job | When | Lock key |
|---|---|---|
| `daily_ingest` | `DAILY_INGEST_HOUR:MINUTE` UTC | 815001 |
| `sim_order_sweep` | ingest + 15 min | 815002 |
| `news_ingest` | ingest + 30 min (if `ENABLE_NEWS_INGEST`; quota-guarded by `NEWS_INGEST_DAILY_CAP`) | 815003 |
| `ingest_job_drain` (Phase 6) | every 5 min | 815004 |
| `space_keepalive` | every 6 h (remote inference only) | — |

Advisory-lock `815005` guards `POST /admin/catalog/sync` (held across per-entry
commits, not transaction-scoped). Whole-market tracking also drains its queue
opportunistically via `BackgroundTasks` on each `POST /market/track`.

## 7. Frontend

Next.js 15 App Router + TypeScript, Tailwind v4, TanStack Query,
lightweight-charts v5. All backend access goes through the authenticated
same-origin proxy `app/api/backend/[...path]` (attaches the Supabase JWT
server-side; forwards `204/304` with a null body). **Phase 6 redesign**: a
CSS-var design-token system + hand-built `components/ui/*` primitives (Card,
Stat, Table, Badge, Button, Input, Sheet, EmptyState, Skeleton…), a responsive
shell with a mobile drawer, a persisted-instance `TradingChart`, a Cmd/Ctrl-K
command palette, and a site-wide floating `AssistantDock`. Pages: Dashboard
(watchlist-aware universe table), Instrument detail (chart + forecast overlay +
backtest + **Research** + watchlist star), **Portfolio** (VaR / Monte-Carlo /
optimization), **Simulation** (portfolio, order ticket, proposals
accept/reject, performance charts, intelligence), Agents + run detail
(**explanation panel**, **Send to Simulation**), **Insights** (evaluation),
Chat (**news citations**), Login (+ guest).

## 8. Configuration

`.env`-driven pydantic settings; full reference in
[environment.md](environment.md). Phase 5 additions: `SIM_STARTING_CASH`,
`FUNDAMENTALS_TTL_HOURS`, `ENABLE_NEWS_INGEST`, `NEWS_RAG_TOP_K`,
`NEWS_RETENTION_DAYS`, `LLM_COST_INPUT_PER_1M`, `LLM_COST_OUTPUT_PER_1M`.
Phase 6 additions: `FINNHUB_API_KEY`, `ALPHA_VANTAGE_API_KEY` (secrets),
`ALPHA_VANTAGE_DAILY_CAP`, `PROVIDER_PRIORITY`, `MAX_TRACKED_INSTRUMENTS`,
`NEWS_INGEST_DAILY_CAP`, `INGEST_PAUSE_SECONDS`. All have safe defaults (the
providers degrade to keyless yfinance), so no deploy-time action is required
beyond setting the two provider secrets if those integrations are wanted.
Phase 6.1: `KRONOS_VARIANT` (empty = auto: base for dev, small for prod) and
`GEMINI_MODEL` now defaults to the stable `gemini-flash-latest` alias (pinned
Gemini versions get retired for new API keys and then 404).

## 9. Testing & CI

- Fast suite: `pytest -m "not slow and not db"` — pure logic incl. the
  simulation engine (execution semantics, accounting, metrics), research
  serialization/earnings math, news-RAG transforms, explanation composition,
  evaluation math.
- Integration (db-marked): real Postgres round-trips — order lifecycle,
  ownership isolation, proposal accept flow, news ingest/dedupe/KNN.
- Frontend: `tsc --noEmit`, `node:test` suite, `next build`.
- CI jobs: backend (ruff/mypy/bandit/pytest + kronos_src drift check),
  integration (pgvector Postgres + full migration chain + db tests),
  frontend, docker (full + slim images).

## 10. ADR index

| ADR | Decision |
|---|---|
| [0001](adr/ADR-0001-architecture.md) | Modular monolith |
| [0002](adr/ADR-0002-authentication.md) | Supabase Auth + JWT + API key |
| [0003](adr/ADR-0003-agent-orchestrator.md) | In-process agent pipeline, coded risk limits |
| [0004](adr/ADR-0004-deployment.md) | Vercel + Render + HF Space + Supabase |
| [0005](adr/ADR-0005-ai-inference.md) | Remote inference via HF Space |
| [0006](adr/ADR-0006-paper-trading.md) | Paper-trading engine semantics & human-in-the-loop AI |

## 11. Non-goals

Real trading/order execution; notifications (permanently out of scope);
intraday data; multi-tenant RLS policies (data access is backend-mediated with
ownership in app code); document uploads for RAG (news-only corpus this phase,
by owner decision).

**Deferred (Phase 6, ready for a later phase):** streaming assistant responses
(needs backend SSE + proxy passthrough); Reddit / Twitter-X sentiment and
OpenBB providers (the `providers/` abstraction is ready for them); correlated
(covariance-based) Monte-Carlo (current model is per-asset GBM); the official
TradingView Charting Library (current charts use lightweight-charts — no license
was available; swap-in path documented for when one is).
