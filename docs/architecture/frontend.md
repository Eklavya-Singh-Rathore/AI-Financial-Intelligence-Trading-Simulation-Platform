# Frontend Architecture

**Next.js 15** (App Router, TypeScript) + Tailwind v4 + TanStack Query +
TradingView `lightweight-charts` + `next-themes` (system-adaptive light/dark).
Deployed on Vercel (project root `frontend/`). **Phase 6** adds a CSS-var
**design-token system** and a hand-built primitive library (`components/ui/*` —
Card, Stat, Table, Badge, Button, Input, Select, Tabs, Sheet, EmptyState,
Skeleton, Spinner), a responsive **app shell** with a mobile drawer, a Cmd/Ctrl-K
**command palette**, and a site-wide **floating AI assistant**.

## Pages (`app/`)

| Route | Purpose |
|---|---|
| `/login` | Sign in / sign up (Supabase browser client) + **Continue as Guest** |
| `/` | Dashboard — **watchlist-aware** universe table (search/filter/sort, watchlist tabs, star toggles, 30-day trend) |
| `/instruments/[symbol]` | Professional **`TradingChart`** (candles/volume + MA overlays + forecast band + trade markers); SMA-crossover backtest with metric tiles; "Analyze with agents"; **Research** (profile, earnings trend, statement tables); watchlist star |
| `/portfolio` | **Portfolio analytics** — holdings, allocation, Value-at-Risk, Monte-Carlo simulation, mean-variance optimization (Phase 6) |
| `/simulation` | Paper trading (redesigned focused workspace) — portfolio tiles + positions, order ticket (market/limit/stop), open orders + AI proposals (accept/reject), trade history |
| `/agents`, `/agents/[runId]` | Agent-run list + live-polling transcript & decision card; **explanation panel** (why/stances/indicators/forecast/backtest/risk at decision time) + **Send to Simulation** |
| `/insights` | AI evaluation — forecast accuracy, agent stats, recommendation success, usage & cost + portfolio-intelligence digest |
| `/chat` | Persisted chat sessions with grounded, context-chipped answers + **numbered news citations** (clickable) |

Shared UI in `components/`: the `ui/*` primitive library, `Shell`,
`chart/TradingChart` (persisted lightweight-charts instance — replaced the old
rebuild-on-every-render `CandleChart`), `assistant/AssistantDock`,
`SearchCommand` (command palette), `WatchlistStar`, `RunBits`,
`ResearchSection`, `sim/*` (order ticket, holdings, allocation…),
`portfolio/*` (Monte-Carlo + frontier charts), `chat/ContextChips`. Pure logic
lives in `lib/*.mjs` with `node:test` coverage; API layer in `lib/api.ts`;
Supabase browser client in `lib/supabase.ts`.

**Charting.** All chart wiring is isolated in `components/chart/` — the
`useTradingChart` hook creates the lightweight-charts instance once and
reconciles series from data (the persisted-instance pattern), and `TradingChart`
owns the toolbar/overlays. Pages only pass data + config. lightweight-charts was
chosen because no TradingView **Charting Library** license was available;
swapping to the official library later is a change confined to this folder — the
page contract (props in, chart out) does not move. (Deferred, Phase 6.)

## The authenticated backend proxy

The browser **never** calls the backend directly. All data goes through the
same-origin catch-all route `app/api/backend/[...path]/route.ts`:

- Reads the signed-in user's Supabase session server-side and forwards
  `Authorization: Bearer <jwt>` to `BACKEND_URL` (Render). Falls back to
  `X-API-Key` (`BACKEND_API_KEY`) only in local dev.
- `export const maxDuration = 300` — forecast/backtest/chat are single
  synchronous calls that may ride out a Render cold start + HF Space wake; 300 s
  is the Vercel Hobby+Fluid ceiling.
- Buffers the response (no streaming); forwards `204/304` with a null body
  (a non-null body on a null-body status throws). Network failure → a neutral `502`.

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
