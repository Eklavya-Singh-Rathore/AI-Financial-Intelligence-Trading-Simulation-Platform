# Environment variables — complete reference (Phase 4.5)

Every variable the platform reads, grouped by concern. **Where set** uses:
`local` = repo-root `.env` (git-ignored, from `.env.example`) ·
`Render` = Render service env vars (secrets marked `sync: false` in
`render.yaml`) · `Vercel` = frontend project env vars · `Space` = Hugging Face
Space variables/secrets · `GH` = GitHub Actions repo variables/secrets.

Backend settings are all defined in `backend/app/core/config.py` (pydantic-
settings; env var = field name upper-cased; every field has a default, so the
app boots with partial config and degrades explicitly).

## Backend — runtime & security

| Variable | Default | Secret | Where set | Purpose |
|---|---|---|---|---|
| `ENV` | `development` | no | local, Render (`production`) | environment label (log fields, prod warnings) |
| `LOG_LEVEL` | `INFO` | no | local, Render | structlog/uvicorn level |
| `API_KEY` | *(empty)* | **yes** | local, Render | `X-API-Key` service auth (admin-equivalent). Empty = open dev mode (warned) |
| `RATE_LIMIT_PER_MINUTE` | `120` | no | local, Render | per-client rate limit |
| `CORS_ORIGINS` | *(empty)* | no | *(unset in prod)* | comma-separated browser origins; empty = middleware off. Prod traffic rides the Vercel server-side proxy, so CORS stays off |
| `EXPOSE_ERROR_DETAILS` | `false` | no | Render (`false`) | include internal error text in responses (dev only) |

## Backend — database (Supabase Postgres)

| Variable | Default | Secret | Where set | Purpose |
|---|---|---|---|---|
| `DATABASE_URL` | *(empty)* | **yes** | local, Render | asyncpg URL (direct or pooler; pooler auto-detected). Functionally required |
| `DB_STATEMENT_CACHE_SIZE` | auto | no | rarely | override asyncpg statement cache (pooler compat is automatic) |

## Supabase Auth (backend + frontend)

| Variable | Default | Secret | Where set | Purpose |
|---|---|---|---|---|
| `SUPABASE_URL` | *(empty)* | no | local, Render | project URL (`https://<ref>.supabase.co`) |
| `SUPABASE_ANON_KEY` | *(empty)* | no (public by design) | local, Render | remote JWT validation path |
| `SUPABASE_JWT_SECRET` | *(empty)* | **yes** | local, Render (optional) | local HS256 JWT verification (fast path; remote fallback works without it) |
| `NEXT_PUBLIC_SUPABASE_URL` | — | no | Vercel, `frontend/.env.local` | browser Supabase client + middleware |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | — | no (public) | Vercel, `frontend/.env.local` | 〃 |

## Hugging Face — remote inference (Phase 4.5)

| Variable | Default | Secret | Where set | Purpose |
|---|---|---|---|---|
| `KRONOS_MODE` | `local` | no | Render (`remote`) | `local` = in-process Kronos (needs `[local-ml]` extra) · `remote` = Space `/forecast` |
| `EMBEDDINGS_MODE` | `local` | no | Render (`remote`) | same switch for MiniLM semantic memory |
| `INFERENCE_SPACE_URL` | *(empty)* | no | Render | Space base URL, e.g. `https://eklavya73-ai-inference-service.hf.space` |
| `HF_TOKEN` | *(empty)* | **yes** | Render, local (remote mode) | fine-grained token with **read** on the private Space (also lifts Hub rate limits in local mode) |
| `INFERENCE_SPACE_API_KEY` | *(empty)* | **yes** | Render (only if Space public) | shared secret sent as `X-API-Key`; pairs with Space secret `SPACE_API_KEY` |
| `INFERENCE_CONNECT_TIMEOUT_SECONDS` | `10` | no | rarely | httpx connect timeout |
| `INFERENCE_READ_TIMEOUT_SECONDS` | `120` | no | rarely | httpx read timeout per attempt |
| `INFERENCE_MAX_RETRIES` | `2` | no | rarely | extra attempts for transient failures |
| `INFERENCE_RETRY_BACKOFF_SECONDS` | `1.5` | no | rarely | backoff base (jittered) |
| `INFERENCE_WAKE_MAX_WAIT_SECONDS` | `180` | no | rarely | total budget while a slept Space returns 503 |
| `KRONOS_MODEL_ID` | `NeoQuasar/Kronos-small` | no | local/Render + Space | checkpoint id (keep backend & Space aligned) |
| `KRONOS_TOKENIZER_ID` | `NeoQuasar/Kronos-Tokenizer-base` | no | 〃 | tokenizer id |
| `KRONOS_MAX_CONTEXT` | `512` | no | 〃 | context window cap |
| `KRONOS_DEVICE` | `cpu` | no | local only | local-mode torch device |
| `EMBEDDING_MODEL_ID` | `sentence-transformers/all-MiniLM-L6-v2` | no | local/Render + Space | embedding model (must stay 384-d — DB column `vector(384)`) |

