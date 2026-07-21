# ADR-0002: Authentication via Supabase Auth + backend JWT verification

- **Status:** Accepted
- **Date:** 2026

## Context

The platform became multi-user and needs per-user data isolation, plus a
service credential for automation/tests, without running a bespoke identity
service. The DB and Auth already live on Supabase.

## Decision

Use **Supabase Auth** (email+password, open sign-up) for user identity. The
backend accepts two credentials on every business route:

- `Authorization: Bearer <supabase-jwt>` — verified **locally** (HS256 via
  `SUPABASE_JWT_SECRET`) when configured, else **remotely** against
  `/auth/v1/user` with a 60 s cache. Deployment never blocks on the JWT secret.
- `X-API-Key` → a `service` (admin-equivalent) context.

Roles come from JWT `app_metadata.role`; `admin` is granted to two owner emails
by a DB trigger. Ownership is enforced in application code (`owner_filter_id`),
and the Supabase REST API is locked by RLS deny-by-default. **Guest** access
signs in a dedicated `user`-role account **server-side** (credentials never hit
the browser) — [ADR is realized in](../architecture/security.md).

## Consequences

- **+** No custom auth service; JWTs verifiable offline or online; the frontend
  proxy forwards the Bearer token so the browser holds no backend secret.
- **+** Guest = a normal user → isolation/RBAC apply with zero special-casing.
- **−** Remote verification adds a cached network hop when the JWT secret is
  unset. The admin allow-list is hard-coded in a migration (fine for this scope).
- **−** Open sign-up + no funded LLM fallback means public exposure has cost/abuse
  surface; mitigated by rate limits and run caps, revisited later.
