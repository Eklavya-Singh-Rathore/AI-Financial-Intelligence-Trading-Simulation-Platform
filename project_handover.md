# project_handover.md

> **Single source of truth for resuming development** — self-contained; no prior
> conversations needed. Last updated: **2026-07-11, Phase 4.6**
> (end-to-end verification, guest login, architecture docs, production-ready).

## 1. What this is

**AI Financial Intelligence Trading Simulation Platform** — multi-user
decision-support (NO real trading) for a fixed 16-asset Indian-market universe
(NIFTY 50, Sensex, gold/silver ETFs, 12 NSE blue-chips). Ingests daily OHLCV,
computes indicators, forecasts with the vendored **Kronos** foundation model,
backtests on **NautilusTrader**, runs a 7-agent LLM pipeline (Gemini) producing
risk-limited recommendations, and serves a Next.js dashboard + grounded chat.

- Repo: https://github.com/Eklavya-Singh-Rathore/AI-Financial-Intelligence-Trading-Simulation-Platform
- DB/Auth: Supabase **`ai-stock-prediction`** (`rekoawsoghrjcimknkfz`, ap-south-1, PG 17)
- **Live** (see §7): Vercel frontend · Render backend · HF inference Space · Supabase
- Docs: `README.md`, `docs/architecture/` (7 docs), `docs/adr/` (ADR-0001..0005),
  `docs/deploy-render.md`, `docs/deploy-hf-space.md`, `docs/environment.md`,
  `AUDIT_REPORT.md` (historical)
- **Notifications are permanently out of scope** (owner decision, Phase 4).

## 2. Phase history (commits on `main`)

| Phase | Delivered |
|---|---|
| 1 | FastAPI core, yfinance→`price_bars` ingestion, indicators, Forecaster/Backtester registries, APScheduler, CI, Docker |
| 2 | LLM layer (Gemini/OpenAI/fake), 7-agent pipeline w/ coded risk limits, NewsAPI, MiniLM semantic memory, agents API |
| 2.5 | Full audit remediation: API-key auth, rate limiting, run caps + timeouts + orphan sweep, CPU off event loop, failover normalization, pooler-safe asyncpg, requirements.lock, hardened non-root Docker, Prometheus + request IDs, prompt trust boundaries, DB-integration suite |
| Kronos | Vendored `app/ml/kronos_src/` (MIT); `model=kronos` verified live |
| 3 | First live verification (11,844 bars, live Kronos + Nautilus + agent run) + 5 bug fixes; `/instruments/summary`; persisted chat + RAG; **Next.js frontend** (dashboard/candles+forecast/backtest/agents/chat), auth proxy, both themes |
| 4 | **Supabase Auth + JWT + RBAC + per-user isolation** (migration 0009), open sign-up, login UI + session middleware, Vercel frontend deploy |
| 4.5 | **Deployment migration**: `RemoteKronosForecaster` + remote MiniLM via a private HF Space, reusable `space_client`, `KRONOS_MODE`/`EMBEDDINGS_MODE` toggles, slim torch-free Render image, `render.yaml`, keepalive workflow, proxy `maxDuration=300`; **backend + Space + frontend deployed and production-verified** |
| 4.6 | this phase — **stabilization**: full E2E verification, **Guest Login** (server-side session, dedicated guest account, no bypass), 1 bug fix + regression test, DB hardening (migration 0010), **architecture docs (7) + ADRs (5)**, handover rewrite |

## 3. Architecture

`api/routers → services → (ml | backtesting | llm | agents) → models/db`
(async SQLAlchemy → Supabase). Registries select implementations; heavy work
runs off the event loop. **Inference modes**: `KRONOS_MODE`/`EMBEDDINGS_MODE` =
`local` (in-process torch, dev) or `remote` (HF Space, production) — same public
forecaster name `kronos`, same persisted `model_name`. Frontend (Next.js 15)
reaches the backend only via the authenticated same-origin proxy
`app/api/backend/[...path]` (forwards the Supabase Bearer JWT; `maxDuration=300`).
**Full detail: `docs/architecture/` + `docs/adr/`.**

## 4. Auth model

- **Users:** Supabase Auth, email+password, open sign-up; cookie sessions
  (@supabase/ssr); `middleware.ts` guards all routes except `api/backend` +
  `api/guest`.
- **Guest (4.6):** "Continue as Guest" → server-side `/api/guest` signs in a
  dedicated pre-provisioned guest account (`guest@finintel.app`) with server-only
  `GUEST_EMAIL`/`GUEST_PASSWORD`; normal `user` role, full ownership isolation,
  no bypass, no client-exposed secret.
- **Backend** (`app/core/auth.py`): `X-API-Key` → `service`; `Bearer <jwt>`
  verified locally (HS256 `SUPABASE_JWT_SECRET`) or remotely (`/auth/v1/user`, 60s cache).
- **Roles:** `service` > `admin` (owner emails via trigger) > `user`.
- **Isolation:** `user_id` on chat_sessions/agent_runs/backtests/forecasts;
  cross-user → 404. **Live-verified** incl. the guest account.

## 5. Database

Alembic head **`0010_revoke_admin_execute`** (applied to Supabase; stamped in
lockstep). Owned: `forecasts`, `backtests`, `agent_runs`(+idempotency_key),
`agent_messages`, `chat_sessions`, `chat_messages`. Adopted: `instruments` (16),
`price_bars` (11,844+ real bars), `data_providers`, `instrument_provider_mappings`,
`exchanges`, warehouse tables, `agent_embeddings` (pgvector 384). **RLS
deny-by-default** on all public tables (intended — data flows through the
backend as `postgres`; Supabase REST API locked). Migrations manual
(`alembic upgrade head`). Fresh DB: `scripts/base_schema.sql`. Details:
`docs/architecture/database.md`.

