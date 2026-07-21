# ADR-0006: Paper-trading engine semantics & human-in-the-loop AI

- **Status:** Accepted
- **Date:** 2026

## Context

The platform includes a paper-trading simulator so users can act on AI recommendations
without real money. The platform's market data is **daily OHLCV bars** (no
intraday feed), the backend runs on a 512 MB free tier, and a hard product
rule applies: **the AI must never execute a trade by itself**.

## Decision

1. **Daily-bar execution semantics.** Market orders fill at the latest close.
   Limit/stop orders rest with status `open` and are evaluated against each
   newly ingested bar: buy limit fills at `min(open, limit)` when
   `low <= limit`; sell limit at `max(open, limit)` when `high >= limit`; buy
   stop at `max(open, stop)` when `high >= stop`; sell stop at
   `min(open, stop)` when `low <= stop` (gap-aware). Resting orders are swept
   lazily on portfolio reads and by a daily scheduler job after ingest — no
   long-lived matching process.
2. **Average-cost position accounting** (one `sim_positions` row per
   portfolio+instrument), realized P&L on sells, Decimal for money, float only
   for statistics. Insufficient cash/shares rejects the order and rolls back.
3. **Equity curve reconstructed on demand** from the trade list + close-price
   series instead of a persisted daily-snapshot table. Metrics (total return,
   CAGR, Sharpe, Sortino, volatility, max drawdown, win rate) are computed
   from that series per request.
4. **One portfolio per owner**, enforced by a unique index over
   `COALESCE(user_id, zero-uuid)` so the NULL (service) owner is also unique.
5. **Human-in-the-loop AI.** An agent run's decision becomes at most a
   `proposed` order (via an explicit "Send to Simulation" action), sized as
   `size_pct × equity / latest close` with SELL capped at held quantity;
   HOLD, risk-vetoed, and zero-size decisions are not proposable. A human
   must accept (executes as a market order) or reject. `source='ai'` +
   `agent_run_id` keep the AI-vs-manual attribution auditable.

## Consequences

- **+** Semantics are honest for daily data - no pretend intraday fills; every
  fill is reproducible from bars + rules (unit-tested, including gaps).
- **+** No snapshot table to drift or backfill; the equity curve is always
  consistent with the trades that produced it.
- **+** The never-auto-execute rule is structural (status flow
  `proposed → open/filled` requires a human accept), not a prompt-level
  convention; AI-vs-manual performance is directly comparable.
- **−** Reconstructing the curve is O(days × trades) per request - fine at
  this scale (16 instruments, one portfolio per user), revisit if it grows.
- **−** Fills at daily granularity can differ from real intraday execution;
  acceptable for a simulator whose purpose is decision evaluation, and
  clearly better than inventing prices the data cannot support.
