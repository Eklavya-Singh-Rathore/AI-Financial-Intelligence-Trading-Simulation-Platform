# project_handover.md

> **Single source of truth for resuming development** — self-contained; no prior
> conversations needed. Last updated: **2026-07-21, Phase 6.1 SHIPPED** — merged
> to `main` (`e8f3fba`), Render + Vercel deployed, production-verified. Phase 6.1:
> (1) rotated the Gemini key + moved `GEMINI_MODEL` to the stable
> `gemini-flash-latest` alias (the pinned `gemini-2.5-flash` 404s for new keys);
> (2) a **Kronos variant registry** — `KRONOS_VARIANT` auto-selects **base for
> local dev, small in production**; (3) **intraday forecasting** — the forecast
> service is interval-aware (1m–1H via the ohlcv resolver, session-aware future
> timestamps), migration `0017_intraday_forecasts` adds `forecasts.interval` +
> `target_ts` (Supabase head is now `0017`). See §11. Prior: Phase 6.5 (trading
> workstation) shipped at `2a04d01`, §10.

## 1. What this is

**AI Financial Intelligence Trading Simulation Platform** — multi-user
decision-support (NO real trading) for the Indian market: a **curated Nifty-100
universe** (~100 instruments) that **lazy-loads the rest of NSE/BSE on demand**
(India-only, ~300-instrument cap). Ingests daily OHLCV, computes indicators,
forecasts with the vendored **Kronos** foundation model, backtests on
**NautilusTrader**, runs a 7-agent LLM pipeline (Gemini) producing risk-limited
recommendations, **explains** those recommendations, lets users **paper-trade**
them (human-in-the-loop — AI never auto-executes), computes **portfolio
analytics** (VaR / Monte-Carlo / optimization), serves company **research**
(profiles/statements/earnings), grounds chat — a full page **and** a site-wide
floating dock — in market data + a persisted **news corpus with citations**,
and **evaluates** its own AI quality (`/insights`). Phase 6 layers on a
**professional UI** (design tokens + component library, TradingView-grade
charting) and **external data providers** (Finnhub + Alpha Vantage).

- Repo: https://github.com/Eklavya-Singh-Rathore/AI-Financial-Intelligence-Trading-Simulation-Platform
  — `main` at **`e8f3fba`** (Phase 6.1 complete, deployed). Branch
  `claude/phase-6-1-key-rotation-kronos` == `main`; its worktree + the older
  Phase 6.5 worktree can be deleted.
- DB/Auth: Supabase **`ai-stock-prediction`** (`rekoawsoghrjcimknkfz`, ap-south-1, PG 17)
- **Live** (§7): Vercel frontend · Render backend · HF inference Space · Supabase —
  serving **Phase 6.1**. Supabase head is `0017_intraday_forecasts`.
- Docs: **`docs/MASTER_ARCHITECTURE.md`** (start here), `docs/architecture/`
  (7 docs), `docs/adr/` (ADR-0001..0006), `docs/deploy-render.md`,
  `docs/deploy-hf-space.md`, `docs/environment.md`, `README.md`.
- **Notifications are permanently out of scope** (owner decision, Phase 4).
- The Phase 5 branch `claude/phase-4-5-deployment-migration-ea8b0e` and the
  Phase 6 branch `claude/phase-6-professional-trading` are both fully merged
  into `main` and their worktrees can be deleted. The **active** worktree is
  now on the Phase 6.5 branch (same path, `.claude/worktrees/phase-4-5-…`).

## 2. Phase history (all merged on `main`)

