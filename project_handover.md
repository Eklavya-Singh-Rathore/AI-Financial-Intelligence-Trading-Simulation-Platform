# project_handover.md

> **Single source of truth for resuming development.** Complete enough that a
> new engineer or AI assistant can continue without prior conversations.
> Last updated: **2026-07-07** — Phase 2.5 (hardening & audit remediation) complete;
> Kronos forecaster vendored and verified end-to-end.

## 1. Project overview

**AI Financial Intelligence Platform** — decision-support system (NO real
trading) for a fixed 16-asset Indian-market universe (NIFTY 50, Sensex,
gold/silver ETFs, 12 NSE blue-chips). It ingests daily OHLCV, computes
technical indicators, forecasts prices, backtests strategies on NautilusTrader,
and runs a multi-agent LLM pipeline that produces an explainable, risk-limited
trade recommendation.

- **Working directory:** `D:\Claude Sessions\Stock` (backend in `backend/`, local git repo, branch `main`)
- **Database:** Supabase project **`ai-stock-prediction`** (ref `rekoawsoghrjcimknkfz`, region ap-south-1, Postgres 17)
- **Original planning doc:** `deep-research-report (1).md` (git-ignored — contains development API keys)
- **Audit:** `AUDIT_REPORT.md` (2026-07-07, score 57/100 pre-hardening; authoritative issue list)

## 2. Completed phases

| Phase | Content | Commit(s) |
|---|---|---|
| 1 | FastAPI backend, ingestion→`price_bars`, indicators, Forecaster/Backtester registries (baseline + NautilusTrader 1.230), APScheduler, migrations 0004-baseline/0005, CI, Docker | `a6b86d5`, `71aa32a` |
| 2 | Multi-agent system: LLM layer (Gemini primary/OpenAI fallback/fake), TradingAgents-inspired pipeline, NewsAPI, MiniLM semantic memory, agents API, migration 0006 | `fa9f49d` |
| 2.5 | **Engineering hardening — every applicable audit finding remediated** (this update) | working tree |

## 3. Audit remediation status (Phase 2.5)

**Implemented (Code/Config fixes):**

