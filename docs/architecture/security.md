# Security Architecture

## Identity & roles

Two credential types resolve to one `AuthContext` (`app/core/auth.py`):

- **`X-API-Key`** (static `API_KEY`) → role **`service`** (admin-equivalent;
  automation, tests, the frontend proxy's local-dev fallback).
- **`Authorization: Bearer <supabase-jwt>`** → an authenticated user. Verified
  **locally** (HS256 via `SUPABASE_JWT_SECRET`, fast path) or **remotely**
  against `{SUPABASE_URL}/auth/v1/user` with a 60 s cache — so deployment never
  blocks on the dashboard-only JWT secret.

Role precedence: `service` > `admin` > `user`. `admin` is granted only to two
owner emails by a `BEFORE INSERT` trigger on `auth.users` (migration 0009).
`service`/`admin` see all rows; `user` sees only rows they own. With neither
credential configured (bare local dev), requests get an anonymous `service`
context — loudly warned at startup.

## Per-user isolation

`user_id` on `chat_sessions`, `agent_runs`, `backtests`, `forecasts`,
(Phase 5) `sim_portfolios`/`sim_orders`/`sim_trades`, and (Phase 6)
`watchlists`. The backend stamps the caller's id on write and filters by owner
on read; cross-user access returns `404`. Verified live with distinct users
(and with the guest account, which is an ordinary `user`). The Phase 6 admin
catalog-sync route (`POST /admin/catalog/sync`) is gated on `auth.privileged`
(`service`/`admin`) — it returns `403` for ordinary users.

## Guest access (Phase 4.6)

"Continue as Guest" authenticates a **dedicated, pre-provisioned guest Supabase
account** — no bypass:

- Sign-in happens **server-side** in `app/api/guest/route.ts` using server-only
  `GUEST_EMAIL` / `GUEST_PASSWORD`; the credentials never reach the browser.
- The guest is a normal `user` role (the admin trigger elevates only the two
  owner emails), so ownership isolation, RBAC, and validation all apply
  unchanged — guest sees only guest-owned data.
- The account is created pre-confirmed via SQL (`auth.users` + `auth.identities`,
  bcrypt password); the password is a strong random secret set as an env var
  (rotatable), never hard-coded.

## Database posture

- **RLS deny-by-default**: every `public` table has RLS enabled with no
  policies, locking the Supabase REST API. All access is mediated by the backend
  (connects as `postgres`, RLS-exempt) which enforces ownership in code. See
  [database.md](database.md).
- Migration `0010` revokes RPC `EXECUTE` on the `SECURITY DEFINER`
  `grant_admin_role()` function (it is trigger-only) — the Supabase linter
  warnings cleared.
- Least-privilege app DB role (`app_rw`) is a recommended owner action.

## Hardening (Phase 2.5, still in force)

Per-client rate limiting (`RATE_LIMIT_PER_MINUTE`), agent-run concurrency caps +
per-run timeouts + orphan sweep, CPU work off the event loop, session-rollback
discipline, pooler-safe asyncpg, non-root Docker, request-ID logging, Prometheus
metrics, prompt trust boundaries (`<untrusted-data>`), fail-closed risk
defaults, pinned dependencies, and `EXPOSE_ERROR_DETAILS=false` in production.

## Error-message hygiene

`SpaceClientError` and `ForecasterError` messages can surface in public `503`
details, so they are generic and **never contain tokens, URLs, or headers**;
specifics go to server logs only. Guest sign-in failures return a generic
message (never reveal whether the account exists).

## Secrets

All secrets come from environment variables (`.env` git-ignored; Vercel/Render/
Space/GitHub env stores). Publishable Supabase anon keys are public by design.
The Phase 6 provider keys (`FINNHUB_API_KEY`, `ALPHA_VANTAGE_API_KEY`) are
secrets — only placeholder tokens ship in `.env.example`/`render.yaml`
(`sync: false`), and every provider degrades to empty when its key is absent, so
the platform never depends on a committed key. See
[environment.md](../environment.md) for where each is set.

## Owner actions / known gaps

- Rotate every credential shared during development (DB password, LLM/News keys,
  Render API key, HF token → fine-grained read; regenerate `API_KEY`). Phase 6:
  set + rotate `FINNHUB_API_KEY` / `ALPHA_VANTAGE_API_KEY` as Render secrets.
- Enable Supabase leaked-password protection (dashboard setting).
- Create the least-privilege `app_rw` DB role.
- `vector` extension lives in `public` (accepted; low risk).
