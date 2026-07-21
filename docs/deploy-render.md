# Backend deployment — Render

The backend runs as a **Render free-tier web service** built from
[`backend/Dockerfile.render`](../backend/Dockerfile.render) — the slim image
with **no torch**: Kronos forecasts and MiniLM embeddings are served by the
Hugging Face Space ([docs/deploy-hf-space.md](deploy-hf-space.md)) via
`KRONOS_MODE=remote` / `EMBEDDINGS_MODE=remote`. Everything else (auth, agents,
RAG retrieval, chat, NautilusTrader backtesting, APIs, scheduler) runs
in-process, exactly as on localhost.

```
Vercel frontend ──BACKEND_URL──► Render web service ──INFERENCE_SPACE_URL──► HF Space
                                       │
                                       └────────► Supabase / Gemini / OpenAI / NewsAPI / yfinance
```

## Why the free tier works (evaluation summary)

| Constraint (Free instance) | Measured / design response |
|---|---|
| 512 MB RAM | slim image idles ~230 MB; peak ~350–420 MB during a backtest. torch alone would add ~500 MB → that's why inference is remote |
| 0.1 CPU | backtests/ingest are slower than localhost but complete well inside the proxy's 300 s budget; LLM/agent work is network-bound |
| Sleeps after 15 min idle | `.github/workflows/keepalive.yml` pings `/live` every 10 min |
| 750 instance-hours/month | covers exactly one always-awake service |
| Ephemeral disk | nothing is persisted locally (DB = Supabase; models = Space) |
| May restart anytime | startup sweep marks orphaned agent runs failed; ingest is idempotent |

The unmodified full image (`backend/Dockerfile`, torch + local inference)
needs a ≥2 GB host — on Render that is the Standard plan (~$25/mo), or any
Docker VM via `infrastructure/docker-compose.prod.yml`.

## Service configuration (source of truth: [`render.yaml`](../render.yaml))

- **Type/runtime:** web service, Docker; `dockerfilePath: backend/Dockerfile.render`,
  `dockerContext: backend`
- **Plan/region:** `free`, `singapore` (closest to Supabase ap-south-1 Mumbai)
- **Health check:** `/live` (Render probes it; the container binds Render's
  injected `$PORT`)
- **Auto-deploy:** on every push to `main`
- **Env vars:** plain values live in `render.yaml`; secrets are `sync: false`
  and must be set in the dashboard/API. Full reference:
  [docs/environment.md](environment.md)
- **`DATABASE_URL` must be the Supabase *pooler* URL** —
  `postgresql+asyncpg://postgres.<ref>:<pw>@aws-0-ap-south-1.pooler.supabase.com:6543/postgres`.
  Render egress is IPv4-only and Supabase direct hosts (`db.<ref>.supabase.co`)
  resolve to IPv6 only → the app boots but every DB call fails with `OSError`
  (found the hard way on first deploy). The backend auto-detects pooler URLs
  and disables the asyncpg statement cache for PgBouncer compatibility.

`CORS_ORIGINS` stays **unset** on purpose: browsers only ever call the Vercel
same-origin proxy, which forwards server-side — no cross-origin browser
requests reach Render.

## Deploying

### Path A — Blueprint (dashboard)

1. Render → **New → Blueprint** → connect the GitHub repo → Render reads
   `render.yaml`.
2. Fill in the `sync: false` secrets when prompted (see table in
   [docs/environment.md](environment.md)).
3. Apply. First build takes a few minutes; the service URL is
   `https://<service-name>.onrender.com`.

### Path B — REST API (what Phase 4.5 used)

With a Render API key (`rnd_...`):

```bash
# owner id
curl -s -H "Authorization: Bearer $RENDER_API_KEY" https://api.render.com/v1/owners
# create the service (payload mirrors render.yaml)
curl -s -X POST https://api.render.com/v1/services \
  -H "Authorization: Bearer $RENDER_API_KEY" -H "Content-Type: application/json" \
  -d @service.json
# set/replace env vars
curl -s -X PUT https://api.render.com/v1/services/<srv-id>/env-vars \
  -H "Authorization: Bearer $RENDER_API_KEY" -H "Content-Type: application/json" \
  -d @env-vars.json
# trigger + watch deploys
curl -s -X POST https://api.render.com/v1/services/<srv-id>/deploys \
  -H "Authorization: Bearer $RENDER_API_KEY"
curl -s "https://api.render.com/v1/services/<srv-id>/deploys?limit=1" \
  -H "Authorization: Bearer $RENDER_API_KEY"
```

> Rotate any API key that was ever shared in chat/e-mail after the deployment
> is done (Render dashboard → Account Settings → API Keys).

## Keep-alive (required for the scheduler)

Free instances spin down after 15 idle minutes — a sleeping instance silently
misses the 13:00 UTC ingest cron. Set the repo **Actions variable**
`BACKEND_LIVE_URL=https://<service>.onrender.com/live`; the
[`keepalive`](../.github/workflows/keepalive.yml) workflow then pings it every
10 minutes (also runnable manually via *workflow dispatch*). The backend's own
scheduler keeps the HF Space warm (`space_keepalive` job, every 6 h) — no
GitHub secret needed for that.

## Database migrations

Migrations stay **manual** (the free tier has no SSH/pre-deploy hooks):

```bash
cd backend && alembic upgrade head   # run from a dev machine against Supabase
```

The Supabase DB is already at head `0009_user_ownership`; a fresh deploy needs
no migration step.

## Verification checklist

```bash
BASE=https://<service>.onrender.com
curl -s $BASE/live                     # {"status":"alive"}
curl -s $BASE/health                   # database:"ok", kronos_mode:"remote", embeddings_mode:"remote"
curl -s $BASE/instruments              # 401 without credentials (auth matrix)
curl -s -H "X-API-Key: $API_KEY" $BASE/instruments                        # tracked universe (16 pre-sync; ~100 after POST /admin/catalog/sync)
curl -s -H "X-API-Key: $API_KEY" "$BASE/instruments/RELIANCE/forecast?horizon=5&model=kronos&persist=false"
curl -s -H "X-API-Key: $API_KEY" -X POST $BASE/backtest -H "Content-Type: application/json" \
  -d '{"symbol":"RELIANCE","fast":10,"slow":30}'
```

Then set `BACKEND_URL` on the Vercel project and run the browser E2E
(login → dashboard → forecast → backtest → agent run → chat).

## Free-tier caveats (accepted)

- **Cold start** ~1 min if the keepalive ever misses (first request after
  sleep is slow; the frontend proxy budget is 300 s).
- **No shell access**; debug via Render logs (dashboard → Logs).
- **Restarts can happen anytime**: agent runs in flight are marked failed by
  the startup sweep; users simply re-run.
- **Concurrent NautilusTrader backtests** could theoretically exceed 512 MB —
  Render restarts the instance; requests fail fast and recover.

## Credential rotation checklist (before/at go-live)

1. Supabase **DB password** (→ new `DATABASE_URL`), ideally a least-privilege
   role for the app (SELECT/INSERT/UPDATE/DELETE on app tables only).
2. `API_KEY` — generate a fresh long random value; it is admin-equivalent.
3. `GOOGLE_AI_STUDIO_API_KEY`, `OPENAI_API_KEY`, `NEWSAPI_KEY`.
4. `HF_TOKEN` — fine-grained, **read-only on the inference Space** only.
5. The Render **API key** used for deployment automation.