## 6. Verification status (Phase 4.6)

**All implemented features verified end-to-end. No open bugs.**

- **Auth:** sign-in/guest/logout, JWT (local+remote), session persistence,
  protected routes, admin/user/guest roles, multi-user isolation — ✅.
- **APIs:** auth matrix (anon 401 / X-API-Key 200 / JWT 200), validation
  (horizon>60→422, horizon<1→422, unknown symbol→404, unknown forecaster→422,
  bad body→422), rate limiting configured, error responses sanitized — ✅.
- **Forecasting:** baseline + remote Kronos (HF Space) return 200 with finite
  predictions; UI overlay renders; `ForecasterError`→503 / baseline fallback — ✅.
- **Backtesting:** NautilusTrader 200; metric tiles render (Total return, Sharpe,
  Max drawdown, Win rate, Volatility, Fills); persistence — ✅.
- **Agents:** full 7-agent run completes (7 messages), coded risk limits, JSON
  outputs, remote-embedding memory writes, decision persistence — ✅.
- **Chat/RAG:** sessions create/list/delete, ownership isolation, grounded
  responses (verified when Gemini has quota), graceful degradation when the LLM
  is rate-limited — ✅.
- **DB:** migrations at head, CRUD, ownership, RLS deny-by-default, pgvector
  search — ✅. Security advisors: `grant_admin_role` RPC EXECUTE revoked
  (migration 0010; warnings cleared).
- **Frontend:** every page renders; charts; light/dark theme; responsive (no
  horizontal overflow at mobile); loading/error states; no console errors — ✅.
- **Bug found + fixed:** middleware guarded `/api/guest` and redirected the
  guest sign-in to `/login` (broke guest login) → excluded it + regression test.

### Testing

- Backend: `pytest -m "not slow and not db"` = **136 passed** (ruff/mypy/bandit
  clean); integration db-marked suite via pgvector Postgres.
- Frontend: `tsc` + `npm test` (3 `node:test` middleware-matcher regression
  tests) + `next build` — all green.
- CI (`.github/workflows/ci.yml`): backend / integration / frontend (adds
  `npm test`) / docker (full + slim torch-free) + kronos_src drift check.

## 7. Deployment (live)

```
Users → Vercel frontend → Render backend (slim, no torch) → Supabase
                                 ├→ HF Space ai-inference-service (Kronos + MiniLM)
                                 └→ Gemini/OpenAI · NewsAPI · yfinance
```

- **Frontend → Vercel** project `ai-financial-intelligence-platform` (team
  `eklavya-singh-rathores-projects`). **LIVE:**
  `https://ai-financial-intelligence-platf-eklavya-singh-rathores-projects.vercel.app`.
  Env: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`,
  `BACKEND_URL`, `GUEST_EMAIL`, `GUEST_PASSWORD` (`BACKEND_API_KEY` empty).
  Root Directory = `frontend`; Vercel Authentication disabled (app has its own auth).
- **Backend → Render** free web service `srv-d995r0faqgkc73fpjfsg`. **LIVE:**
  `https://stock-ai-backend-gv17.onrender.com` (Docker `backend/Dockerfile.render`,
  Singapore, `KRONOS_MODE`/`EMBEDDINGS_MODE=remote`). DATABASE_URL uses the
  Supabase **aws-1-ap-south-1 pooler** (IPv4). Runbook: `docs/deploy-render.md`.
- **Inference → HF Space** `Eklavya73/ai-inference-service` (private, Gradio
  SDK on ZeroGPU, CPU-only, no GPU quota). **LIVE:**
  `https://eklavya73-ai-inference-service.hf.space` (`/forecast` `/embed`
  `/health` + Gradio status page). Runbook: `docs/deploy-hf-space.md`.
- **Keep-alive:** GitHub Actions `keepalive.yml` (var `BACKEND_LIVE_URL`) pings
  Render `/live` every 10 min (verified green); backend scheduler pings the Space
  every 6 h.
- **Env reference:** `docs/environment.md`. Local dev unchanged (inference
  defaults to `local`). Expected delta vs localhost: first-request-after-idle
  latency only.

## 8. Remaining owner actions

1. **Rotate credentials shared during development:** Supabase DB password →
   new pooler `DATABASE_URL`; `GOOGLE_AI_STUDIO_API_KEY`, `OPENAI_API_KEY`,
   `NEWSAPI_KEY`; regenerate `API_KEY`; the **Render API key** and **HF write
   token** used this phase (replace HF with a fine-grained **read** token on the
   Space, set as `HF_TOKEN` in Render). Anon key is public by design.
2. Create least-privilege DB role `app_rw` (DML on app tables only) to replace
   the `postgres` app connection — SQL in `docs/deploy-render.md`.
3. Enable Supabase **leaked-password protection** (dashboard → Auth) and
   consider requiring email confirmation (currently open sign-up).
4. Optional: fund the OpenAI key or clear `LLM_FALLBACK_PROVIDER`; paste
   `SUPABASE_JWT_SECRET` into Render for faster JWT verification.
5. Optional: rotate the guest account password (regenerate + update Supabase +
   `GUEST_PASSWORD` in Vercel).

## 9. Phase 5 roadmap (next)

Durable job queue replacing `BackgroundTasks` (durable + scheduled autonomous
runs) · per-user LLM quotas · prompt registry/versioning · agent-quality
evaluation harness · additional data APIs (Twitter/X — the production Vercel URL
is the OAuth callback base) · multi-tenant RLS policies if SaaS is pursued.
*(Notifications: permanently removed.)*
