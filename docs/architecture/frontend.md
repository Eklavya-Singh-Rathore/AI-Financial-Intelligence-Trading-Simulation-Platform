# Frontend Architecture

**Next.js 15** (App Router, TypeScript) + Tailwind v4 + TanStack Query +
TradingView `lightweight-charts` + `next-themes` (system-adaptive light/dark).
Deployed on Vercel (project root `frontend/`).

## Pages (`app/`)

| Route | Purpose |
|---|---|
| `/login` | Sign in / sign up (Supabase browser client) + **Continue as Guest** |
| `/` | Dashboard — 16-asset universe table with sparkline stats |
| `/instruments/[symbol]` | Candles + SMA/EMA overlays + forecast overlay (Kronos/baseline); SMA-crossover backtest with metric tiles; "Analyze with agents" |
| `/agents`, `/agents/[runId]` | Agent-run list + live-polling transcript & decision card |
| `/chat` | Persisted chat sessions with grounded, context-chipped answers |

Shared UI in `components/` (`Shell`, `CandleChart`, `RunBits`); API layer in
`lib/api.ts`; Supabase browser client in `lib/supabase.ts`.

## The authenticated backend proxy

The browser **never** calls the backend directly. All data goes through the
same-origin catch-all route `app/api/backend/[...path]/route.ts`:

- Reads the signed-in user's Supabase session server-side and forwards
  `Authorization: Bearer <jwt>` to `BACKEND_URL` (Render). Falls back to
  `X-API-Key` (`BACKEND_API_KEY`) only in local dev.
- `export const maxDuration = 300` — forecast/backtest/chat are single
  synchronous calls that may ride out a Render cold start + HF Space wake; 300 s
  is the Vercel Hobby+Fluid ceiling.
- Buffers the response (no streaming). Network failure → a neutral `502`.

Because the proxy holds the credentials server-side, the backend API key and
guest password never reach the browser.

## Auth flow

- `lib/supabase.ts` — browser client from `NEXT_PUBLIC_SUPABASE_URL` /
  `NEXT_PUBLIC_SUPABASE_ANON_KEY`. Sessions are cookie-based (`@supabase/ssr`).
- `middleware.ts` — server guard: `supabase.auth.getUser()` redirects
  signed-out visitors to `/login` (and signed-in visitors away from `/login`).
  **Matcher excludes `api/backend` and `api/guest`** (both must be reachable
  without a session — the proxy enforces its own auth, and the guest route
  establishes the session).
- **Guest** (`app/api/guest/route.ts`) — a server-side POST that signs in the
  shared guest account with server-only `GUEST_EMAIL`/`GUEST_PASSWORD` and sets
  the session cookies. A `GET` reports whether guest is configured so the button
  only shows when available. See [security.md](security.md).

## Data fetching & long operations

- TanStack Query with `retry: 1`, `refetchOnWindowFocus: false`,
  `staleTime: 30s`. `HealthDot` polls `/health` every 30 s.
- **Forecast/backtest/chat** are synchronous requests (loading → result/error).
- **Agent runs** are fire-and-poll: `POST /agents/run` → `202` + run id;
  the run/transcript pages poll every 2.5–3 s while the run is live. This keeps
  a multi-minute, 7-LLM-call pipeline off any single long HTTP request.
- Errors surface inline (e.g. a rate-limited LLM renders "the assistant is
  temporarily unavailable"); the guest and normal users share these paths.

## Checks

`npm run typecheck` (tsc), `npm run build` (next build), and `npm test`
(`node:test`, zero extra deps) — the last currently covers the middleware
matcher regression (guest/proxy routes must bypass the guard). CI runs all
three (Node 22).
