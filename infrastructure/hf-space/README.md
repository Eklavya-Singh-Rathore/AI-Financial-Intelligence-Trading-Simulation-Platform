---
title: AI Inference Service
emoji: 📈
colorFrom: indigo
colorTo: green
sdk: gradio
sdk_version: 6.20.0
app_file: app.py
pinned: false
license: mit
short_description: Kronos K-line forecasts + MiniLM embeddings API
---

# ai-inference-service

Private inference API for the AI Financial Intelligence Trading Simulation
Platform (Phase 4.5). Serves the **official Kronos** checkpoints
([NeoQuasar/Kronos-small](https://huggingface.co/NeoQuasar/Kronos-small) +
[NeoQuasar/Kronos-Tokenizer-base](https://huggingface.co/NeoQuasar/Kronos-Tokenizer-base),
MIT) and **MiniLM** embeddings
([sentence-transformers/all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2))
so the Render-hosted backend can run without torch.

**Packaging:** Gradio-SDK Space on **ZeroGPU** hardware (HF's July-2026 policy
gates Docker/cpu-basic Spaces behind PRO; ZeroGPU remains free). The REST API
is a FastAPI app with the Gradio UI mounted at `/ui`. **All inference runs on
CPU** — Kronos-small is 24.7M params — so requests consume **no GPU quota**;
the UI's "ZeroGPU smoke test" button is the only GPU-decorated function.

Model weights are **not** stored in this repo: they download from the Hub into
the container cache on cold start (~350 MB, adds ~1–2 min to a cold boot).

`kronos_src/` is a verbatim copy of the official Kronos implementation
(github.com/shiyu-coder/Kronos, MIT — see `kronos_src/NOTICE.md`). It is kept
byte-identical to `backend/app/ml/kronos_src/` in the main repo (CI enforces
the diff).

## Endpoints

| Route | Auth | Purpose |
|---|---|---|
| `GET /health` | none | liveness + model-loaded status (also the keep-warm ping) |
| `POST /forecast` | private Space token / optional `X-API-Key` | Kronos close-price forecast |
| `POST /embed` | private Space token / optional `X-API-Key` | MiniLM sentence embeddings (384-d) |
| `/ui` | 〃 | human status page + ZeroGPU smoke test |

When the Space is **private** (default deployment), Hugging Face itself
rejects unauthenticated requests — callers send `Authorization: Bearer <HF
read token>`. Setting the `SPACE_API_KEY` secret additionally requires an
`X-API-Key` header on `/forecast` and `/embed` (used if the Space is ever made
public).

### POST /forecast

```json
{
  "context": {"open": [..], "high": [..], "low": [..], "close": [..], "volume": [..]},
  "x_timestamps": ["2026-06-01T00:00:00", "..."],
  "y_timestamps": ["2026-07-13T00:00:00", "..."],
  "horizon": 5,
  "temperature": 1.0,
  "top_p": 0.9,
  "sample_count": 1
}
```

→ `{"predictions": [..], "model_id": "...", "tokenizer_id": "...", "context_len": 512, "elapsed_ms": 2100}`

### POST /embed

`{"texts": ["...", "..."], "normalize": true}` →
`{"vectors": [[384 floats], ...], "dim": 384, "model_id": "...", "elapsed_ms": 40}`

## Configuration (Space Settings → Variables / Secrets)

| Name | Kind | Default | Purpose |
|---|---|---|---|
| `KRONOS_MODEL_ID` | variable | `NeoQuasar/Kronos-small` | forecast model |
| `KRONOS_TOKENIZER_ID` | variable | `NeoQuasar/Kronos-Tokenizer-base` | forecast tokenizer |
| `EMBEDDING_MODEL_ID` | variable | `sentence-transformers/all-MiniLM-L6-v2` | embedding model |
| `KRONOS_MAX_CONTEXT` | variable | `512` | context cap (matches checkpoint) |
| `SPACE_API_KEY` | secret | unset | optional shared-secret gate |

Source of truth for these files: `infrastructure/hf-space/` in the main
project repository — edit there and push here.