| Phase | Delivered |
|---|---|
| 1 | FastAPI core, yfinance→`price_bars` ingestion, indicators, Forecaster/Backtester registries, APScheduler, CI, Docker |
| 2 | LLM layer (Gemini/OpenAI/fake), 7-agent pipeline w/ coded risk limits, NewsAPI, MiniLM semantic memory, agents API |
| 2.5 | Full audit remediation (auth, rate limits, run caps, pooler-safe asyncpg, hardened Docker, Prometheus, prompt trust boundaries, DB-integration suite) |
| Kronos | Vendored `app/ml/kronos_src/` (MIT); `model=kronos` verified live |
| 3 | Live verification + 5 bug fixes; `/instruments/summary`; persisted chat + RAG; **Next.js frontend**, auth proxy, both themes |
| 4 | **Supabase Auth + JWT + RBAC + per-user isolation** (migration 0009), open sign-up, login UI + session middleware, Vercel deploy |
| 4.5 | **Deployment migration**: remote Kronos/MiniLM via private HF Space, `space_client`, mode toggles, slim torch-free Render image, keepalive; production-verified |
| 4.6 | **Stabilization**: full E2E verification, **Guest Login**, 2 bug fixes, DB hardening (migration 0010), architecture docs (7) + ADRs (5) |
| 5 | **Intelligence, research & paper trading** (2026-07-17): paper-trading engine + `/simulation` (API+UI), financial research (profiles/statements/earnings), news RAG + chat citations, explainability (+`context_snapshot`), portfolio intelligence, AI evaluation + `/insights`, `docs/MASTER_ARCHITECTURE.md` + ADR-0006, migrations 0011–0013 |
| 6 | **Professional trading experience & market expansion** (2026-07-19, merge `b839223`): Kronos audit surfaced in `/health`; watchlists (migration 0014); paginated/searchable `/instruments/summary`; curated Nifty-100 catalog + idempotent admin sync + backfill; external-provider abstraction (Finnhub + Alpha Vantage, degrade-to-keyless); whole-market lazy load + durable `ingest_jobs` queue (migration 0015); numpy-only portfolio analytics (VaR/Monte-Carlo/optimization); frontend design system + `components/ui/*`; professional `TradingChart` (persisted lightweight-charts instance, panes, forecast band, trade markers); redesigned dashboard/Portfolio/Simulation; command palette; site-wide floating assistant; design-system polish across agents/insights/chat/login; proxy 204/304 fix |
| 6.5 | **Professional trading chart upgrade** (2026-07-21, merge `2a04d01`) — the chart became a trading workstation. Stays on Lightweight Charts (official Charting Library re-audited, still no license). Multi-interval OHLCV resolver (1m/5m/15m/30m/1H via on-demand yfinance intraday, not persisted; 1D stored; 1W/1M resampled), 10 range presets, 7 chart types (candles/hollow/bar/line/area/baseline/Heikin-Ashi). 10 new indicators (VWAP/ATR/SuperTrend/ADX/StochRSI/CCI/OBV/PSAR/Donchian/Ichimoku) + a data-driven catalog/renderer + picker + localStorage presets. Canvas drawing-tools engine (trend/ray/horizontal/vertical/rectangle/fib/measure/text; select/move/delete, undo/redo, per-symbol persistence) + Volume Profile. Chart-docked order ticket with a new **stop-limit** order type (migration `0016` widens `sim_orders.order_type`). Support/resistance + AI-recommendation overlays. Design spec: `.claude/plans/proud-waddling-eich.md` |

## 3. Architecture

`api/routers → services → (ml | backtesting | llm | agents | providers) →
models/db` (async SQLAlchemy → Supabase). Registries select implementations;
heavy work runs off the event loop. Inference modes: `KRONOS_MODE`/
`EMBEDDINGS_MODE` = `local` (dev) or `remote` (HF Space, production). Frontend
(Next.js 15) reaches the backend only via the authenticated same-origin proxy
`app/api/backend/[...path]`. Phase 5 services: `simulation` (paper-trading
engine), `research`, `news_rag`, `evaluation`. Phase 6 services:
`instrument_admin` (catalog sync), `market_expansion` (lazy-load + queue drain),
`portfolio_analytics` (numpy-only VaR/Monte-Carlo/optimization); the
`app/providers/` package is a capability-based external-data abstraction
(yfinance/Finnhub/Alpha Vantage, degrade-to-empty). **Complete reference:
`docs/MASTER_ARCHITECTURE.md`.**

Key Phase 5 design points (ADR-0006): daily-bar order semantics (market at
latest close; limit/stop rest and trigger on new bars, gap-aware), avg-cost
accounting, equity curve reconstructed on demand (no snapshot table), one
portfolio per owner, and **AI proposals are structural human-in-the-loop**
(`proposed` → human accept/reject; HOLD/veto/zero-size not proposable).

## 4. Auth model

- **Users:** Supabase Auth, email+password, open sign-up; cookie sessions;
  `middleware.ts` guards all routes except `api/backend` + `api/guest`.
- **Guest:** "Continue as Guest" → server-side `/api/guest` signs in a dedicated
  account (`guest@finintel.app`), normal `user` role, no bypass.
- **Backend** (`app/core/auth.py`): `X-API-Key` → `service`; `Bearer <jwt>`
  verified locally (HS256) or remotely (60s cache). Roles: `service` > `admin` > `user`.
