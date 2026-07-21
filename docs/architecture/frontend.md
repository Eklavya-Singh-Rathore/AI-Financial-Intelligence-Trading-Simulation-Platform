# Frontend Architecture

**Next.js 15** (App Router, TypeScript) + Tailwind v4 + TanStack Query +
TradingView `lightweight-charts` + `next-themes` (system-adaptive light/dark).
Deployed on Vercel (project root `frontend/`). **Phase 6** adds a CSS-var
**design-token system** and a hand-built primitive library (`components/ui/*` —
Card, Stat, Table, Badge, Button, Input, Select, Tabs, Sheet, EmptyState,
Skeleton, Spinner), a responsive **app shell** with a mobile drawer, a Cmd/Ctrl-K
**command palette**, and a site-wide **floating AI assistant**.

**Premium redesign (2026-07).** A *tasteful* gradient/glow/glass layer over the
flat foundation, added **centrally** so pages re-skin via tokens/variants rather
than rewrites. `app/globals.css` gained `accent-2` (purple gradient partner),
`surface-3`, `on-accent`, `warn`, `shadow-lg` + accent `shadow-glow`, and
`.bg-grad-primary` / `.bg-grad-buy` / `.glass` / `.hover-lift` helpers + a
`scale-in` motion token (each with light + dark values — parity preserved).
`lib/ui.ts` gained a `gradient` Button variant; `Card` gained
`default|elevated|glass` variants (now `rounded-xl`); `Stat` gained an icon chip,
top-right delta, and a chart slot. **New primitives:** `Sparkline` (extracted from
the dashboard), `Avatar`, `Progress`, `Tooltip`, `DropdownMenu`. The **shell**
moved global controls to a **desktop topbar** (centered command-palette search;
live NSE market clock on the right), with the theme toggle + an avatar account
menu (sign-out) in the **sticky** sidebar footer and the collapse toggle in the
sidebar header. Applied per page: the gradient **Buy — Market Order** CTA + iconed
KPI tiles (Simulation/Portfolio/Insights/Dashboard breadth), an elevated
decision-card with a glowing shield + initials avatars (Agents), a glow/gradient
**login hero**, and a **responsive Chat** (the previously fixed two-pane layout
now stacks on mobile). Notifications/Alerts/Upgrade-to-Pro chrome is deliberately
omitted (no backend for it). Remaining: instrument-page control normalization +
Dialog/Toast/Pagination primitives.

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

**Charting (Phase 6.5 trading workstation).** All chart wiring is isolated in
`components/chart/` — the `useTradingChart` hook creates the lightweight-charts
instance once and reconciles series from data (the persisted-instance pattern);
`TradingChart` owns the toolbar. lightweight-charts was chosen because no
TradingView **Charting Library** license was available (re-audited in Phase 6.5,
still unavailable). Phase 6.5 adds: **intervals** 1m–1M (intraday from yfinance
via the backend `ohlcv` resolver, on-demand + cached; daily stored; W/M
resampled — `lib/chartIntervals.mjs`); **7 chart types** (candles/hollow/bar/
line/area/baseline/Heikin-Ashi); a **data-driven indicator catalog**
(`lib/indicators.ts`) rendered generically (overlays on the price pane,
oscillators in sub-panes, bands/histograms/reference-levels) with a picker +
localStorage presets (`lib/chartPresets.mjs`); a **canvas drawing engine**
(`DrawingCanvas.tsx` + `lib/chartDrawings.mjs`) that maps data-space anchors to
pixels via the chart's coordinate converters and redraws on pan/zoom — trend
line, ray, horizontal/vertical, rectangle, Fibonacci, measure, text; select/
move/delete, undo/redo, per-symbol persistence; a **Volume Profile** overlay;
and **support/resistance + AI overlays** (`lib/supportResistance.mjs`). The
instrument page also docks the paper-trading **order ticket** (market/limit/
stop/stop-limit) beside the chart.

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