**Space-side** (Settings → Variables and secrets): `KRONOS_MODEL_ID`,
`KRONOS_TOKENIZER_ID`, `EMBEDDING_MODEL_ID`, `KRONOS_MAX_CONTEXT` (variables;
model changes need a factory rebuild) and `SPACE_API_KEY` (secret, public-Space
option only).

## LLM providers

| Variable | Default | Secret | Where set | Purpose |
|---|---|---|---|---|
| `LLM_PROVIDER` | `gemini` | no | local, Render | primary provider (`gemini` \| `openai` \| `fake`) |
| `LLM_FALLBACK_PROVIDER` | `openai` | no | local, Render | automatic failover target (empty = none) |
| `GOOGLE_AI_STUDIO_API_KEY` | — | **yes** | local, Render | Gemini key |
| `GEMINI_MODEL` | `gemini-2.5-flash` | no | local, Render | Gemini model id |
| `OPENAI_API_KEY` | — | **yes** | local, Render | OpenAI key (fallback; currently unfunded — see handover) |
| `OPENAI_MODEL` | `gpt-4o-mini` | no | local, Render | OpenAI model id |
| `LLM_TIMEOUT_SECONDS` | `90` | no | rarely | per-call timeout |

## News APIs

| Variable | Default | Secret | Where set | Purpose |
|---|---|---|---|---|
| `NEWSAPI_KEY` | — | **yes** | local, Render | NewsAPI.org key (missing key = news degrades to empty, agents still run) |
| `NEWS_LOOKBACK_DAYS` | `7` | no | rarely | headline window |
| `NEWS_MAX_HEADLINES` | `12` | no | rarely | cap per run |

## Backend — scheduler / ingest / agents

| Variable | Default | Secret | Where set | Purpose |
|---|---|---|---|---|
| `ENABLE_SCHEDULER` | `true` | no | Render (`true`) | APScheduler master switch (daily ingest + Space keep-warm) |
| `DAILY_INGEST_HOUR` / `DAILY_INGEST_MINUTE` | `13` / `0` | no | rarely | UTC daily ingest time (~post-IST close) |
| `DEFAULT_HISTORY_DAYS` | `1095` | no | rarely | initial backfill window |
| `DEFAULT_FORECASTER` | `kronos` | no | Render | forecaster when the request omits `model` |
| `AGENTS_DEBATE_ROUNDS` | `1` | no | rarely | bull/bear debate depth |
| `MAX_POSITION_PCT` | `10` | no | rarely | coded risk cap (LLMs can only tighten) |
| `RISK_MAX_DRAWDOWN_VETO_PCT` | `40` | no | rarely | drawdown veto threshold |
| `ENABLE_AGENT_MEMORY` | `true` | no | Render (`true`) | semantic memory on/off |
| `AGENT_MEMORY_TOP_K` | `3` | no | rarely | RAG recall depth |
| `MAX_CONCURRENT_AGENT_RUNS` | `2` | no | Render | run concurrency cap (429 beyond) |
| `AGENT_RUN_TIMEOUT_SECONDS` | `600` | no | rarely | per-run wall clock |
| `AGENT_RUN_STALE_MINUTES` | `30` | no | rarely | startup orphan sweep threshold |
| `MEMORY_TTL_DAYS` | `90` | no | rarely | embedding retention |

## Frontend (Vercel project)

| Variable | Default | Secret | Where set | Purpose |
|---|---|---|---|---|
| `BACKEND_URL` | `http://127.0.0.1:8000` | no | **Vercel (required)** | the Render URL; unset = proxy targets localhost and returns 502 in prod |
| `BACKEND_API_KEY` | *(empty)* | **yes** | local dev only — **leave empty on Vercel** | proxy's X-API-Key fallback when no user session (dev convenience) |
| `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_ANON_KEY` | — | no | Vercel | see Supabase section |

## GitHub Actions (keepalive)

| Name | Kind | Purpose |
|---|---|---|
| `BACKEND_LIVE_URL` | repo **variable** | `https://<service>.onrender.com/live`; workflow no-ops while unset |

## Future / reserved

| Variable | Status |
|---|---|
| `ANTHROPIC_API_KEY` | declared in settings, **not yet wired** — the LLM registry currently builds only gemini/openai/fake; reserved for a future Claude provider |
| Twitter/X & other data APIs | Phase 5 roadmap; will follow the same pattern (key in Render env, graceful degrade when absent). The old `ALPHA_VANTAGE_KEY` doc reference was dead — no code reads it — and has been dropped |