| Audit ID | Fix | Where |
|---|---|---|
| CRIT-1 | X-API-Key auth on all business routes (+`/api/v1` alias), fixed-window per-IP rate limiting, startup warning when auth disabled | `app/core/security.py`, `app/main.py` |
| CRIT-2 | All CPU/model work off the event loop via `asyncio.to_thread` (Nautilus run, forecaster inference, MiniLM encode/load) | `services/backtest_service.py`, `services/forecast_service.py`, `services/embeddings.py` |
| HIGH-1 | Whole provider interaction normalized to `LLMError` (incl. `.text`/`.choices` access); failover normalizes foreign exceptions | `app/llm/gemini_client.py`, `openai_client.py`, `registry.py` |
| HIGH-2 | `session.rollback()` in ingest error path (poisoned-session cascade fixed) | `services/data_ingest.py` |
| HIGH-3 | Failure path rolls back (fresh-session fallback), per-run `asyncio.wait_for` timeout, startup `sweep_orphaned_runs()` | `agents/orchestrator.py`, `app/main.py` |
| HIGH-4 | Concurrency guard (429), per-symbol in-flight dedup (409) | `api/routers/agents.py` |
| HIGH-5 | Least-privilege DB roles documented (infra step — see §10) | `.env.example`, this file |
| HIGH-6 | Pooler auto-detect → asyncpg `statement_cache_size=0`; `DB_STATEMENT_CACHE_SIZE` override | `app/db/base.py` |
| HIGH-7 | `backend/requirements.lock` (112 pins, pip-freeze), CI installs from lock, Dependabot, bandit (blocking) + pip-audit (advisory) in CI | `requirements.lock`, `.github/*` |
| HIGH-8 | `.dockerignore`, explicit COPY, pinned install, non-root `appuser`, HEALTHCHECK on `/live` | `backend/Dockerfile`, `backend/.dockerignore` |
| MED-1 | Headlines/memory rendered in `<untrusted-data>` trust boundaries, delimiter-injection stripped, preamble rule | `agents/context.py`, `agents/base.py` |
| MED-2 | Risk fails CLOSED: missing backtest evidence → size halved + `missing_evidence` flag | `agents/risk.py` |
| MED-3 | Run errors sanitized unless `EXPOSE_ERROR_DETAILS=true` (curated messages pass) | `api/routers/agents.py` |
| MED-4 | Ingest mutex (409 on concurrent) + `background=true` mode (202-style) | `api/routers/ingest.py` |
| MED-5 | Postgres advisory lock makes the daily job single-flight across replicas | `scheduler/jobs.py` |
| MED-6 | DB-integration suite (`tests/test_db_integration.py`, `db` marker) + CI Postgres job | `.github/workflows/ci.yml` |
| MED-7 | Request-ID middleware (structlog-bound, echoed header), `exc_info=True` logging, Prometheus `/metrics` + run/token/duration metrics | `core/middleware.py`, `core/metrics.py`, `main.py` |
| MED-8 | `scripts/base_schema.sql` bootstrap (CI + compose auto-load) + 0005 precondition guard with clear error | `scripts/`, `alembic/versions/0005*` |
| MED-9 | `/api/v1` dual mount (non-breaking) + `Idempotency-Key` on `POST /agents/run` (DB-backed, unique index) | `main.py`, `api/routers/agents.py`, migration 0007 |
| MED-10 | Retry classification (`LLMError.retryable`), backoff+jitter, non-retryable skips straight to fallback | `app/llm/base.py`, `registry.py` |
| LOW-1 | NewsAPI key moved to `X-Api-Key` header | `services/news.py` |
| LOW-2 | Memory search symbol-partitioned (join via runs), TTL purge (`MEMORY_TTL_DAYS`, on startup sweep), DB unique dedupe index | `services/embeddings.py`, migration 0007 |
| LOW-3 | CORS configurable via `CORS_ORIGINS` (empty = off) | `main.py` |
| LOW-4 | `/prices` bounded (`limit` param, default 10 000, most-recent kept) | `api/routers/instruments.py` |
| LOW-5 | Typed `SmaCrossoverParams` (same JSON shape; validates at the boundary) | `schemas/backtest.py` |
| LOW-7 | Per-hit UUID guard in memory recall | `agents/orchestrator.py` |
| LOW-8 | `/live` (no deps) added; `/health` remains readiness | `main.py` |

**Deferred (with reasons):**

| Item | Reason | Dependency | Recommended phase |
|---|---|---|---|
| Real authn/z (JWT/Supabase Auth, roles, per-user quotas) | Needs identity design + user store; API-key stopgap in place | Product decision | Phase 4 (per roadmap) |
| Job queue replacing BackgroundTasks | Architectural change explicitly out of Phase 2.5 scope | Queue choice (PG-backed vs Redis) | Phase 3/4 |
| Least-privilege DB roles (HIGH-5 execution) | Requires DBA action on Supabase; SQL documented in §10 | Owner/DBA | Before production |
| Prompt registry/versioning (TD-5) | Improvement, not an audit defect | — | Phase 3 |
| LOW-6 dual migration bookkeeping | Process discipline, documented in §7 | — | ongoing |

## 4. Architecture (unchanged by 2.5 — hardened in place)

Modular monolith. `api/routers` → `services` → (`ml` | `backtesting` | `llm` |
`agents`) → `models`/`db`. Registries select implementations
(forecaster: kronos/baseline; backtester: nautilus/simple; LLM:
gemini/openai/fake with failover). The agent pipeline gathers all data
deterministically, then: technical analyst → news analyst → bull/bear debate →
trader → risk manager (LLM + **coded hard limits that only tighten**) →
portfolio manager. Every step persisted to `agent_messages`; final decision +
token usage on `agent_runs`.