- **Isolation:** `user_id` on chat_sessions/agent_runs/backtests/forecasts/
  sim_portfolios/sim_orders/sim_trades; cross-user → 404. News documents are a
  shared corpus (public headlines) by design.

## 5. Database

Alembic head on Supabase: **`0016_stop_limit`** — Phase 6 added
`0014_watchlists` + `0015_ingest_jobs`; Phase 6.5 added `0016_stop_limit`
(widened `sim_orders.order_type` to `VARCHAR(16)` for the stop-limit type). All
applied to Supabase. *(Note: `alembic upgrade` can't run against the Supabase
pooler — prepared-statement error; 0016 was applied via a direct `ALTER` + a
stamp of `alembic_version`. CI still proves the whole chain on vanilla
Postgres.)* Owned: `forecasts`, `backtests`, `agent_runs` (+`context_snapshot`),
`agent_messages`, `chat_sessions`, `chat_messages`, `sim_portfolios`,
`sim_orders`, `sim_trades`, `sim_positions`, `instrument_fundamentals`,
`research_documents`, `watchlists`, `watchlist_items`, `ingest_jobs`. Adopted:
`instruments` (curated Nifty-100 +
on-demand, incl. `sector_id`/`industry_id` mapped on the ORM), `price_bars`,
`data_providers`, `instrument_provider_mappings`, `exchanges`, warehouse
tables, `agent_embeddings`. **RLS deny-by-default everywhere** (backend
connects as `postgres`, ownership in app code). Migrations manual
(`alembic upgrade head`); CI proves the chain on vanilla Postgres.
`scripts/base_schema.sql` is **stale** (predates 0011–0013) — regenerate it if
a fresh-DB bootstrap is ever needed.

## 6. Verification status (Phase 6 ship, 2026-07-19)

- **Backend gates:** ruff/mypy/bandit clean (104 files typed; 17 bandit Low,
  0 Med, 0 High — accepted baseline). **218 fast tests passed** (Phase 6
  suites: providers, portfolio_analytics, catalog, market_expansion, plus
  all prior).
- **DB integration:** **25/25 db-marked tests green** against live Supabase
  (Phase 6 adds watchlists CRUD, catalog sync + no-op idempotency,
  market-expansion track lifecycle + advisory lock).
- **Frontend:** `tsc --noEmit` clean, **36 node tests** pass (chart ranges,
  chart markers, search, table sort, order ticket, nav, assistant session),
  `next build` green (11 routes).
- **Phase 5 verification still holds** — the Phase 5 paper-trading engine,
  research, news RAG, explainability, and evaluation surfaces are unchanged
  by Phase 6.
- **Production verification (2026-07-19, live guest→Vercel→Render→Supabase):**
  - `/health` reports **Phase 6 model-audit fields** (`default_forecaster:
    kronos`, `kronos_model_id: NeoQuasar/Kronos-small`,
    `kronos_tokenizer_id: NeoQuasar/Kronos-Tokenizer-base`,
    `kronos_max_context: 512`, `embedding_model_id: all-MiniLM-L6-v2`,
    `remote_inference` key present).
  - Redesigned login form uses the `Card`/`Input`/`Button` primitives
    (verified computed styles: 36px inputs, shadow-xs card).
  - Dashboard: 16 instruments render with real deltas (▲13 ▼3 –0), watchlist
    tabs, search, type filters, floating assistant FAB all present.
  - `/watchlists` responds 200 (empty for fresh guest).
  - `/market/search?q=TATA` responds 200 with 7 hits (whole-market lazy-load
    search functional).
  - `/instruments/summary?limit=5` returns the Phase 6 paginated shape
    (`items`, `total: 16`, first=ASIANPAINT).
  - `/simulation/analytics/risk` responds 200 with `available: true` —
    portfolio analytics ran end-to-end against the guest's paper portfolio.
  - `TradingChart` renders on RELIANCE (990×412 canvas, SMA/Vol/range
    toolbar, RSI indicator, forecast mention).
- **Bug found & fixed during Task 18 verification:** the `/api/backend` proxy
  turned upstream `204 No Content` into `500` by passing an empty-string body
  to `new NextResponse(...)` (null-body statuses reject any body). DELETE
  returns 204, so chat-session deletion was broken end-to-end. Fixed to
  forward `204/205/304` with a `null` body. Committed with Task 18 (`ee65202`).
