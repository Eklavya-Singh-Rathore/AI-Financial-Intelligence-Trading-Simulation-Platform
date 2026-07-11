# Inference Space deployment — Hugging Face (Phase 4.5)

`ai-inference-service` is a **private Gradio-SDK Space on ZeroGPU hardware**
that serves the ML models the Render backend no longer runs in-process:

- **`POST /forecast`** — the official **Kronos** K-line model
  (`NeoQuasar/Kronos-small` + `NeoQuasar/Kronos-Tokenizer-base`, MIT)
- **`POST /embed`** — **MiniLM** sentence embeddings
  (`sentence-transformers/all-MiniLM-L6-v2`, 384-d, normalized)
- **`GET /health`** — open liveness/model status (doubles as the keep-warm ping)
- **`/ui`** — human status page (Gradio) + ZeroGPU smoke-test button

> **Why ZeroGPU, not Docker?** Hugging Face's July-2026 policy gates Docker
> and cpu-basic Gradio Spaces behind PRO ($9/mo); ZeroGPU Spaces remain
> available to free accounts. The app is a FastAPI mounted alongside a minimal
> Gradio UI, so the REST contract is identical to the original Docker design —
> the backend's `space_client` is packaging-agnostic. **All inference runs on
> CPU** (Kronos-small is 24.7M params), so backend traffic consumes **no GPU
> quota**; only the UI smoke-test button touches the GPU slice.
>
> If the owner ever subscribes to PRO, the repo history contains the original
> Docker packaging (Dockerfile + build-time weight bake) — commit `1e0b1db`.

Source of truth: [`infrastructure/hf-space/`](../infrastructure/hf-space/) in
this repo. Deploying = pushing those files to the Space repo. Weights are
**never** stored in the Space repo: they download from the Hub into the
container cache on cold start (~350 MB → cold boots take ~1–2 min extra; the
keep-warm ping makes this rare).

`kronos_src/` inside the Space is a byte-identical copy of
`backend/app/ml/kronos_src/` (the vendored official implementation, MIT +
NOTICE). CI's drift check keeps the two copies in sync — always edit the
backend copy and re-copy.

## Creating / updating the Space

1. Create the Space (once) with the ZeroGPU hardware flavor — free accounts
   cannot create cpu-basic/Docker Spaces:
   ```python
   from huggingface_hub import HfApi
   api = HfApi(token="hf_...")           # write token
   api.create_repo(
       repo_id="Eklavya73/ai-inference-service",
       repo_type="space",
       space_sdk="gradio",
       space_hardware="zero-a10g",       # ZeroGPU
       private=True,
   )
   ```
   (UI path: New Space → SDK **Gradio** → hardware **ZeroGPU** → private.)
2. Push the files:
   ```python
   api.upload_folder(
       folder_path="infrastructure/hf-space",
       repo_id="Eklavya73/ai-inference-service",
       repo_type="space",
       ignore_patterns=["**/__pycache__/**", "*.pyc"],
   )
   ```
3. The Space builds (installs `requirements.txt` + the `sdk_version` pin of
   gradio from the README front-matter), then starts; first start also
   downloads the checkpoints. It's ready when `/health` answers.

## Auth model

| Space visibility | Caller must send | Where configured |
|---|---|---|
| **private** (deployed default) | `Authorization: Bearer <HF token>` — enforced by Hugging Face itself | backend `HF_TOKEN` (fine-grained token, **read** on this Space) |
| public (optional) | `X-API-Key: <shared secret>` — enforced by `app.py` | Space secret `SPACE_API_KEY` + backend `INFERENCE_SPACE_API_KEY` |

Both can be enabled simultaneously. `/health` never requires the X-API-Key
(liveness must stay pingable), but on a private Space it still requires the
HF token.

## Runtime configuration (Space Settings → Variables and secrets)

| Name | Kind | Default | Notes |
|---|---|---|---|
| `KRONOS_MODEL_ID` | variable | `NeoQuasar/Kronos-small` | forecast model (restart to reload) |
| `KRONOS_TOKENIZER_ID` | variable | `NeoQuasar/Kronos-Tokenizer-base` | 〃 |
| `EMBEDDING_MODEL_ID` | variable | `sentence-transformers/all-MiniLM-L6-v2` | must stay 384-d (DB column `vector(384)`) |
| `KRONOS_MAX_CONTEXT` | variable | `512` | matches the checkpoint |
| `SPACE_API_KEY` | secret | unset | only for the public-Space option |

No secrets are required for the private deployment — the models are public
and auth is platform-level.

## Smoke tests

```bash
SPACE=https://eklavya73-ai-inference-service.hf.space
AUTH="Authorization: Bearer $HF_TOKEN"        # omit if the Space is public

curl -s -H "$AUTH" $SPACE/health
# {"status":"ok","kronos_loaded":true,"embedding_loaded":true,...}

curl -s -H "$AUTH" -X POST $SPACE/embed -H "Content-Type: application/json" \
  -d '{"texts":["hello market","prices rising"]}'
# {"vectors":[[...384 floats...],[...]],"dim":384,...}

curl -s -H "$AUTH" -X POST $SPACE/forecast -H "Content-Type: application/json" \
  -d @sample_forecast_payload.json
# {"predictions":[...5 floats...],"model_id":"NeoQuasar/Kronos-small",...}

curl -s -o /dev/null -w "%{http_code}\n" $SPACE/health   # without token: 401 (private)
```

## Sleep & wake behaviour

Free Spaces sleep after **~48 h without requests** and take ~1–2 min to wake
(gateway answers **503** while starting; cold start includes the checkpoint
download). Two layers handle this:

- the backend scheduler pings `/health` every 6 h (`space_keepalive` job), so
  in steady state the Space never sleeps;
- the backend's Space client treats 503 as "waking" and polls for up to
  `INFERENCE_WAKE_MAX_WAIT_SECONDS` (default 180 s) before failing cleanly
  (API 503 → agent runs fall back to the baseline forecaster).

## Upgrade / rollback

- **Code change:** edit `infrastructure/hf-space/` in the repo (kronos_src via
  the backend copy), push to the Space → automatic rebuild/restart.
- **Model change:** update the Space variables and restart; update the
  backend's `KRONOS_MODEL_ID`/`KRONOS_TOKENIZER_ID` to keep metadata truthful.
- **Rollback:** revert the commit on the Space repo (it's plain git).
- **ZeroGPU quota note:** backend endpoints are CPU-only and consume none;
  the `/ui` smoke button consumes a few GPU-seconds per click.
