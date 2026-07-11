# Inference Space deployment — Hugging Face (Phase 4.5)

`ai-inference-service` is a **private Docker Space** on the free **CPU Basic**
hardware (2 vCPU / 16 GB RAM / 50 GB disk) that serves the ML models the
Render backend no longer runs in-process:

- **`POST /forecast`** — the official **Kronos** K-line model
  (`NeoQuasar/Kronos-small` + `NeoQuasar/Kronos-Tokenizer-base`, MIT)
- **`POST /embed`** — **MiniLM** sentence embeddings
  (`sentence-transformers/all-MiniLM-L6-v2`, 384-d, normalized)
- **`GET /health`** — open liveness/model status (doubles as the keep-warm ping)

Source of truth: [`infrastructure/hf-space/`](../infrastructure/hf-space/) in
this repo. Deploying = pushing those files to the Space repo. The Space repo
never contains model weights — `download_models.py` bakes them into the Docker
image from the Hub at **build** time, and the container runs with
`HF_HUB_OFFLINE=1` (wakes never re-download).

`kronos_src/` inside the Space is a byte-identical copy of
`backend/app/ml/kronos_src/` (the vendored official implementation, MIT +
NOTICE). CI's drift check keeps the two copies in sync — always edit the
backend copy and re-copy.

## Creating / updating the Space

1. Create the Space (once): huggingface.co → **New Space** → name
   `ai-inference-service`, SDK **Docker**, visibility **private**, hardware
   **CPU Basic** (or via API:
   `POST https://huggingface.co/api/repos/create` with
   `{"name":"ai-inference-service","type":"space","private":true,"sdk":"docker"}`).
2. Push the files (any of):
   - `huggingface_hub` (used for the Phase 4.5 deployment):
     ```python
     from huggingface_hub import HfApi
     HfApi(token="hf_...").upload_folder(
         folder_path="infrastructure/hf-space",
         repo_id="Eklavya73/ai-inference-service",
         repo_type="space",
         commit_message="deploy",
         ignore_patterns=["__pycache__/*", "*.pyc"],
     )
     ```
   - or git: `git clone https://huggingface.co/spaces/Eklavya73/ai-inference-service`,
     copy the folder contents in, commit, push (token as password).
3. The Space builds automatically (~5–10 min first time: CPU torch + weight
   bake). Status is visible on the Space page; it's ready when `/health`
   answers.

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
| `KRONOS_MODEL_ID` | variable | `NeoQuasar/Kronos-small` | change → **factory rebuild** to re-bake weights |
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

Free Spaces sleep after **~48 h without requests** and take ~1 min to wake
(the gateway answers **503** while starting). Two layers handle this:

- the backend scheduler pings `/health` every 6 h (`space_keepalive` job), so
  in steady state the Space never sleeps;
- the backend's Space client treats 503 as "waking" and polls for up to
  `INFERENCE_WAKE_MAX_WAIT_SECONDS` (default 180 s) before failing cleanly
  (API 503 → agent runs fall back to the baseline forecaster).

## Upgrade / rollback

- **Code change:** edit `infrastructure/hf-space/` in the repo (kronos_src via
  the backend copy), push to the Space → automatic rebuild. Weights layer is
  cached unless `download_models.py`/requirements changed.
- **Model change:** update the variables *and* trigger a **factory rebuild**
  (Settings) so the bake layer re-runs; update the backend's
  `KRONOS_MODEL_ID`/`KRONOS_TOKENIZER_ID` to keep metadata truthful.
- **Rollback:** revert the commit on the Space repo (it's plain git).
