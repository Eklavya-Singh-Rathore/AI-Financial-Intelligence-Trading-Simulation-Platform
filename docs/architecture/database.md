# Database Architecture

**Supabase Postgres 17** (project `ai-stock-prediction`, `rekoawsoghrjcimknkfz`,
ap-south-1) with the **pgvector** extension. The backend connects with async
SQLAlchemy 2 + asyncpg; on Render it uses the **Supabase pooler** URL
(`aws-1-ap-south-1.pooler.supabase.com:6543`) because Render egress is IPv4-only
and direct hosts are IPv6-only.

## Schema ownership

The project **adopts** a pre-existing market-data warehouse and adds its own
owned tables. Migrations are Alembic, applied to Supabase with
`alembic_version` stamped in lockstep. **Head: `0016_stop_limit`** (Phase 6.5
widened `sim_orders.order_type` to `VARCHAR(16)` for the `stop_limit` type).

| Group | Tables |
|---|---|
| Market data (adopted, read) | `instruments` (curated Nifty-100 + on-demand, incl. `sector_id`/`industry_id` classification FKs), `price_bars`, `data_providers`, `instrument_provider_mappings`, `exchanges`, and the warehouse tables |
| Project-owned | `forecasts`, `backtests`, `agent_runs` (+`idempotency_key`, +`context_snapshot`), `agent_messages`, `chat_sessions`, `chat_messages` |
| Paper trading (Phase 5) | `sim_portfolios` (one per owner, unique over `COALESCE(user_id, zero-uuid)`), `sim_orders`, `sim_trades`, `sim_positions` |
| Research (Phase 5) | `instrument_fundamentals` (yfinance JSONB cache, TTL), `research_documents` (news corpus, `content_hash` dedupe, `vector(384)`) |
| Market expansion (Phase 6) | `watchlists`, `watchlist_items` (per-user, `0014`); `ingest_jobs` (durable track/backfill queue: status queued/running/done/error, `0015`) |
| Semantic memory | `agent_embeddings` (`vector(384)`, pgvector) |

## Migration history (Alembic)

`0004_warehouse` (baseline) → `0005_forecasts_backtests` → `0006_agent_runs` →
`0007_hardening` → `0008_chat` → `0009_user_ownership` (per-user `user_id` +
admin-grant trigger) → `0010_revoke_admin_execute` (revoke RPC EXECUTE on
the `SECURITY DEFINER` trigger function) → `0011_simulation` (paper-trading
tables) → `0012_research` (fundamentals cache + news-RAG corpus) →
`0013_run_context` (`agent_runs.context_snapshot` for explainability) →
`0014_watchlists` (per-user watchlists) → `0015_ingest_jobs` (durable
whole-market track/backfill queue) → **`0016_stop_limit`** (Phase 6.5: widen
`sim_orders.order_type` to `VARCHAR(16)` for the stop-limit order type).

Migrations run manually (`cd backend && alembic upgrade head`) from a dev
machine or CI; never at app boot. CI's integration job applies the full chain
against a fresh `pgvector/pgvector:pg17` container, so every migration is
proven to apply on vanilla Postgres (Supabase-only objects are guarded with
existence checks — e.g. the `auth.users` trigger and the `anon`/`authenticated`
roles).

## Per-user ownership (migration 0009)

`user_id UUID` (nullable, indexed) on `chat_sessions`, `agent_runs`,
`backtests`, `forecasts`, (Phase 5) `sim_portfolios`/`sim_orders`/`sim_trades`,
and (Phase 6) `watchlists`. On write the backend stamps the caller's `user_id`;
on read, non-privileged callers are filtered to their own rows
(`AuthContext.owner_filter_id()`), cross-user access returns `404`, and legacy
`NULL` rows are visible only to `admin`/`service`. Guest accounts are ordinary
`user`s, so isolation applies to them unchanged. See [security.md](security.md).

## RLS: deny-by-default

Every `public` table has **RLS enabled with no policies**. This is intentional:
it locks down the Supabase auto-generated PostgREST/REST API so nothing can read
or write the database directly with the anon/authenticated keys. **All data
flows through the backend**, which connects as the `postgres` role (RLS-exempt)
and enforces ownership in application code. The Supabase linter reports these as
`rls_enabled_no_policy` (INFO) — expected for this architecture, not a defect.

## pgvector / semantic memory & news RAG

`agent_embeddings.embedding vector(384)` stores MiniLM
(`all-MiniLM-L6-v2`) sentence embeddings. Recall is cosine-distance KNN in SQL
(`embedding.cosine_distance(query)` ordered/limited), scoped to a symbol's runs
for the agent orchestrator and universe-wide for chat. Embeddings are computed
locally (dev) or on the HF Space (`EMBEDDINGS_MODE=remote`, production) — same
model, identical 384-d vectors. A TTL sweep purges embeddings older than
`MEMORY_TTL_DAYS`.

`research_documents` (Phase 5) uses the same 384-d vectors for the news
corpus: headlines dedupe on `content_hash` (sha256 of title|url), embed in
batch (rows keep `embedding=NULL` when embeddings are unavailable and are
excluded from KNN), and are purged past `NEWS_RETENTION_DAYS`. News is a
shared, non-user-scoped corpus (public headlines) by design.

## Fresh-DB bootstrap

A brand-new database loads `scripts/base_schema.sql` (the adopted warehouse
schema) before `alembic upgrade head` applies the project tables on top. CI and
docker-compose do this automatically; migration `0005` guards with a clear
error if the base schema is missing.

## Known advisories (accepted)

- `extension_in_public` (vector) — pre-existing; moving schemas risks breaking
  column type references; low risk, deferred.
- `auth_leaked_password_protection` disabled — a Supabase Auth dashboard setting
  (owner action), not code.
