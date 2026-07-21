"""Remote Kronos forecaster - same model, served by the inference Space.

Phase 4.5: production backends do not ship torch, so ``KRONOS_MODE=remote``
swaps the in-process :class:`KronosForecaster` for this class. It keeps the
public name ``"kronos"`` (API ``model`` param, ``default_forecaster`` and the
persisted ``model_name`` stay identical to localhost) and builds the exact
same inputs the local path builds - context window, OHLCV arrays and
business-day target timestamps are all computed here and sent as plain JSON,
so forecasting semantics do not depend on the Space.

Failures are normalized to :class:`ForecasterError`, preserving both existing
contracts: the API maps it to HTTP 503 and the agent orchestrator falls back
to the baseline model.
"""

from __future__ import annotations

import math
import time

import pandas as pd

from app.core.config import get_settings
from app.ml.base import (
    Forecaster,
    ForecasterError,
    ForecastResult,
    resolve_target_timestamps,
)
from app.ml.kronos_variants import resolve_kronos_config


class RemoteKronosForecaster(Forecaster):
    name = "kronos"

    def __init__(
        self,
        *,
        temperature: float = 1.0,
        top_p: float = 0.9,
        sample_count: int = 1,
    ) -> None:
        settings = get_settings()
        cfg = resolve_kronos_config(settings)
        self.model_id = cfg.model_id
        self.tokenizer_id = cfg.tokenizer_id
        self.max_context = cfg.max_context
        self.temperature = temperature
        self.top_p = top_p
        self.sample_count = sample_count

    def forecast(
        self,
        df: pd.DataFrame,
        horizon: int,
        *,
        target_timestamps: pd.Series | None = None,
    ) -> ForecastResult:
        self._validate(df, horizon)
        # Lazy import keeps module import free of httpx-related side effects
        # and mirrors how the local forecaster defers its heavy imports.
        from app.services.space_client import SpaceClientError, get_space_client

        ctx = df.tail(self.max_context).copy()
        volume = (
            ctx["volume"].astype(float).tolist()
            if "volume" in ctx.columns
            else [0.0] * len(ctx)
        )
        x_timestamp = pd.Series(pd.to_datetime(ctx.index)).reset_index(drop=True)
        y_timestamp = resolve_target_timestamps(target_timestamps, ctx.index, horizon)
        payload = {
            "context": {
                "open": ctx["open"].astype(float).tolist(),
                "high": ctx["high"].astype(float).tolist(),
                "low": ctx["low"].astype(float).tolist(),
                "close": ctx["close"].astype(float).tolist(),
                "volume": volume,
            },
            "x_timestamps": [t.isoformat() for t in x_timestamp],
            "y_timestamps": [t.isoformat() for t in y_timestamp],
            "horizon": horizon,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "sample_count": self.sample_count,
        }

        started = time.perf_counter()
        try:
            data = get_space_client().post_json("/forecast", payload, op="forecast")
        except SpaceClientError as exc:
            raise ForecasterError(f"Kronos remote inference failed: {exc}") from exc

        raw = data.get("predictions")
        if not isinstance(raw, list) or len(raw) != horizon:
            raise ForecasterError(
                "Kronos remote inference failed: unexpected prediction count"
            )
        try:
            predictions = [float(v) for v in raw]
        except (TypeError, ValueError) as exc:
            raise ForecasterError(
                "Kronos remote inference failed: non-numeric prediction values"
            ) from exc
        if not all(math.isfinite(v) for v in predictions):
            raise ForecasterError(
                "Kronos remote inference failed: non-finite prediction values"
            )

        elapsed_ms = data.get("elapsed_ms")
        if not isinstance(elapsed_ms, (int, float)):
            elapsed_ms = int((time.perf_counter() - started) * 1000)
        return ForecastResult(
            model_name=self.name,
            horizon=horizon,
            predictions=predictions,
            meta={
                "model_id": data.get("model_id") or self.model_id,
                "tokenizer_id": data.get("tokenizer_id") or self.tokenizer_id,
                "context_len": int(len(ctx)),
                "target_dates": [d.date().isoformat() for d in y_timestamp],
                "mode": "remote",
                "space_latency_ms": int(elapsed_ms),
            },
        )