- Not live-exercised in production (mechanism proven by db-integration tests
  and/or gated on the owner): admin catalog sync (needs `X-API-Key`;
  `POST /admin/catalog/sync` will expand 16 → ~100 instruments and backfill);
  the two provider secrets (`FINNHUB_API_KEY`, `ALPHA_VANTAGE_API_KEY`) — not
  yet set as Render production secrets, so those providers currently degrade
  to keyless yfinance (see §8).

## 7. Deployment (live, Phase 6 code)

```
Users → Vercel frontend → Render backend (slim, no torch) → Supabase
                                 ├→ HF Space ai-inference-service (Kronos + MiniLM)
                                 └→ Gemini/OpenAI · NewsAPI · yfinance · Finnhub · Alpha Vantage
```

- **Frontend → Vercel** `ai-financial-intelligence-platform`. **LIVE:**
  `https://ai-financial-intelligence-platf-eklavya-singh-rathores-projects.vercel.app`
  (auto-deployed from the `main` push at `b839223`).
- **Backend → Render** `srv-d995r0faqgkc73fpjfsg`. **LIVE:**
  `https://stock-ai-backend-gv17.onrender.com` — deploy
  `dep-d9e8aajrjlhs73bu2udg` of commit `b839223` (Phase 6, 2026-07-19,
  build+rollout 08:04:58Z → 08:08:31Z ≈ 3.5 min). **Note:** the Render
  service does NOT auto-deploy on push in practice (webhook never fired for
  the 4.5, 5, or 6 merges) — trigger via API:
  `POST /v1/services/srv-…/deploys {"commitId": …}`.
- **Inference → HF Space** `Eklavya73/ai-inference-service` (private, Gradio
  SDK on ZeroGPU, CPU-only). **LIVE:**
  `https://eklavya73-ai-inference-service.hf.space` — unchanged by Phase 6.
- **Keep-alive:** GitHub Actions pings Render `/live` every 10 min; backend
  scheduler pings the Space every 6 h. Phase 6 adds `ingest_job_drain` every
  5 min (advisory lock 815004). Phase 5 jobs: sim order sweep (ingest+15min),
  news ingest (ingest+30min, `ENABLE_NEWS_INGEST`, quota-guarded by
  `NEWS_INGEST_DAILY_CAP`).
- **Env:** no new required vars — all Phase 5 + 6 settings have safe defaults
  (providers degrade to keyless yfinance without their keys). Full reference:
  `docs/environment.md`.

## 8. Remaining owner actions

**Immediate (Phase 6 ship follow-through):**

1. **Expand the universe to Nifty-100 in production.** Run the idempotent
   catalog sync (privileged; needs your `X-API-Key`):
   ```
   curl -X POST https://stock-ai-backend-gv17.onrender.com/admin/catalog/sync \
     -H "X-API-Key: <API_KEY>"
   ```
   This takes 16 → ~100 instruments and enqueues backfills (drained by the
   5-min `ingest_job_drain` job; also opportunistically). Watch Render RAM
   during backfill (`INGEST_PAUSE_SECONDS=0.3` keeps peak well under 512 MB).
2. **(Optional) Enable the Phase 6 providers.** Set `FINNHUB_API_KEY` and
   `ALPHA_VANTAGE_API_KEY` as Render secrets (Render dashboard →
   Environment). Values are in your local git-ignored `.env`; treat those
   dev values as compromised and rotate to fresh keys before setting. Skip
   entirely and the providers just degrade to keyless yfinance — everything
   still works.

**Standing (unchanged from Phase 5):**

3. **Rotate credentials shared during development:** Supabase DB password →
   new pooler `DATABASE_URL`; `GOOGLE_AI_STUDIO_API_KEY`, `OPENAI_API_KEY`,
   `NEWSAPI_KEY`; regenerate `API_KEY`; the **Render API key** (used again
   this phase to trigger the Phase 6 deploy) and **HF write token** (replace
   HF with a fine-grained **read** token on the Space).
4. Create least-privilege DB role `app_rw` to replace the `postgres` app
   connection — SQL in `docs/deploy-render.md`.
5. Enable Supabase **leaked-password protection**; consider requiring email
   confirmation (currently open sign-up).
6. Optional: fund the OpenAI key or clear `LLM_FALLBACK_PROVIDER`; paste
   `SUPABASE_JWT_SECRET` into Render; rotate the guest password.
7. Housekeeping: delete the merged branches
   `claude/phase-4-5-deployment-migration-ea8b0e` and
   `claude/phase-6-professional-trading` + their worktrees; regenerate
   `scripts/base_schema.sql` if a fresh-DB bootstrap is wanted.

## 9. Future / beyond Phase 6