## 5. Technology stack

Python 3.12 · FastAPI 0.139 · SQLAlchemy 2 async + asyncpg · Alembic ·
Supabase Postgres 17 + pgvector 0.8 · pandas 3 / numpy 2.5 · nautilus_trader
1.230 · torch 2.12 · sentence-transformers (MiniLM-L6-v2, 384-dim) ·
google-genai (gemini-2.5-flash) · openai (gpt-4o-mini fallback) ·
prometheus-fastapi-instrumentator · structlog · APScheduler · pytest/ruff/mypy.
**All pinned in `backend/requirements.lock`.**

## 6. API status

Mounted at `/` (legacy) and `/api/v1` (canonical). API-key protected when
`API_KEY` set; `/live`, `/health`, docs always open.

- `GET /live`, `GET /health`, `GET /metrics`
- `GET /instruments`, `GET /instruments/{s}/prices?limit=`, `.../indicators`, `.../forecast`
- `POST /ingest/run` (mutex; `background=true` supported)
- `POST /backtest` (typed params)
- `POST /agents/run` (202; `Idempotency-Key`; 409 in-flight dup; 429 at cap),
  `GET /agents/runs`, `GET /agents/runs/{id}`, `GET /agents/runs/{id}/messages`

## 7. Database status

- Alembic head **`0007_hardening`** — applied to Supabase (0005, 0006, 0007 all
  applied via Supabase MCP; `alembic_version` stamped in lockstep — keep both
  bookkeeping systems in sync when applying DDL outside Alembic).
- Project-owned tables: `forecasts`, `backtests`, `agent_runs`
  (+`idempotency_key` unique), `agent_messages`; RLS enabled on all.
- Pre-existing base schema (prior repo): `instruments` (16 seeded),
  `price_bars`, `data_providers`, `instrument_provider_mappings`,
  `exchanges/sectors/industries`, `agent_embeddings` (+ new dedupe unique
  index), `warehouse_*`.
- Fresh-DB bootstrap: `scripts/base_schema.sql` (CI service container and
  docker-compose load it automatically; 0005 guards with a clear error if the
  base schema is missing).

## 8. AI/Agent status

- Gemini (`gemini-2.5-flash`) **live-verified**; OpenAI fallback key has **no
  quota (429 insufficient_quota)** — failover logic tested with fakes; supply a
  funded key for a working fallback.
- NewsAPI **live-verified** (headlines flow; key now sent via header).
- Semantic memory: symbol-partitioned recall, TTL purge, dedupe index; MiniLM
  loads lazily off the event loop; memory-off degradation preserved.
- Kronos forecaster: **vendored and working end-to-end** (2026-07-07). Source
  under `app/ml/kronos_src/model/` (github.com/shiyu-coder/Kronos, MIT — see
  `kronos_src/NOTICE.md`; one local change: relative-import fix). Weights pull
  from HF (`NeoQuasar/Kronos-small` + `-Tokenizer-base`) on first use, cached
  after. Verified: a real CPU forecast returns 5 predictions in ~23 s (cold).
  `model=kronos` is the default forecaster; baseline remains the automatic
  fallback if the model can't load. Slow-marked test:
  `test_kronos_forecast_end_to_end`.

## 9. Testing status

- **89 fast tests** (unit; network/DB-free; ~1 s) + **7 DB-integration tests**
  (`-m db`; CI Postgres job bootstraps base schema + migrations; cover
  migration presence, upsert idempotency, HIGH-2 session recovery, full
  fake-LLM pipeline vs real DB, orphan sweep, idempotency-key replay) + 3
  slow-marked local tests (Nautilus e2e, MiniLM dims, kronos gating).
- ruff clean, mypy clean (68 files), bandit in CI (blocking, `-ll`), pip-audit
  advisory.
- **Unable to verify locally:** the `db`/CI jobs (no Docker locally, repo has
  no GitHub remote yet, and `DATABASE_URL` is empty) — they are written to run
  green in CI; first push will prove them.

