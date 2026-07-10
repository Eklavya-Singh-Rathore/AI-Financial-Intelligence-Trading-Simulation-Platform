# project_handover.md

> **Single source of truth for resuming development** — self-contained; no prior
> conversations needed. Last updated: **2026-07-08, Phase 4 complete**
> (production auth, multi-user isolation, deployment).

## 1. What this is

**AI Financial Intelligence Trading Simulation Platform** — decision-support
(NO real trading) for a fixed 16-asset Indian-market universe (NIFTY 50, Sensex,
gold/silver ETFs, 12 NSE blue-chips). Ingests daily OHLCV, computes indicators,
forecasts with the vendored **Kronos** foundation model, backtests on
**NautilusTrader**, runs a 7-agent LLM pipeline (Gemini) producing risk-limited
recommendations, and serves a **multi-user** Next.js dashboard + grounded chat.

- Repo: https://github.com/Eklavya-Singh-Rathore/AI-Financial-Intelligence-Trading-Simulation-Platform
- DB/Auth: Supabase **`ai-stock-prediction`** (`rekoawsoghrjcimknkfz`, ap-south-1, PG 17)
- Docs: `README.md`, `AUDIT_REPORT.md` (historical audit), `docs/deploy-oracle.md`
- **Notifications are permanently out of scope** (owner decision, Phase 4).

## 2. Phase history (commits on `main`)

| Phase | Commits | Delivered |
|---|---|---|
| 1 | `a6b86d5`,`71aa32a` | FastAPI core, yfinance→`price_bars` ingestion, indicators, Forecaster/Backtester registries, APScheduler, migrations 0004-baseline/0005, CI, Docker |
| 2 | `fa9f49d` | LLM layer (Gemini primary/OpenAI fallback/fake), 7-agent TradingAgents-style pipeline w/ coded hard risk limits, NewsAPI, MiniLM semantic memory (`agent_embeddings`, 384-d), agents API, migration 0006 |
| 2.5 | `7e8fc60` | Full audit remediation: API-key auth, rate limiting, run concurrency caps + timeouts + orphan sweep, CPU work off event loop, rollback discipline, failover normalization + rate-limit backoff, pooler-safe asyncpg, requirements.lock, hardened non-root Docker, Prometheus metrics + request IDs, prompt trust boundaries, fail-closed risk, migration 0007, DB-integration suite + `scripts/base_schema.sql` |
| Kronos | `a284557` | Vendored `app/ml/kronos_src/` (MIT; one relative-import fix); `model=kronos` verified live |
| 3 | `9b0aeed`,`89b478b`,`a0c3976`,`95c2034` | **First live verification** (11,844 bars, live Kronos forecast, live Nautilus backtest, first completed agent run — drawdown veto fired) + 5 live-found bug fixes (enums, cash-vs-equity drawdown, adjusted prices, 429 backoff, ORM-after-rollback); `/instruments/summary`; persisted chat + RAG (migration 0008); Next.js frontend (dashboard/candles+forecast overlay/backtest UI/agent transcripts/chat), auth proxy, both themes, dataviz-validated palettes |
| 4 | this phase | **Supabase Auth + JWT + RBAC + per-user isolation** (migration 0009), open sign-up, login UI + session middleware, GitHub push, Vercel frontend deploy, Oracle backend runbook |

## 3. Architecture (stable since audit)

`api/routers` → `services` → (`ml` | `backtesting` | `llm` | `agents`) →
`models`/`db` (async SQLAlchemy → Supabase). Registries select implementations.
Agent pipeline: deterministic gather → technical + news analysts → bull/bear
debate → trader → risk manager (**coded limits only tighten**: size cap,
drawdown veto, missing-evidence halving) → portfolio manager; every step
persisted (`agent_messages`), memory embedded for RAG recall. Chat grounds
answers in live stats + recent decisions + semantic memory inside
`<untrusted-data>` boundaries. Frontend (Next.js 15) reaches the backend only
through `app/api/backend/[...path]` which forwards the user's Supabase Bearer
token (or `BACKEND_API_KEY` in local dev).

## 4. Auth model (Phase 4)

- **Users:** Supabase Auth, email+password, **open sign-up**; session in cookies
  (@supabase/ssr); `middleware.ts` redirects signed-out visitors to `/login`.
- **Backend** (`app/core/auth.py` → `get_auth` on every business route):
  `X-API-Key` = `service` role (admin-equivalent, automation/dev);
  `Bearer <jwt>` verified locally (HS256, `SUPABASE_JWT_SECRET`) or remotely
  (`/auth/v1/user`, 60s cache) — deploy never blocks on the JWT secret.
