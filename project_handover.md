# project_handover.md

> **Single source of truth for resuming development** — self-contained; no prior
> conversations needed. Last updated: **2026-07-17, Phase 5 SHIPPED**
> (paper trading, research, news RAG, explainability, evaluation — merged to
> `main`, CI green, deployed, production-verified).

## 1. What this is

**AI Financial Intelligence Trading Simulation Platform** — multi-user
decision-support (NO real trading) for a fixed 16-asset Indian-market universe
(NIFTY 50, Sensex, gold/silver ETFs, 12 NSE blue-chips). Ingests daily OHLCV,
computes indicators, forecasts with the vendored **Kronos** foundation model,
backtests on **NautilusTrader**, runs a 7-agent LLM pipeline (Gemini) producing
risk-limited recommendations, **explains** those recommendations, lets users
**paper-trade** them (human-in-the-loop — AI never auto-executes), serves
company **research** (profiles/statements/earnings), grounds chat in market
data + a persisted **news corpus with citations**, and **evaluates** its own
AI quality (`/insights`).

- Repo: https://github.com/Eklavya-Singh-Rathore/AI-Financial-Intelligence-Trading-Simulation-Platform
  — `main` at **`bb99901`** (Phase 5 merge), everything pushed, no open PRs.
- DB/Auth: Supabase **`ai-stock-prediction`** (`rekoawsoghrjcimknkfz`, ap-south-1, PG 17)
- **Live** (§7): Vercel frontend · Render backend · HF inference Space · Supabase —
  all serving the Phase 5 code.
- Docs: **`docs/MASTER_ARCHITECTURE.md`** (start here), `docs/architecture/`
  (7 docs), `docs/adr/` (ADR-0001..0006), `docs/deploy-render.md`,
  `docs/deploy-hf-space.md`, `docs/environment.md`, `README.md`.
- **Notifications are permanently out of scope** (owner decision, Phase 4).
- The Phase 5 work branch `claude/phase-4-5-deployment-migration-ea8b0e` (in a
  worktree under `.claude/worktrees/`) is fully merged into `main` and can be
  deleted along with its worktree.

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

## 3. Architecture

`api/routers → services → (ml | backtesting | llm | agents) → models/db`
(async SQLAlchemy → Supabase). Registries select implementations; heavy work
runs off the event loop. Inference modes: `KRONOS_MODE`/`EMBEDDINGS_MODE` =
`local` (dev) or `remote` (HF Space, production). Frontend (Next.js 15) reaches
the backend only via the authenticated same-origin proxy
`app/api/backend/[...path]`. Phase 5 services: `simulation` (paper-trading
engine), `research` (yfinance fundamentals, TTL cache), `news_rag` (embedded
news corpus + KNN), `evaluation` (AI quality/cost). **Complete reference:
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

Alembic head on Supabase: **`0013_run_context`** (applied; `alembic current`
verified). Owned: `forecasts`, `backtests`, `agent_runs`
(+`context_snapshot`), `agent_messages`, `chat_sessions`, `chat_messages`,
`sim_portfolios`, `sim_orders`, `sim_trades`, `sim_positions`,
`instrument_fundamentals`, `research_documents`. Adopted: `instruments` (16,
incl. `sector_id`/`industry_id` mapped on the ORM), `price_bars`,
`data_providers`, `instrument_provider_mappings`, `exchanges`, warehouse
tables, `agent_embeddings`. **RLS deny-by-default everywhere** (backend
connects as `postgres`, ownership in app code). Migrations manual
(`alembic upgrade head`); CI proves the chain on vanilla Postgres.
`scripts/base_schema.sql` is **stale** (predates 0011–0013) — regenerate it if
a fresh-DB bootstrap is ever needed.

## 6. Verification status (Phase 5 ship, 2026-07-17)

- **Backend gates:** 185 fast tests passed, ruff/mypy/bandit clean.
- **DB integration:** 18/18 db-marked tests green against live Supabase
  (order lifecycle, ownership isolation, proposal accept flow, limit
  rest→fill, news ingest/dedupe/KNN).
- **Frontend:** `tsc --noEmit`, `next build` (routes `/simulation`,
  `/insights` present), `npm test` 3/3.
- **CI:** green on merge commit `bb99901`.
- **Local full-stack smoke (before merge):** portfolio auto-create → market
  buy filled at close → performance/intelligence correct; research
  profile/financials/earnings live from yfinance then `cache` on second call;
  evaluation computed real historical numbers (5 matured Kronos points,
  MAPE 1.56%).