**Deferred in Phase 6, abstractions ready:** streaming assistant responses
(needs backend SSE + proxy passthrough) · Reddit / Twitter-X sentiment and
OpenBB providers (add a `BaseProvider` subclass + key + `PROVIDER_PRIORITY`
entry) · correlated (covariance-based) Monte-Carlo (current model is per-asset
GBM) · the official TradingView Charting Library — **re-audited in Phase 6.5**
(2026-07-20): still requires a TradingView-granted license the owner doesn't
have, so the decision to stay on Lightweight Charts was reconfirmed; revisit if
a license is ever obtained.

**Longer-term:** per-user LLM quotas · prompt registry/versioning · RAG
document uploads (filings/transcripts — `research_documents.doc_type` is ready)
· forecast persistence from the UI (frontend calls `persist=false`, so
`/insights` accuracy only accrues from API/backfill usage) · agent-quality
evaluation harness beyond `/evaluation/summary` · multi-tenant RLS policies if
SaaS is pursued. *(Notifications: permanently removed. The durable job queue —
formerly future work — shipped in Phase 6 as `ingest_jobs`.)*

## 10. Phase 6.5 — professional trading chart upgrade (SHIPPED)

**Merged to `main` at `2a04d01`** (2026-07-21), Render deploy
`dep-d9f8c1r7uimc73fvanjg` LIVE, Vercel auto-deployed, production-verified
(guest path: stop-limit order placed → resting `open` → cancelled; instrument
page renders the drawing rail + Trade/AI cards + interval selector). **Plan
file:** `C:\Users\Eklavya Singh Rathor\.claude\plans\proud-waddling-eich.md`.

**Scope decisions (owner-approved, do not re-litigate without asking):**
- **Stay on TradingView Lightweight Charts** (custom build), not the official
  Charting Library — needs a granted license the owner doesn't have.
- **Intraday data source: yfinance** (free, already a dependency, verified live
  for NSE `.NS`). The owner supplied three paid keys
  (`MARKETSTACK_API_KEY`, `ALPHA_VANTAGE_INTRADAY_KEY`, and a duplicate
  `FINNHUB_API_KEY`) intending them for intraday — **all three return 403 /
  "premium endpoint" on their free tiers** for intraday specifically (verified
  live). They're stored in the git-ignored root `.env` and wired into the
  provider abstraction's capability set for future paid upgrades, but yfinance
  is the actual intraday source today.
- **Staged delivery**, 5 stages, each committed + gated + live-verified
  independently (see the phase-history row above and the plan file for the
  full per-stage breakdown).
- **Four scope calls:** Kronos confidence band deferred (real ML/Space change,
  not charting) · ~11 high-value drawing tools, not all ~30 from the original
  prompt · intraday fetched on-demand + 60s-cached, **not** persisted to
  `price_bars` · drawing/indicator presets in localStorage first (no new
  schema).

**Stage 1 (done, `eb34bdc`):** backend multi-interval OHLCV resolver
(`app/services/ohlcv.py`) + `interval` param on `/prices` and `/indicators`;
frontend interval selector (1m/5m/15m/30m/1H/1D/1W/1M), 10 range presets
(1D…MAX), and 7 chart types (candles/hollow/bar/line/area/baseline/Heikin-Ashi).
Verified live against real NSE data (5m RSI recomputed over 4256 points, IST
session timestamps correct).

**Stage 2 (done, `76f2388`):** 10 new backend indicators in
`app/services/indicators.py` (VWAP, ATR, SuperTrend, ADX, Stochastic RSI, CCI,
OBV, Parabolic SAR, Donchian, Ichimoku); a data-driven frontend catalog
(`lib/indicators.ts`) where each `id` doubles as the backend name, a generic
renderer in `useTradingChart.ts` (overlays on the price pane, oscillators each
in their own sub-pane, with bands/histograms/reference-levels), an indicator
picker dropdown in `TradingChart.tsx`, and localStorage presets
(`lib/chartPresets.mjs`). Verified live (all 10 compute on real data; picker
toggles refetch + persist; no console errors). **Volume Profile was moved to
Stage 3** — it needs the same canvas price→pixel coordinate mapping as the
drawing-tools engine, so it's built there.

**Stage 3 (done):** `DrawingCanvas.tsx` — a canvas overlay mapping data-space
anchors to pixels via the chart's converters, redrawn on pan/zoom; tools
(trend/ray/horizontal/vertical/rectangle/fib/measure/text), select/move/delete,
undo/redo, per-symbol localStorage persistence; **Volume Profile** overlay.
Pure geometry in `lib/chartDrawings.mjs`.

