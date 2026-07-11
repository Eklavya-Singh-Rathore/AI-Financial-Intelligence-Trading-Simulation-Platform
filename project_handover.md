# project_handover.md

> **Single source of truth for resuming development** — self-contained; no prior
> conversations needed. Last updated: **2026-07-11, Phase 4.5**
> (deployment migration: Render backend + Hugging Face inference Space).

## 1. What this is

**AI Financial Intelligence Trading Simulation Platform** — decision-support
(NO real trading) for a fixed 16-asset Indian-market universe (NIFTY 50, Sensex,
gold/silver ETFs, 12 NSE blue-chips). Ingests daily OHLCV, computes indicators,
forecasts with the vendored **Kronos** foundation model, backtests on
**NautilusTrader**, runs a 7-agent LLM pipeline (Gemini) producing risk-limited
recommendations, and serves a **multi-user** Next.js dashboard + grounded chat.

- Repo: https://github.com/Eklavya-Singh-Rathore/AI-Financial-Intelligence-Trading-Simulation-Platform
- DB/Auth: Supabase **`ai-stock-prediction`** (`rekoawsoghrjcimknkfz`, ap-south-1, PG 17)
- Docs: `README.md`, `AUDIT_REPORT.md` (historical audit), `docs/deploy-render.md`,
  `docs/deploy-hf-space.md`, `docs/environment.md`
- **Notifications are permanently out of scope** (owner decision, Phase 4).

## 2. Phase history (commits on `main`)

| Phase | Commits | Delivered |
|---|---|---|
| 1 | `a6b86d5`,`71aa32a` | FastAPI core, yfinance→`price_bars` ingestion, indicators, Forecaster/Backtester registries, APScheduler, migrations 0004-baseline/0005, CI, Docker |
| 2 | `fa9f49d` | LLM layer (Gemini primary/OpenAI fallback/fake), 7-agent TradingAgents-style pipeline w/ coded hard risk limits, NewsAPI, MiniLM semantic memory (`agent_embeddings`, 384-d), agents API, migration 0006 |
| 2.5 | `7e8fc60` | Full audit remediation: API-key auth, rate limiting, run concurrency caps + timeouts + orphan sweep, CPU work off event loop, rollback discipline, failover normalization + rate-limit backoff, pooler-safe asyncpg, requirements.lock, hardened non-root Docker, Prometheus metrics + request IDs, prompt trust boundaries, fail-closed risk, migration 0007, DB-integration suite + `scripts/base_schema.sql` |
| Kronos | `a284557` | Vendored `app/ml/kronos_src/` (MIT; one relative-import fix); `model=kronos` verified live |
| 3 | `9b0aeed`,`89b478b`,`a0c3976`,`95c2034` | **First live verification** (11,844 bars, live Kronos forecast, live Nautilus backtest, first completed agent run — drawdown veto fired) + 5 live-found bug fixes; `/instruments/summary`; persisted chat + RAG (migration 0008); Next.js frontend (dashboard/candles+forecast overlay/backtest UI/agent transcripts/chat), auth proxy, both themes |
| 4 | `33ffb60` | **Supabase Auth + JWT + RBAC + per-user isolation** (migration 0009), open sign-up, login UI + session middleware, GitHub push, Vercel frontend deploy, (superseded) Oracle backend runbook |
| 4.5 | this phase | **Deployment migration**: `RemoteKronosForecaster` + remote MiniLM via a private HF Space (`ai-inference-service`), reusable `space_client` (retries/wake handling/structured errors), `KRONOS_MODE`/`EMBEDDINGS_MODE` toggles, slim torch-free Render image (`Dockerfile.render` + `requirements-deploy.lock`), `render.yaml`, keepalive workflow, proxy `maxDuration=300`, docs replace the Oracle runbook |

## 3. Architecture (stable since audit; Phase 4.5 adds remote inference)

`api/routers` → `services` → (`ml` | `backtesting` | `llm` | `agents`) →
`models`/`db` (async SQLAlchemy → Supabase). Registries select implementations.
**Inference modes (4.5):** `KRONOS_MODE`/`EMBEDDINGS_MODE` = `local` (in-process
torch, dev default; needs `pip install -e .[dev,local-ml]`) or `remote`
(production): `app/services/space_client.py` calls the HF Space with bounded
retries, a 503 "Space waking" poll path, and generic token-free errors;
failures keep the existing contracts (API 503, orchestrator → baseline
fallback, embeddings → memory-off). The public forecaster name stays `kronos`
in both modes, so API params and persisted `model_name` match localhost.
Agent pipeline: deterministic gather → technical + news analysts → bull/bear
debate → trader → risk manager (**coded limits only tighten**: size cap,
drawdown veto, missing-evidence halving) → portfolio manager; every step
persisted (`agent_messages`), memory embedded for RAG recall. Chat grounds
answers in live stats + recent decisions + semantic memory inside
`<untrusted-data>` boundaries. Frontend (Next.js 15) reaches the backend only
through `app/api/backend/[...path]` which forwards the user's Supabase Bearer
token (or `BACKEND_API_KEY` in local dev); the proxy sets `maxDuration = 300`
for the synchronous forecast/backtest/chat calls.

## 4. Auth model (Phase 4) — unchanged

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
  seeded users.

## 5. Database — unchanged this phase

