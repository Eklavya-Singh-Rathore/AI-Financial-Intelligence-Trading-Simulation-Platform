"""ai-inference-service: official Kronos forecasts + MiniLM embeddings.

FastAPI app for a Hugging Face Docker Space. Models load once at startup from
the image's baked HF cache (see Dockerfile / download_models.py); inference is
CPU-only. Endpoints:

  GET  /health    liveness + model status (open; doubles as the keep-warm ping)
  POST /forecast  Kronos close-price forecast for one OHLCV context window
  POST /embed     MiniLM sentence embeddings (384-d, normalized by default)

Auth: a private Space is already gated by Hugging Face itself (Bearer token).
If the SPACE_API_KEY env/secret is set, /forecast and /embed additionally
require a matching X-API-Key header (covers the public-Space option).
"""

from __future__ import annotations

import logging
import math
import os
import threading
import time
from contextlib import asynccontextmanager
from typing import Any

import pandas as pd
import torch
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ai-inference-service")

APP_VERSION = "0.1.0"
KRONOS_MODEL_ID = os.environ.get("KRONOS_MODEL_ID", "NeoQuasar/Kronos-small")
KRONOS_TOKENIZER_ID = os.environ.get("KRONOS_TOKENIZER_ID", "NeoQuasar/Kronos-Tokenizer-base")
EMBEDDING_MODEL_ID = os.environ.get(
    "EMBEDDING_MODEL_ID", "sentence-transformers/all-MiniLM-L6-v2"
)
KRONOS_MAX_CONTEXT = int(os.environ.get("KRONOS_MAX_CONTEXT", "512"))
SPACE_API_KEY = os.environ.get("SPACE_API_KEY", "")

_STATE: dict[str, Any] = {"predictor": None, "embedder": None}
# 2 vCPU on the free tier: serialize Kronos sampling so concurrent requests
# don't thrash each other; embeddings are cheap enough to run unserialized.
_PREDICT_LOCK = threading.Lock()


@asynccontextmanager
async def lifespan(_: FastAPI):
    torch.set_num_threads(2)
    from kronos_src.model import Kronos, KronosPredictor, KronosTokenizer

    log.info("loading kronos model=%s tokenizer=%s", KRONOS_MODEL_ID, KRONOS_TOKENIZER_ID)
    tokenizer = KronosTokenizer.from_pretrained(KRONOS_TOKENIZER_ID)
    model = Kronos.from_pretrained(KRONOS_MODEL_ID)
    _STATE["predictor"] = KronosPredictor(
        model, tokenizer, device="cpu", max_context=KRONOS_MAX_CONTEXT
    )

    from sentence_transformers import SentenceTransformer

    log.info("loading embedder=%s", EMBEDDING_MODEL_ID)
    _STATE["embedder"] = SentenceTransformer(EMBEDDING_MODEL_ID, device="cpu")
    log.info("models ready")
    yield


app = FastAPI(title="ai-inference-service", version=APP_VERSION, lifespan=lifespan)


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


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "kronos_loaded": _STATE["predictor"] is not None,
        "embedding_loaded": _STATE["embedder"] is not None,
        "device": "cpu",
        "torch": torch.__version__,
        "kronos_model_id": KRONOS_MODEL_ID,
        "kronos_tokenizer_id": KRONOS_TOKENIZER_ID,
        "embedding_model_id": EMBEDDING_MODEL_ID,
        "app_version": APP_VERSION,
    }


@app.post("/forecast")
def forecast(payload: ForecastRequest, request: Request) -> dict[str, Any]:
    _require_api_key(request)
    predictor = _STATE["predictor"]
    if predictor is None:
        raise HTTPException(status_code=503, detail="model still loading")

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
            pred_df = predictor.predict(
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
    log.info("forecast ok context=%d horizon=%d elapsed_ms=%d", len(x_df), payload.horizon, elapsed_ms)
    return {
        "predictions": predictions,
        "model_id": KRONOS_MODEL_ID,
        "tokenizer_id": KRONOS_TOKENIZER_ID,
        "context_len": int(len(x_df)),
        "elapsed_ms": elapsed_ms,
    }


@app.post("/embed")
def embed(payload: EmbedRequest, request: Request) -> dict[str, Any]:
    _require_api_key(request)
    embedder = _STATE["embedder"]
    if embedder is None:
        raise HTTPException(status_code=503, detail="model still loading")

    started = time.perf_counter()
    try:
        vectors = embedder.encode(
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
