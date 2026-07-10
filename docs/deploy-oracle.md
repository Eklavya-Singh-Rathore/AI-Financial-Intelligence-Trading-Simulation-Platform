# Backend deployment — Oracle Cloud (OCI)

Runbook for hosting the FastAPI backend on an OCI compute VM with Docker.
The frontend lives on Vercel; the database and auth live on Supabase — the VM
runs only the stateless API container behind Caddy (automatic HTTPS).

## 1. Provision the VM

- **Shape:** `VM.Standard.A1.Flex` (Ampere ARM) with **4 OCPU / 24 GB** fits the
  Always-Free tier and comfortably runs the image (torch and nautilus_trader
  both ship `aarch64` manylinux wheels). Any x86 shape ≥ 8 GB RAM also works.
- **Image:** Ubuntu 22.04/24.04.
- **Ingress rules** (VCN security list or NSG): open TCP **80** and **443** from
  `0.0.0.0/0`; keep 22 restricted to your IP. Do NOT open 8000 — the API is
  reached only through Caddy.
- Point a DNS `A` record (e.g. `api.yourdomain.com`) at the VM's public IP.
  Caddy needs a domain to issue the TLS certificate.

## 2. Install Docker

```bash
sudo apt-get update && sudo apt-get install -y ca-certificates curl
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER && newgrp docker
```

Ubuntu on OCI also needs iptables ingress for 80/443 (OS-level firewall):

```bash
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save 2>/dev/null || true
```

## 3. Deploy

```bash
git clone https://github.com/Eklavya-Singh-Rathore/AI-Financial-Intelligence-Trading-Simulation-Platform.git app
cd app
cp .env.example .env.production        # then fill in real values (see below)
export BACKEND_DOMAIN=api.yourdomain.com
docker compose -f infrastructure/docker-compose.prod.yml up -d --build
```

First build compiles/downloads several GB (torch); allow 10–20 minutes.

### Required `.env.production` values

| Key | Value |
|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://…` Supabase connection string (**rotated** password) |
| `API_KEY` | long random string — service/automation access |
| `SUPABASE_URL` / `SUPABASE_ANON_KEY` | from Supabase dashboard → Settings → API |
| `SUPABASE_JWT_SECRET` | optional fast-path JWT verification (same page) |
| `GOOGLE_AI_STUDIO_API_KEY` | **rotated** Gemini key |
| `OPENAI_API_KEY` | funded key, or leave empty and set `LLM_FALLBACK_PROVIDER=` |
| `NEWSAPI_KEY` | **rotated** NewsAPI key |
| `CORS_ORIGINS` | your Vercel URL, e.g. `https://<app>.vercel.app` |
| `EXPOSE_ERROR_DETAILS` | `false` |

## 4. Verify

```bash
curl https://api.yourdomain.com/live      # {"status":"alive"}
curl https://api.yourdomain.com/health    # {"status":"ok","database":"ok"}
docker compose -f infrastructure/docker-compose.prod.yml logs backend | tail
```

## 5. Connect the frontend

In Vercel → Project → Settings → Environment Variables set
`BACKEND_URL=https://api.yourdomain.com`, remove any `BACKEND_API_KEY`, and
redeploy. The dashboard health dot turns green and all pages go live.

## Secrets that MUST be rotated before production

All development credentials were shared in planning documents/sessions and are
compromised by definition:

1. Supabase **database password** (dashboard → Settings → Database → Reset) —
   update `DATABASE_URL` everywhere.
2. `GOOGLE_AI_STUDIO_API_KEY`, `OPENAI_API_KEY`, `NEWSAPI_KEY`,
   `ALPHA_VANTAGE_KEY`.
3. Create the least-privilege DB role for the app (SQL in
   `project_handover.md` §security) instead of connecting as `postgres`.

The Supabase **anon key** is public by design and needs no rotation.
