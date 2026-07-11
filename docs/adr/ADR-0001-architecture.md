# ADR-0001: Modular monolith

- **Status:** Accepted
- **Date:** 2026 (Phase 1; reaffirmed Phase 4.6)

## Context

A solo/small-team project spanning data ingestion, indicators, ML forecasting,
backtesting, a multi-agent LLM pipeline, RAG chat, and a web dashboard. It needs
fast iteration, low operational overhead, and cheap hosting — while keeping the
door open to swapping ML/LLM/backtest implementations.

## Decision

Build a **modular monolith**: one FastAPI backend with clear internal layers
(`api/routers → services → (ml | backtesting | llm | agents) → models/db`) and
**registries** that select implementations by name/config. Deploy as a single
process; offload CPU-bound work with `asyncio.to_thread`. The frontend is a
separate Next.js app that reaches the backend only through an authenticated
same-origin proxy.

## Consequences

- **+** One deployable, one codebase, trivial local dev; no cross-service RPC or
  distributed transactions.
- **+** Registries give the extensibility of pluggable components without
  microservice overhead (e.g. `kronos` local↔remote is a config switch).
- **−** Single process shares a fault domain and scaling unit; long jobs (agent
  runs) use `BackgroundTasks` rather than a durable queue.
- **→** Phase 5 may extract a durable job queue if autonomous/scheduled runs
  demand it — the registry seam makes that incremental. The one piece already
  extracted is **ML inference** (to a Hugging Face Space), driven by hosting RAM
  limits, not by architectural preference — see [ADR-0005](ADR-0005-ai-inference.md).
