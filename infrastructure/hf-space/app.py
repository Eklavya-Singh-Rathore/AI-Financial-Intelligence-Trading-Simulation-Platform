"""ai-inference-service: official Kronos forecasts + MiniLM embeddings.

Gradio-SDK Space on ZeroGPU hardware (HF's July-2026 policy gates Docker/
cpu-basic Spaces behind PRO; ZeroGPU remains available to free accounts).
The REST endpoints keep the JSON contracts of the original Docker design, so
the backend's space_client needs no changes:

  GET  /health    liveness + model status (doubles as the keep-warm ping)
  POST /forecast  Kronos close-price forecast for one OHLCV context window
  POST /embed     MiniLM sentence embeddings (384-d, normalized by default)

Serving model: the ZeroGPU harness holds port 7860 until gradio's own
``demo.launch()`` performs the handoff (a self-run uvicorn dies with "address
already in use"), so we launch gradio non-blocking and attach the REST routes
to gradio's FastAPI app, prepended ahead of gradio's routes so no catch-all
can shadow them.

Inference runs on CPU: Kronos-small (24.7M params) takes a few seconds per
forecast and consumes ZERO GPU quota. The @spaces.GPU-decorated button in the
UI exists only to verify the ZeroGPU runtime - the backend never calls it.

Auth: a private Space is gated by Hugging Face itself (Bearer token). If the
SPACE_API_KEY env/secret is set, /forecast and /embed additionally require a
matching X-API-Key header (covers the public-Space option).

Models load at import time; on a cold start the checkpoints download from the
Hub (~350 MB total) into the container cache first.
"""

from __future__ import annotations

import logging
import math
import os
import threading
import time
from typing import Any

try:  # ZeroGPU runtime hook - import before any CUDA use. Harmless elsewhere.
    import spaces  # type: ignore
except Exception:  # noqa: BLE001 - keep the API alive even if the hook breaks
    spaces = None  # type: ignore

import gradio as gr
import pandas as pd
import torch
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ai-inference-service")

APP_VERSION = "0.2.3"  # 0.2: Gradio/ZeroGPU packaging (was Docker)
KRONOS_MODEL_ID = os.environ.get("KRONOS_MODEL_ID", "NeoQuasar/Kronos-small")
KRONOS_TOKENIZER_ID = os.environ.get("KRONOS_TOKENIZER_ID", "NeoQuasar/Kronos-Tokenizer-base")
EMBEDDING_MODEL_ID = os.environ.get(
    "EMBEDDING_MODEL_ID", "sentence-transformers/all-MiniLM-L6-v2"
)
KRONOS_MAX_CONTEXT = int(os.environ.get("KRONOS_MAX_CONTEXT", "512"))
SPACE_API_KEY = os.environ.get("SPACE_API_KEY", "")

# Serialize Kronos sampling; embeddings are cheap and stay unserialized.
_PREDICT_LOCK = threading.Lock()

# ---- load models at import (cold start downloads from the Hub first) -------
torch.set_num_threads(2)
log.info("loading kronos model=%s tokenizer=%s", KRONOS_MODEL_ID, KRONOS_TOKENIZER_ID)
from kronos_src.model import Kronos, KronosPredictor, KronosTokenizer  # noqa: E402

_tokenizer = KronosTokenizer.from_pretrained(KRONOS_TOKENIZER_ID)
_model = Kronos.from_pretrained(KRONOS_MODEL_ID)
PREDICTOR = KronosPredictor(_model, _tokenizer, device="cpu", max_context=KRONOS_MAX_CONTEXT)

log.info("loading embedder=%s", EMBEDDING_MODEL_ID)
from sentence_transformers import SentenceTransformer  # noqa: E402

EMBEDDER = SentenceTransformer(EMBEDDING_MODEL_ID, device="cpu")
log.info("models ready")


# ---- REST API (attached to gradio's FastAPI at launch) ----------------------

api = APIRouter()


def _require_api_key(request: Request) -> None:
    if SPACE_API_KEY and request.headers.get("x-api-key") != SPACE_API_KEY:
        raise HTTPException(status_code=401, detail="invalid or missing X-API-Key")


class ForecastContext(BaseModel):
    open: list[float] = Field(min_length=1)
    high: list[float] = Field(min_length=1)
    low: list[float] = Field(min_length=1)
    close: list[float] = Field(min_length=1)
    volume: list[float] = Field(min_length=1)


class ForecastRequest(BaseModel):
    context: ForecastContext
    x_timestamps: list[str]
    y_timestamps: list[str]
    horizon: int = Field(ge=1, le=60)
    temperature: float = Field(default=1.0, gt=0.0, le=4.0)
    top_p: float = Field(default=0.9, gt=0.0, le=1.0)
    sample_count: int = Field(default=1, ge=1, le=5)

    @model_validator(mode="after")
    def _check_lengths(self) -> "ForecastRequest":
        n = len(self.context.close)
        for name in ("open", "high", "low", "volume"):
            if len(getattr(self.context, name)) != n:
                raise ValueError(f"context.{name} length must match context.close")
        if len(self.x_timestamps) != n:
            raise ValueError("x_timestamps length must match context arrays")
        if len(self.y_timestamps) != self.horizon:
            raise ValueError("y_timestamps length must equal horizon")
        return self


class EmbedRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=64)
    normalize: bool = True

    @model_validator(mode="after")
    def _check_texts(self) -> "EmbedRequest":
        for t in self.texts:
            if len(t) > 10_000:
                raise ValueError("each text must be <= 10000 characters")
        return self


