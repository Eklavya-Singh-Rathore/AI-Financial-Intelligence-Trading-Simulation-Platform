---
title: AI Inference Service
emoji: 📈
colorFrom: indigo
colorTo: green
sdk: docker
app_port: 7860
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

Model weights are **not** stored in this repo: they are downloaded from the
Hugging Face Hub at Docker **build** time into the image's HF cache
(`download_models.py`), and the container runs with `HF_HUB_OFFLINE=1` —
restarts and wakes never re-download anything.

`kronos_src/` is a verbatim copy of the official Kronos implementation
(github.com/shiyu-coder/Kronos, MIT — see `kronos_src/NOTICE.md` for
provenance and the single relative-import fix). It is kept byte-identical to
`backend/app/ml/kronos_src/` in the main repo (CI enforces the diff).

## Endpoints

| Route | Auth | Purpose |
|---|---|---|
| `GET /health` | none | liveness + model-loaded status (also the keep-warm ping) |
| `POST /forecast` | private Space token / optional `X-API-Key` | Kronos close-price forecast |
| `POST /embed` | private Space token / optional `X-API-Key` | MiniLM sentence embeddings (384-d) |

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
