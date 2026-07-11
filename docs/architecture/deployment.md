# Deployment Architecture

Four managed surfaces, all on free tiers (≈ $0/month), auto-deploying from
`main`. Runbooks: [deploy-render.md](../deploy-render.md),
[deploy-hf-space.md](../deploy-hf-space.md); env: [environment.md](../environment.md).

```
Users ─▶ Vercel (frontend) ─▶ Render (backend) ─▶ Supabase (DB/Auth)
                                     └──────────▶ HF Space (Kronos + MiniLM)
                                     └──────────▶ Gemini/OpenAI · NewsAPI · yfinance
```

## Surfaces

| Surface | What | URL |
|---|---|---|
| **Vercel** | Next.js frontend, root `frontend/` | `https://ai-financial-intelligence-platf-eklavya-singh-rathores-projects.vercel.app` |
| **Render** | Slim FastAPI backend (Docker, no torch) | `https://stock-ai-backend-gv17.onrender.com` |
| **HF Space** | `ai-inference-service` — Gradio/ZeroGPU, official Kronos + MiniLM | `https://eklavya73-ai-inference-service.hf.space` |
| **Supabase** | Postgres 17 + pgvector + Auth | project `rekoawsoghrjcimknkfz` |

## Backend image (Render)

Two Dockerfiles: `backend/Dockerfile` (full, torch, self-host/CI) and
`backend/Dockerfile.render` (**slim, no torch**, `requirements-deploy.lock`).
Production runs the slim image with `KRONOS_MODE=remote` /
`EMBEDDINGS_MODE=remote`, so inference is delegated to the Space and RSS stays
inside the 512 MB free tier. Render free notes: 0.1 CPU, 15-min idle spin-down,
ephemeral disk, IPv4-only egress (→ Supabase **pooler** DATABASE_URL required).
IaC record: `render.yaml`.

## Inference Space

Gradio-SDK Space on **ZeroGPU** (Hugging Face paywalled Docker/cpu-basic Spaces
in July 2026; ZeroGPU stays free). Inference runs on **CPU** (Kronos-small is
24.7 M params) so it consumes no GPU quota. Official checkpoints load from the
Hub; no weights are committed to the Space repo. `infrastructure/hf-space/` is
the source of truth (its `kronos_src/` is kept byte-identical to the backend
copy — CI enforces the diff).

## Keep-alive

- GitHub Actions cron `.github/workflows/keepalive.yml` pings the Render `/live`
  every 10 min (repo variable `BACKEND_LIVE_URL`) so the free instance never
  sleeps and the 13:00 UTC daily ingest fires.
- The backend scheduler pings the Space `/health` every 6 h (`space_keepalive`)
  so the Space never hits its ~48 h idle shutdown.

## CI/CD (`.github/workflows/ci.yml`)

`backend` (ruff → mypy → bandit → pip-audit → fast pytest + kronos_src drift
check) · `integration` (pgvector Postgres, `base_schema.sql` + `alembic upgrade
head` + db-marked tests) · `frontend` (tsc → `node:test` → build) · `docker`
(full image **and** slim Render image, asserting the slim image boots
torch-free). Merges to `main` trigger Vercel + Render auto-deploys.

## Migrations & data

Migrations are manual (`alembic upgrade head` from a dev machine; the free
tiers have no shell/pre-deploy hooks). Supabase is at head
`0010_revoke_admin_execute`.

## Expected behavioral delta vs localhost

Latency only: the first request after an idle window rides a ~1 min Render wake
and/or an HF Space 503-wake poll (bounded by `INFERENCE_WAKE_MAX_WAIT_SECONDS`);
the proxy's 300 s budget absorbs it. Kronos sampling is non-deterministic
(T=1.0, top_p=0.9, no seed), so forecast values differ run-to-run by design.
