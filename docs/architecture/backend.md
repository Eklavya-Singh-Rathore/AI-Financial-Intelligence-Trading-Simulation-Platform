# Backend Architecture

FastAPI (async) application under `backend/app/`. Layering:

```
api/routers  ─▶  services  ─▶  (ml | backtesting | llm | agents)  ─▶  models / db
```

Routers stay thin; business logic lives in `services`; heavy/CPU work runs off
the event loop via `asyncio.to_thread`. Implementation choices (which
forecaster, which backtester, which LLM) come from **registries**, so switching
is a config change.

## Package map

| Package | Contents |
|---|---|
| `app/main.py` | App factory, lifespan (logging, orphan-run sweep, scheduler), CORS, router mounting at `/` and `/api/v1`, `/metrics` |
| `app/core/` | `config.py` (pydantic-settings), `auth.py` (JWT/API-key → `AuthContext`), logging, domain constants |
| `app/api/routers/` | `health`, `instruments` (prices/indicators/forecast), `ingest`, `backtest`, `agents`, `chat` |
| `app/services/` | `market_data`, `data_ingest`, `indicators`, `forecast_service`, `backtest_service`, `news`, `embeddings`, `space_client`, `chat_service` |
| `app/ml/` | `Forecaster` interface + `registry`; `baseline`, `kronos` (local), `remote_kronos` (Space); vendored `kronos_src/` (MIT) |
| `app/backtesting/` | `Backtester` interface + registry; NautilusTrader + a simple vectorized engine; SMA-crossover strategy |
| `app/llm/` | `LLMClient` + failover registry; Gemini / OpenAI / fake clients |
| `app/agents/` | 7-agent orchestrator, prompts, risk limits (see [ai-agents.md](ai-agents.md)) |
| `app/models/`, `app/db/` | Async SQLAlchemy ORM + engine/session |
| `app/scheduler/` | APScheduler jobs (daily ingest; inference-Space keep-warm) |

## Registries (the extension seam)

- **Forecaster** (`app/ml/registry.py`): `get_forecaster(name)` →
  `kronos` | `baseline`. For `kronos`, `KRONOS_MODE` selects `KronosForecaster`
  (in-process torch) or `RemoteKronosForecaster` (HF Space). The public name
  stays `kronos` in both modes, so API params and persisted `model_name` never
  change. Instances cached per `(name, mode)`.
- **Backtester** (`app/backtesting/registry.py`): `nautilus` | `simple`.
- **LLM** (`app/llm/registry.py`): `FailoverLLMClient` wraps primary + fallback
  with classified retry, jittered backoff, and rate-limit-aware waits.

All three share the same shape: a narrow interface, a name→impl map, lazy
construction, and normalization of failures to one error type. The remote
inference client (`app/services/space_client.py`) follows the same pattern.

## Concurrency & performance

- Single uvicorn worker (Render free tier is 0.1 CPU / 512 MB). CPU-bound work
  (forecast, backtest, embeddings, LLM calls, ingest) is offloaded with
  `asyncio.to_thread` so the event loop stays responsive.
- Agent runs execute in FastAPI `BackgroundTasks` with an in-loop concurrency
  cap (`MAX_CONCURRENT_AGENT_RUNS`, default 2 → `429` on saturation), one
  in-flight run per symbol (`409`), and `Idempotency-Key` support.
- The slim production image excludes torch/sentence-transformers entirely
  (inference is remote); idle RSS ~230 MB, backtest peak ~350–420 MB.

## Startup lifecycle (`app/main.py` lifespan)

1. Load settings, configure structlog, warn if auth is unconfigured.
2. If a database is configured: sweep orphaned agent runs (mark stale
   `running`/`pending` failed) and purge expired embeddings, then start the
   scheduler.
3. Migrations are **manual** (`alembic upgrade head`), never at boot.

## Error handling & observability

- Forecast failures → `ForecasterError` → HTTP `503` (agent runs fall back to
  the baseline forecaster). LLM failures → normalized `LLMError` → primary/
  fallback failover, then a sanitized message. Space failures → structured
  `SpaceClientError` with **token-free** messages (they can surface in `503`
  details).
- `EXPOSE_ERROR_DETAILS=false` in production sanitizes error bodies.
- Prometheus metrics at `/metrics` (auth-gated); structlog with request IDs;
  `/live` (liveness) and `/health` (readiness incl. DB + inference modes).

## API surface (selected)

| Endpoint | Notes |
|---|---|
| `GET /live`, `GET /health` | open; health reports DB + `kronos_mode`/`embeddings_mode` |
| `GET /instruments`, `/instruments/summary` | the 16-asset universe |
| `GET /instruments/{s}/prices` `/indicators` `/forecast` | forecast: `horizon` (1–60), `model` (`kronos`/`baseline`), `persist` |
| `POST /backtest` | SMA-crossover, `nautilus`/`simple` engine |
| `POST /agents/run` → `202` | fire-and-poll; `GET /agents/runs/{id}` + `/messages` |
| `POST /chat/sessions`, `POST /chat/sessions/{id}/messages` | RAG-grounded chat |

Every business route depends on `get_auth`; routes are dual-mounted at `/` and
`/api/v1`. Validation is Pydantic (out-of-range → `422`, unknown symbol → `404`,
unknown forecaster → `422`).