@api.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "kronos_loaded": PREDICTOR is not None,
        "embedding_loaded": EMBEDDER is not None,
        "device": "cpu",
        "torch": torch.__version__,
        "kronos_model_id": KRONOS_MODEL_ID,
        "kronos_tokenizer_id": KRONOS_TOKENIZER_ID,
        "embedding_model_id": EMBEDDING_MODEL_ID,
        "app_version": APP_VERSION,
    }


@api.post("/forecast")
def forecast(payload: ForecastRequest, request: Request) -> dict[str, Any]:
    _require_api_key(request)

    # Defensive context cap (the backend already sends tail(max_context)).
    n = len(payload.context.close)
    start = max(0, n - KRONOS_MAX_CONTEXT)
    x_df = pd.DataFrame(
        {
            "open": payload.context.open[start:],
            "high": payload.context.high[start:],
            "low": payload.context.low[start:],
            "close": payload.context.close[start:],
            "volume": payload.context.volume[start:],
        }
    ).astype(float)
    try:
        x_timestamp = pd.Series(pd.to_datetime(payload.x_timestamps[start:]))
        y_timestamp = pd.Series(pd.to_datetime(payload.y_timestamps))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="unparseable timestamps") from exc

    started = time.perf_counter()
    try:
        with _PREDICT_LOCK:
            pred_df = PREDICTOR.predict(
                df=x_df,
                x_timestamp=x_timestamp,
                y_timestamp=y_timestamp,
                pred_len=payload.horizon,
                T=payload.temperature,
                top_k=0,
                top_p=payload.top_p,
                sample_count=payload.sample_count,
                verbose=False,
            )
        predictions = [float(v) for v in pred_df["close"].tolist()]
    except Exception as exc:  # noqa: BLE001 - never leak internals to callers
        log.exception("forecast failed")
        raise HTTPException(
            status_code=500, detail=f"forecast failed: {type(exc).__name__}"
        ) from exc
    if len(predictions) != payload.horizon or not all(math.isfinite(v) for v in predictions):
        raise HTTPException(status_code=500, detail="forecast failed: invalid output")

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    log.info(
        "forecast ok context=%d horizon=%d elapsed_ms=%d", len(x_df), payload.horizon, elapsed_ms
    )
    return {
        "predictions": predictions,
        "model_id": KRONOS_MODEL_ID,
        "tokenizer_id": KRONOS_TOKENIZER_ID,
        "context_len": int(len(x_df)),
        "elapsed_ms": elapsed_ms,
    }


@api.post("/embed")
def embed(payload: EmbedRequest, request: Request) -> dict[str, Any]:
    _require_api_key(request)

    started = time.perf_counter()
    try:
        vectors = EMBEDDER.encode(
            payload.texts,
            normalize_embeddings=payload.normalize,
            show_progress_bar=False,
        )
        out = [[float(x) for x in vec] for vec in vectors]
    except Exception as exc:  # noqa: BLE001 - never leak internals to callers
        log.exception("embed failed")
        raise HTTPException(
            status_code=500, detail=f"embed failed: {type(exc).__name__}"
        ) from exc

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    log.info("embed ok texts=%d elapsed_ms=%d", len(payload.texts), elapsed_ms)
    return {
        "vectors": out,
        "dim": len(out[0]) if out else 0,
        "model_id": EMBEDDING_MODEL_ID,
        "elapsed_ms": elapsed_ms,
    }


# ---- Gradio UI (root page; also hosts the ZeroGPU smoke check) --------------


def _gpu_smoke() -> str:
    """Prove the ZeroGPU slice attaches. Never called by the backend."""
    return f"cuda_available={torch.cuda.is_available()} torch={torch.__version__}"


if spaces is not None:
    _gpu_smoke = spaces.GPU(duration=10)(_gpu_smoke)

with gr.Blocks(title="ai-inference-service") as demo:
    gr.Markdown(
        "## ai-inference-service\n"
        "API-only Space serving the official **Kronos** K-line model and "
        "**MiniLM** embeddings for the AI Financial Intelligence Platform.\n\n"
        "Endpoints: `GET /health` · `POST /forecast` · `POST /embed` "
        "(see the repo's README for contracts). Inference runs on **CPU** and "
        "consumes no GPU quota; the button below only verifies the ZeroGPU "
        "runtime is healthy."
    )
    btn = gr.Button("ZeroGPU smoke test")
    out = gr.Textbox(label="result")
    btn.click(_gpu_smoke, outputs=out)


def _attach_api(fastapi_app) -> None:  # noqa: ANN001 - gradio's FastAPI subclass
    """Attach the REST routes ahead of gradio's own (no catch-all shadowing)."""
    fastapi_app.include_router(api)
    ours = [
        r
        for r in fastapi_app.router.routes
        if getattr(r, "path", None) in ("/health", "/forecast", "/embed")
    ]
    for route in ours:
        fastapi_app.router.routes.remove(route)
    fastapi_app.router.routes[:0] = ours
    log.info("REST routes attached: /health /forecast /embed")


# Module-level launch, like every classic Spaces app: the platform IMPORTS
# app.py (a __main__ guard never runs there) and only auto-launches `demo`
# itself when the import finishes without a live server - which would skip
# the route attachment. ssr_mode=False is required: gradio 6's SSR puts a
# Node proxy on the public port that only forwards gradio routes, so custom
# REST endpoints would 405. Launch non-blocking, bolt the REST routes onto
# gradio's live FastAPI app, then block to keep the process alive.
served_app, _local_url, _share_url = demo.launch(prevent_thread_lock=True, ssr_mode=False)
_attach_api(served_app)
threading.Event().wait()