## 10. Security status

- API key auth + rate limiting + concurrency caps: **in place** (set `API_KEY`!).
- Error sanitization, request-IDs, non-root container, pinned deps: in place.
- **Before any deployment (owner actions):**
  1. **Rotate every key** in `.env` / the planning doc (all were shared for dev).
  2. Create least-privilege DB roles (HIGH-5):
     `CREATE ROLE app_rw LOGIN PASSWORD '...'; GRANT SELECT,INSERT,UPDATE,DELETE ON
     price_bars, forecasts, backtests, agent_runs, agent_messages, agent_embeddings TO app_rw;
     GRANT SELECT ON instruments, data_providers, instrument_provider_mappings, exchanges TO app_rw;`
     — app uses `app_rw`, migrations keep an elevated role.
  3. Supply a funded OpenAI key (or disable fallback).
  4. Confirm Supabase backup/PITR posture (**Unable to verify from code**).

## 11. Deployment status

Not deployed. Docker image hardened; compose stack now self-bootstraps a local
DB. Backend needs a container host (Fly/Render/Cloud Run/ECS) — it does NOT fit
Vercel serverless (torch + nautilus + scheduler). No GitHub remote configured;
CI exists but has never run remotely.

## 12. Milestones

- **Current:** Phase 2.5 complete — all applicable audit findings remediated;
  production readiness gates reduced to: runtime verification (needs
  `DATABASE_URL`), key rotation, DB roles, first CI run, Kronos vendoring
  (optional).
- **Next recommended:** Runtime verification end-to-end against Supabase, then
  **Phase 3** — Next.js dashboard + chat interface (Vercel), CORS origins,
  SSE/polling on run progress; queue extraction when adding scheduled
  autonomous runs.

## 13. Runtime verification — DONE (2026-07-07, Phase 3 step 0)

`DATABASE_URL` supplied by owner and wired into `.env`. First live results:
- **Ingest:** 16/16 instruments, **11,844 bars** (3y daily). TATAMOTORS demerger
  handled: yfinance mapping updated to successor **TMPV.NS** (registry data fix).
- **Read path:** prices + indicators live; **Kronos forecast on real data** works;
  **NautilusTrader backtest** works (RELIANCE 10/30 SMA: −4.77%, maxDD −28.2%).
- **First live agent run COMPLETED** (TCS, 7 Gemini calls, 12k tokens): decision
  `HOLD 0%` via **drawdown_veto** — the coded risk limits fired in production.
- `pytest -m db` green against Supabase (4 passed, 2 fake-LLM skips).

**Bugs found & fixed by live verification** (the audit's "unable to verify" was right):
1. `Instrument.status/instrument_type` mapped as String vs PG enum → asyncpg
   `operator does not exist` (fixed: ENUM(create_type=False)).
2. Nautilus drawdown/Sharpe measured CASH not equity (−96% fake DD) → replaced
   with mark-to-market equity curve from fills × bar closes.
3. Backtests ran on RAW prices → corporate-action cliffs (RELIANCE 1:1 bonus)
   corrupted results; backtests now use adjusted OHLC.
4. Gemini free-tier 429 mid-pipeline with useless 1.5s retry → rate-limit-aware
   backoff (35s+, extra attempt) in the failover client.
5. ORM access after rollback in ingest error path → MissingGreenlet cascade
   (ingest loop now uses plain values snapshot).

## Outstanding prerequisites

1. **Funded OpenAI key** for a real fallback provider (optional; Gemini free
   tier is tight — a paid tier would remove 429 stalls).
2. **GitHub remote + first push** to activate CI.

## 14. Future roadmap

Phase 3: frontend + chat (LibreChat-inspired), run-progress streaming.
Phase 4: real auth (Supabase Auth/JWT, roles), notifications, job queue.
Phase 5: multi-user/multi-tenant (tenant columns + forced RLS policies),
evaluation harness for agent decision quality, model-serving isolation.