**Stage 4 (done):** backend **stop-limit** order type (`ORDER_TYPES`, schema,
`trigger_fill_price`, validation; migration `0016` widened
`sim_orders.order_type`); chart-docked `OrderTicket` (pre-filled symbol) + an
"AI view" card (latest completed agent recommendation); **support/resistance**
overlay (`lib/supportResistance.mjs`) drawn as `levels` on the canvas.

**Stage 5 (done):** docs (this file, environment/database/frontend/MASTER),
full regression, merged + deployed + production-verified.

**Deferred beyond Phase 6.5:** exotic drawing tools (pitchfork, Gann, channels,
long/short position box), non-native intervals (3m/10m/45m/2H/4H), exotic chart
types (Renko/Kagi/P&F/Line-Break/Range), Kronos confidence band. Paid intraday
providers (`MARKETSTACK_API_KEY`, `ALPHA_VANTAGE_INTRADAY_KEY`) remain **local
`.env` only** (not in `.env.example`/`render.yaml`) — the free tiers can't do
intraday, so yfinance serves it; wire them if a paid plan is ever obtained.

## 11. Phase 6.1 — key rotation, Kronos variants, intraday forecasting (SHIPPED)

**Merged to `main` at `e8f3fba`** (2026-07-21); Render deploy
`dep-d9fh506rnols73bv3mug`, Vercel auto; Supabase head `0017_intraday_forecasts`.

**Task 1 — Gemini key rotation.** Rotated `GOOGLE_AI_STUDIO_API_KEY` in the
git-ignored root `.env` and on Render (runtime only — never committed;
`.env.example`/`render.yaml` stay placeholders). The provided key authenticates
fine, but the configured `gemini-2.5-flash` **404s for new keys** ("no longer
available to new users"), so `GEMINI_MODEL` now defaults to the stable
`gemini-flash-latest` alias (config.py + `.env.example` + Render env). Verified:
local `google-genai` call + a prod `/chat` round-trip (200, cleaned up). **The key
looks free-tier** (gemini-2.0-flash already 429s on it) — watch rate limits under
agent load; the OpenAI fallback key is set on Render.

**Task 3 — env-based Kronos variant.** `app/ml/kronos_variants.py` maps
`mini|small|base` → Hub ids (only these are published NeoQuasar checkpoints;
"tiny"/"large" are a *different* model family, deliberately absent).
`KRONOS_VARIANT` empty = **auto by `ENV`**: base for local dev, small in
production. `resolve_kronos_config` feeds both Kronos forecasters + `/health`;
`KRONOS_MODEL_ID`/`_TOKENIZER_ID`/`_MAX_CONTEXT` remain per-field overrides. Local
`.env` set to `KRONOS_VARIANT=base`; **Render needs no change** (ENV=production →
auto small); the HF Space is unchanged (still small, its own `app.py`). Base
loads+forecasts locally (validated).

**Task 2 — intraday forecasting.** `run_forecast` gained an `interval` param: it
sources bars via the `ohlcv` resolver and generates interval-correct future
timestamps (`ohlcv.future_timestamps` — business days / NSE session-aware intraday
steps / resample anchor), passed into the forecaster via `resolve_target_timestamps`
so Kronos sees the right temporal context (Kronos is timeframe-agnostic — the
daily-only limit was platform wiring, not the model). Migration `0017` adds
`forecasts.interval` + `target_ts`; evaluation's daily accuracy join filters
`interval='1D'`. Endpoint + `ForecastOut`/`ForecastPoint` gained `interval` +
`target_time`; the chart overlay now renders on every interval (maps `target_time`
for intraday). The UI requests `persist=false` for display (as daily always did);
persistence is fully supported for `persist=true`. Verified: real e2e (RELIANCE
1D/5m/15m/1H) + a persisted 5m row (interval/target_ts correct, cleaned up).

**Migration 0017 applied to Supabase via direct ALTER + version stamp** (same
pooler/asyncpg prepared-stmt limitation as 0016; CI proves the chain on vanilla
PG). Gates: backend ruff/mypy/bandit + 262 fast tests; frontend tsc + 60 tests +
build.

**Deferred (Phase 6.1):** intraday forecast *accuracy* eval (no stored intraday
actuals to mature against — daily-only by design); a paid/keyed Gemini tier if the
free key rate-limits under load. The paid intraday-data keys stay deferred as
before (yfinance serves intraday).
