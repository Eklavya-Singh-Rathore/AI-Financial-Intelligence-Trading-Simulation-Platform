# ADR-0003: In-process agent orchestrator with coded risk limits

- **Status:** Accepted
- **Date:** 2026 (Phase 2; hardened Phase 2.5)

## Context

The recommendation engine is a 7-agent LLM pipeline (analysts → debate → trader
→ risk → portfolio manager). It must be safe (LLMs must not be able to exceed
risk limits), observable (every step inspectable), grounded (recall prior
decisions), and cheap to run — without external orchestration infrastructure.

## Decision

Run the pipeline **in-process** via FastAPI `BackgroundTasks`, triggered by
`POST /agents/run` → `202` + poll. Enforce **risk limits in code, not prompts**:
the Risk Manager stage applies a position-size cap, a drawdown veto, and
missing-evidence halving that can only *tighten* the trader's proposal. Persist
every step to `agent_messages`; embed salient messages (MiniLM, 384-d) for RAG
recall. Guard with a concurrency cap (429), per-symbol single-flight (409),
idempotency keys, per-run timeout, and a startup orphan sweep. LLM calls go
through a failover client (Gemini → OpenAI → fake) with `<untrusted-data>`
prompt boundaries.

## Consequences

- **+** No queue/worker infra; the safety-critical limits are deterministic and
  auditable; runs survive restarts (orphan sweep) and are fully traceable.
- **+** Fire-and-poll keeps a multi-minute, ~7-LLM-call run off any single long
  HTTP request (frontend polls every 2.5–3 s).
- **−** `BackgroundTasks` is not durable — a crash mid-run loses in-flight work
  (the sweep marks it failed; the user re-runs). Throughput is bounded by the
  single process and the LLM provider's rate limits.
- **→** A durable job queue is the main Phase 5 candidate (needed for scheduled
  autonomous runs).