Alembic head **`0009_user_ownership`** (all migrations applied to Supabase).
Project-owned tables: `forecasts`, `backtests`, `agent_runs`(+idempotency_key),
`agent_messages`, `chat_sessions`, `chat_messages` (+`user_id` on the four
owned tables). Adopted pre-existing: `instruments` (16), `price_bars`
(**11,844+ real bars**), `data_providers`, `instrument_provider_mappings`
(TATAMOTORS→`TMPV.NS` post-demerger), `exchanges/...`, `agent_embeddings`
(pgvector 384). Fresh-DB bootstrap: `scripts/base_schema.sql`. Migrations stay
**manual** (`alembic upgrade head` from a dev machine; Render free tier has no
shell/pre-deploy hooks).

## 6. Status snapshot (2026-07-11)

- **Backend code:** remote-inference core in place; fast suite **135 passed**
  (was 106) incl. space-client taxonomy (503-wake, retries, token-leak guard),
  remote-forecaster contract, registry mode switch, remote-embeddings degrade;
  ruff/mypy clean; frontend `tsc` + `next build` clean.
- **CI:** adds a kronos_src drift check (backend copy ↔ Space copy) and a slim
  Render image build asserting it boots **torch-free**.
- **AI:** Gemini `gemini-2.5-flash` primary (free tier — 429s absorbed by 35s
  backoff); OpenAI fallback key has **no quota** (dead until funded); Kronos +
  Nautilus verified live on real data (Phase 3).
- **Deployment:** frontend live on Vercel; HF Space + Render deployment
  executed in Phase 4.5 — URLs + verification results in §7.

## 7. Deployment (Phase 4.5 architecture)

```
Users → Vercel frontend → Render backend (slim, torch-free) → Supabase
                                   ├→ HF Space ai-inference-service (Kronos + MiniLM)
                                   └→ Gemini/OpenAI · NewsAPI · yfinance
```

- **Frontend → Vercel** (root `frontend/`; owner's personal Vercel account).
  Env: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`,
  **`BACKEND_URL` = the Render URL** (leave `BACKEND_API_KEY` empty in prod).
- **Backend → Render free web service** (Docker `backend/Dockerfile.render`,
  blueprint `render.yaml`, region Singapore, health `/live`, auto-deploy from
  `main`). Runbook + free-tier evaluation: `docs/deploy-render.md`.
  Backend URL: `https://stock-ai-backend.onrender.com` *(confirm in the Render
  dashboard if the service name was adjusted at create time)*.
- **Inference → HF Space** `Eklavya73/ai-inference-service` (private, Docker,
  CPU Basic free): official Kronos (`NeoQuasar/Kronos-small` +
  `Kronos-Tokenizer-base`) + MiniLM, weights baked into the image at build,
  endpoints `/forecast` `/embed` `/health`. Runbook: `docs/deploy-hf-space.md`.
  URL: `https://eklavya73-ai-inference-service.hf.space`.
- **Keep-alive:** GH Actions `keepalive.yml` pings backend `/live` every
  10 min (repo variable `BACKEND_LIVE_URL`); the backend scheduler pings the
  Space every 6 h (`space_keepalive`). Without the ping, Render free sleeps
  after 15 idle minutes and the 13:00 UTC ingest is silently skipped.
- **Env reference:** `docs/environment.md` (every variable, where set,
  secret-or-not).
- **Local dev unchanged:** uvicorn :8000 + `npm run dev` :3000; inference
  modes default to `local`.
- **Expected behavioral delta vs localhost:** only latency — first request
  after an idle window (if keepalive missed) rides a ~1 min Render wake and/or
  a Space 503-wake poll; the proxy budget (300 s) absorbs it.

## 8. Security posture & owner actions

1. **Rotate ALL dev credentials** (shared during development, compromised by
   definition): Supabase **DB password** (→ new `DATABASE_URL`),
   `GOOGLE_AI_STUDIO_API_KEY`, `OPENAI_API_KEY`, `NEWSAPI_KEY`, **the Render
   API key used for Phase 4.5 automation**, and regenerate `API_KEY`. The anon
   key is public by design.
2. **HF token:** create a fine-grained token with **read** access to the
   `ai-inference-service` Space only; set as `HF_TOKEN` in Render (and in the
   local `.env` when testing remote mode from a dev machine).
3. Create least-privilege DB role (replace `postgres` app connection):
   `CREATE ROLE app_rw LOGIN PASSWORD '...'; GRANT SELECT,INSERT,UPDATE,DELETE
   ON price_bars,forecasts,backtests,agent_runs,agent_messages,chat_sessions,
   chat_messages,agent_embeddings TO app_rw; GRANT SELECT ON instruments,
   data_providers,instrument_provider_mappings,exchanges TO app_rw;`
4. Optional: paste `SUPABASE_JWT_SECRET` into Render env (faster local JWT
   verification). 5. Fund the OpenAI key or clear `LLM_FALLBACK_PROVIDER`.
6. Rate limiting + agent-run caps are ON; `EXPOSE_ERROR_DETAILS=false` in prod.

## 9. Phase 5 roadmap (next)

Job queue replacing BackgroundTasks (durable runs) · per-user LLM quotas ·
scheduled autonomous runs (needs queue + alerting) · prompt registry/versioning ·
agent-quality evaluation harness · additional data APIs (Twitter/X etc. — the
production URL from Vercel is the OAuth callback base) · multi-tenant RLS
policies if SaaS ever pursued. *(Notifications: permanently removed.)*