- **Production verification (after deploy, via the real guest→proxy path):**
  `/health` = production + remote modes; guest portfolio auto-created
  (₹10,00,000); limit order placed → rested `open` → cancelled; intelligence +
  performance correct; RELIANCE profile/earnings live; evaluation
  owner-scoped. Browser-verified: `/simulation`, `/insights`, and the
  instrument Research section all render with live data, **zero console
  errors** (screenshot taken in-session).
- **Bug found & fixed during ship:** equity curve valued holdings at 0 for
  calendar days after the last ingested bar (day-one portfolios, weekends) —
  `reindex(calendar)` dropped close history before `ffill`. Fixed by ffilling
  over the union of history + calendar; 2 regression tests added; verified
  live (equity 1,000,000 not 987,034). Commit `0821946`.
- Not live-exercised in production (mechanism verified by tests instead):
  chat news-citations end-to-end (corpus fills as agent runs / the daily
  `news_ingest` job execute) and the AI proposal accept flow (needs a
  completed BUY/SELL run; covered by db-integration test).

## 7. Deployment (live, Phase 5 code)

```
Users → Vercel frontend → Render backend (slim, no torch) → Supabase
                                 ├→ HF Space ai-inference-service (Kronos + MiniLM)
                                 └→ Gemini/OpenAI · NewsAPI · yfinance
```

- **Frontend → Vercel** `ai-financial-intelligence-platform`. **LIVE:**
  `https://ai-financial-intelligence-platf-eklavya-singh-rathores-projects.vercel.app`
  (auto-deployed from the `main` push).
- **Backend → Render** `srv-d995r0faqgkc73fpjfsg`. **LIVE:**
  `https://stock-ai-backend-gv17.onrender.com` — deploy `dep-d9cvkp58nd3s73canleg`
  of commit `bb99901`. **Note:** the Render service does NOT auto-deploy on
  push in practice (webhook never fired for this merge; also observed in 4.5) —
  trigger via API: `POST /v1/services/srv-…/deploys {"commitId": …}`.
- **Inference → HF Space** `Eklavya73/ai-inference-service` (private, Gradio
  SDK on ZeroGPU, CPU-only). **LIVE:**
  `https://eklavya73-ai-inference-service.hf.space` — unchanged by Phase 5.
- **Keep-alive:** GitHub Actions pings Render `/live` every 10 min; backend
  scheduler pings the Space every 6 h. New Phase 5 jobs: sim order sweep
  (ingest+15min), news ingest (ingest+30min, `ENABLE_NEWS_INGEST`).
- **Env:** no new required vars — all Phase 5 settings have safe defaults
  (see `docs/environment.md` §Phase 5).

## 8. Remaining owner actions

1. **Rotate credentials shared during development:** Supabase DB password →
   new pooler `DATABASE_URL`; `GOOGLE_AI_STUDIO_API_KEY`, `OPENAI_API_KEY`,
   `NEWSAPI_KEY`; regenerate `API_KEY`; the **Render API key** and **HF write
   token** (replace HF with a fine-grained **read** token on the Space).
   The Render API key was used again this phase (deploy trigger + status).
2. Create least-privilege DB role `app_rw` to replace the `postgres` app
   connection — SQL in `docs/deploy-render.md`.
3. Enable Supabase **leaked-password protection**; consider requiring email
   confirmation (currently open sign-up).
4. Optional: fund the OpenAI key or clear `LLM_FALLBACK_PROVIDER`; paste
   `SUPABASE_JWT_SECRET` into Render; rotate the guest password.
5. Housekeeping: delete the merged branch
   `claude/phase-4-5-deployment-migration-ea8b0e` + its worktree; regenerate
   `scripts/base_schema.sql` if a fresh-DB bootstrap is wanted.

## 9. Future / beyond Phase 5

Durable job queue replacing `BackgroundTasks` (durable + scheduled autonomous
runs) · per-user LLM quotas · prompt registry/versioning · RAG document
uploads (filings/transcripts — `research_documents.doc_type` is ready for it)
· forecast persistence from the UI (frontend currently calls
`persist=false`, so `/insights` forecast accuracy only accrues from
API/backfill usage) · agent-quality evaluation harness beyond
`/evaluation/summary` · additional data APIs (Twitter/X — the production
Vercel URL is the OAuth callback base) · multi-tenant RLS policies if SaaS is
pursued. *(Notifications: permanently removed.)*
