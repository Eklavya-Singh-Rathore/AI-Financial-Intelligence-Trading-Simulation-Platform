# AI Agents Architecture

A **7-agent, TradingAgents-style pipeline** (`app/agents/`) that turns market
data + news + forecast + backtest evidence into a risk-limited recommendation.
Runs are asynchronous, fully persisted, and grounded in semantic memory.

## Pipeline

```
gather_context (deterministic: prices, indicators, news, Kronos forecast, backtest)
        │
        ▼
 Technical Analyst ── News Analyst
        │
        ▼
   Bull  ⇄  Bear   debate (AGENTS_DEBATE_ROUNDS)
        │
        ▼
     Trader  ──▶  Risk Manager  ──▶  Portfolio Manager
```

1. **gather_context** — deterministic evidence: OHLCV + indicators, recent
   NewsAPI headlines, a `horizon=5` Kronos forecast (falls back to `baseline`
   on `ForecasterError`), and a NautilusTrader backtest (falls back to the
   `simple` engine on error). No LLM.
2. **Technical / News Analysts** — structured JSON stances from the evidence.
3. **Bull / Bear debate** — argue for/against, `AGENTS_DEBATE_ROUNDS` rounds.
4. **Trader** — proposes a position.
5. **Risk Manager** — applies **coded hard limits that can only tighten** the
   trader's proposal: position-size cap (`MAX_POSITION_PCT`), drawdown veto
   (`RISK_MAX_DRAWDOWN_VETO_PCT`), and missing-evidence halving. The LLM cannot
   loosen these — they are enforced in code, not prompts.
6. **Portfolio Manager** — final decision + rationale.

Every step is persisted to `agent_messages`; the final decision to
`agent_runs`. **Phase 5:** the gather-time inputs (price summary, indicators,
forecast, backtest, headlines) are also persisted on the run as
`context_snapshot`, so `GET /agents/runs/{id}/explanation` composes a
faithful, deterministic explanation of the recommendation (no LLM call);
pre-snapshot runs degrade to message-derived sections. A completed BUY/SELL
non-veto decision can be sent to the paper-trading simulator as a `proposed`
order (human accept/reject — never auto-executed, see
[ADR-0006](../adr/ADR-0006-paper-trading.md)).

## Orchestration & safety

- Triggered by `POST /agents/run` → `202` + run id; executes in FastAPI
  `BackgroundTasks`. Concurrency cap `MAX_CONCURRENT_AGENT_RUNS` (429 on
  saturation), one in-flight run per symbol (409), `Idempotency-Key` dedup, and
  a per-run wall-clock timeout (`AGENT_RUN_TIMEOUT_SECONDS`). A startup sweep
  marks orphaned runs failed after `AGENT_RUN_STALE_MINUTES`.
- LLM calls go through `FailoverLLMClient` (Gemini → OpenAI → fake) with
  classified retry, jittered backoff, and rate-limit-aware waits. All prompts
  wrap external/tool text in `<untrusted-data>` boundaries.
- **JSON outputs**: each agent returns a schema-validated object; malformed
  output is repaired/rejected by the LLM layer, never trusted blindly.

## Semantic memory (RAG)

- After a run, salient messages are embedded (MiniLM, 384-d) and stored in
  `agent_embeddings` (`store_embedding`).
- The orchestrator recalls symbol-scoped notes for context; **chat** recalls
  universe-wide notes to ground answers in prior decisions
  (`recall_message_notes`, cosine-distance KNN).
- Embeddings compute locally (dev) or on the HF Space
  (`EMBEDDINGS_MODE=remote`, production). Memory is best-effort: if embedding is
  unavailable it degrades to "memory off" without breaking runs or chat.
- Toggle `ENABLE_AGENT_MEMORY`; retention `MEMORY_TTL_DAYS`.

## Chat / RAG

`chat_service` grounds each answer in live universe stats + the user's recent
agent decisions + semantic memory + **retrieved news headlines with
numbered citations**, all inside `<untrusted-data>` boundaries, then calls the
LLM (instructed to cite `[n]`). Headlines land in the `research_documents`
corpus two ways: opportunistically on every agent run, and via the daily
`news_ingest` scheduler job (`ENABLE_NEWS_INGEST`; retention
`NEWS_RETENTION_DAYS`). Citations (title/url/date) persist in the message
context and render as links. Sessions and messages are per-user owned; context
chips in the UI show which symbols/decisions/memory-notes/news were used. On
LLM unavailability (e.g. Gemini rate-limit with no funded fallback) it returns
a sanitized "temporarily unavailable" message.