- **Roles:** JWT `app_metadata.role`; a `BEFORE INSERT` trigger on `auth.users`
  (`public.grant_admin_role`, migration 0009) grants **admin** to
  `esr.arsenal.07@gmail.com` and `rathore.eklavya72@gmail.com` at sign-up.
- **Isolation:** `user_id` on `chat_sessions`, `agent_runs`, `backtests`,
  `forecasts`. Non-privileged queries filter by owner; cross-user access → 404;
  legacy NULL rows visible to admin/service only. **Live-verified** with two
  seeded users (A/B could not see each other's data; deleted after).

## 5. Database

Alembic head **`0009_user_ownership`** (all migrations applied to Supabase via
MCP with `alembic_version` stamped in lockstep). Project-owned tables:
`forecasts`, `backtests`, `agent_runs`(+idempotency_key), `agent_messages`,
`chat_sessions`, `chat_messages` (+`user_id` on the four owned tables). Adopted
pre-existing: `instruments` (16), `price_bars` (**11,844 real bars**),
`data_providers`, `instrument_provider_mappings` (TATAMOTORS→`TMPV.NS`
post-demerger), `exchanges/...`, `agent_embeddings`. Fresh-DB bootstrap:
`scripts/base_schema.sql` (CI + compose auto-load; 0005 guards with a clear
error).

## 6. Status snapshot

- **Backend:** all endpoints live-verified incl. auth matrix; `/api/v1` + legacy
  mounts; metrics `/metrics`; probes `/live` `/health`.
- **AI:** Gemini `gemini-2.5-flash` live (free tier — 429s absorbed by 35s
  backoff); OpenAI fallback key has **no quota** (dead until funded); Kronos +
  Nautilus verified on real data; RAG chat live-verified.
- **Tests:** 106 fast + 7 db-marked (incl. isolation) + 4 slow — all green;
  ruff/mypy/bandit clean; frontend `tsc`+`next build` clean.
- **CI:** backend / integration-Postgres / frontend / docker jobs (first remote
  run happens on GitHub push).
- **Frontend:** login/sign-up, session guard, dashboard, instrument detail
  (candles+forecast+backtest), agent transcripts, chat — verified in browser.

## 7. Deployment

- **Frontend → Vercel** (root `frontend/`). Env: `NEXT_PUBLIC_SUPABASE_URL`,
  `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `BACKEND_URL` (set once backend is hosted;
  leave `BACKEND_API_KEY` empty in production).
- **Backend → Oracle Cloud VM** (owner provides credentials later): full
  runbook `docs/deploy-oracle.md` + `infrastructure/docker-compose.prod.yml`
  (API behind Caddy auto-HTTPS; A1 ARM Always-Free shape fits — aarch64 wheels).
  Post-deploy: set Vercel `BACKEND_URL`, set backend `CORS_ORIGINS` to the
  Vercel URL.
- Local dev: uvicorn :8000 + `npm run dev` :3000 (`.claude/launch.json`).

## 8. Security posture & owner actions before production

1. **Rotate ALL dev credentials** (shared during development, compromised by
   definition): Supabase **DB password**, `GOOGLE_AI_STUDIO_API_KEY`,
   `OPENAI_API_KEY`, `NEWSAPI_KEY`, `ALPHA_VANTAGE_KEY`. Anon key is public by
   design.
2. Create least-privilege DB role (replace `postgres` app connection):
   `CREATE ROLE app_rw LOGIN PASSWORD '...'; GRANT SELECT,INSERT,UPDATE,DELETE
   ON price_bars,forecasts,backtests,agent_runs,agent_messages,chat_sessions,
   chat_messages,agent_embeddings TO app_rw; GRANT SELECT ON instruments,
   data_providers,instrument_provider_mappings,exchanges TO app_rw;`
3. Optional: paste `SUPABASE_JWT_SECRET` into backend env (faster local JWT
   verification). 4. Fund the OpenAI key or clear `LLM_FALLBACK_PROVIDER`.
5. Rate limiting + agent-run caps are ON; `EXPOSE_ERROR_DETAILS=false` in prod.

## 9. Phase 5 roadmap (next)

Job queue replacing BackgroundTasks (durable runs) · per-user LLM quotas ·
scheduled autonomous runs (needs queue + alerting) · prompt registry/versioning ·
agent-quality evaluation harness · additional data APIs (Twitter/X etc. — the
production URL from Vercel is the OAuth callback base) · multi-tenant RLS
policies if SaaS ever pursued. *(Notifications: permanently removed.)*
