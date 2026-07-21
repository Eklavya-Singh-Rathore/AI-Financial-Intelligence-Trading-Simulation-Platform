# ADR-0004: Deployment on Vercel + Render + Hugging Face + Supabase

- **Status:** Accepted
- **Date:** 2026 (supersedes the earlier Oracle-VM plan)

## Context

The platform must run near-$0 and auto-deploy from `main`. The frontend was
already on Vercel and the DB/Auth on Supabase, but the backend was undeployed.
An earlier plan targeted a single Oracle Cloud VM running the full torch/nautilus
image; it was never executed. Measurements showed the full backend (torch +
MiniLM in-process) needs ~800–900 MB RSS — far over a small free instance.

## Decision

Split hosting across managed free tiers:

- **Frontend → Vercel** (Next.js, root `frontend/`).
- **Backend → Render** free web service, running a **slim Docker image with no
  torch** (`Dockerfile.render`); ML inference is delegated to a Hugging Face
  Space. Idle RSS ~230 MB fits the 512 MB tier.
- **ML inference → Hugging Face Space** ([ADR-0005](ADR-0005-ai-inference.md)).
- **DB/Auth → Supabase** (existing).
- Keep-alive via GitHub Actions cron; DATABASE_URL uses the Supabase **pooler**
  (Render is IPv4-only). The full image (`Dockerfile`) remains for self-hosting.

## Consequences

- **+** ~$0/month, auto-deploy from `main`, each surface independently
  scalable/replaceable; IaC in `render.yaml`.
- **−** More moving parts and free-tier constraints: Render 15-min sleep (needs
  keep-alive), HF Space ~48 h idle sleep + cold-start latency, no persistent
  disk, manual migrations (no shell). Documented in the deployment runbooks.
- **−** First-request-after-idle latency is the only intended behavioral delta
  vs localhost; the Vercel proxy `maxDuration=300` absorbs it.
