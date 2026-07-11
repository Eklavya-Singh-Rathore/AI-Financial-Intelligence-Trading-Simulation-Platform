# Database Architecture

**Supabase Postgres 17** (project `ai-stock-prediction`, `rekoawsoghrjcimknkfz`,
ap-south-1) with the **pgvector** extension. The backend connects with async
SQLAlchemy 2 + asyncpg; on Render it uses the **Supabase pooler** URL
(`aws-1-ap-south-1.pooler.supabase.com:6543`) because Render egress is IPv4-only
and direct hosts are IPv6-only.

## Schema ownership

The project **adopts** a pre-existing market-data warehouse and adds its own
owned tables. Migrations are Alembic, applied to Supabase with
`alembic_version` stamped in lockstep. **Head: `0010_revoke_admin_execute`.**

| Group | Tables |
|---|---|
| Market data (adopted, read) | `instruments` (16), `price_bars` (~11,800+ real bars), `data_providers`, `instrument_provider_mappings`, `exchanges`, and the warehouse tables |
| Project-owned | `forecasts`, `backtests`, `agent_runs` (+`idempotency_key`), `agent_messages`, `chat_sessions`, `chat_messages` |
| Semantic memory | `agent_embeddings` (`vector(384)`, pgvector) |

## Migration history (Alembic)

`0004_warehouse` (baseline) → `0005_forecasts_backtests` → `0006_agent_runs` →
`0007_hardening` → `0008_chat` → `0009_user_ownership` (per-user `user_id` +
admin-grant trigger) → **`0010_revoke_admin_execute`** (revoke RPC EXECUTE on
the `SECURITY DEFINER` trigger function).

Migrations run manually (`cd backend && alembic upgrade head`) from a dev
machine or CI; never at app boot. CI's integration job applies the full chain
against a fresh `pgvector/pgvector:pg17` container, so every migration is
proven to apply on vanilla Postgres (Supabase-only objects are guarded with
existence checks — e.g. the `auth.users` trigger and the `anon`/`authenticated`
roles).

## Per-user ownership (migration 0009)

`user_id UUID` (nullable, indexed) on `chat_sessions`, `agent_runs`,
`backtests`, `forecasts`. On write the backend stamps the caller's `user_id`;
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

## pgvector / semantic memory

`agent_embeddings.embedding vector(384)` stores MiniLM
(`all-MiniLM-L6-v2`) sentence embeddings. Recall is cosine-distance KNN in SQL
(`embedding.cosine_distance(query)` ordered/limited), scoped to a symbol's runs
for the agent orchestrator and universe-wide for chat. Embeddings are computed
locally (dev) or on the HF Space (`EMBEDDINGS_MODE=remote`, production) — same
model, identical 384-d vectors. A TTL sweep purges embeddings older than
`MEMORY_TTL_DAYS`.

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
