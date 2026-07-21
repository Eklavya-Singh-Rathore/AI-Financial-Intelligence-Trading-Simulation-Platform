"""Kronos forecaster - wraps the Kronos foundation model for K-line forecasting.

The Kronos runtime classes (KronosTokenizer, Kronos, KronosPredictor) are NOT on
PyPI; their source must be vendored under ``app/ml/kronos_src/`` (from
github.com/shiyu-coder/Kronos, MIT). Until that is present this forecaster raises
a clear ForecasterError and callers fall back to the baseline model.

Model/tokenizer weights are pulled from the Hugging Face Hub
(NeoQuasar/Kronos-*), cached after first load.
"""

from __future__ import annotations

import threading
from typing import Any

import pandas as pd

from app.core.config import get_settings
from app.ml.base import (
    Forecaster,
    ForecasterError,
    ForecastResult,
    resolve_target_timestamps,
)
from app.ml.kronos_variants import resolve_kronos_config

_LOCK = threading.Lock()
_PREDICTOR_CACHE: dict[tuple, Any] = {}


def _load_predictor(model_id: str, tokenizer_id: str, device: str, max_context: int) -> Any:
    key = (model_id, tokenizer_id, device, max_context)
    with _LOCK:
        cached = _PREDICTOR_CACHE.get(key)
        if cached is not None:
            return cached
        try:
            from app.ml.kronos_src.model import Kronos, KronosPredictor, KronosTokenizer
        except Exception as exc:  # noqa: BLE001
            raise ForecasterError(
                "Kronos model source is not available. Vendor it under "
                "app/ml/kronos_src/ (github.com/shiyu-coder/Kronos, MIT) to enable "
                "the 'kronos' forecaster; the 'baseline' model works meanwhile."
            ) from exc
        tokenizer = KronosTokenizer.from_pretrained(tokenizer_id)
        model = Kronos.from_pretrained(model_id)
        predictor = KronosPredictor(model, tokenizer, device=device, max_context=max_context)
        _PREDICTOR_CACHE[key] = predictor
        return predictor


class KronosForecaster(Forecaster):
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
        self.device = settings.kronos_device
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
        predictor = _load_predictor(
            self.model_id, self.tokenizer_id, self.device, self.max_context
        )

        ctx = df.tail(self.max_context).copy()
        x_df = pd.DataFrame(
            {
                "open": ctx["open"].astype(float).to_numpy(),
                "high": ctx["high"].astype(float).to_numpy(),
                "low": ctx["low"].astype(float).to_numpy(),
                "close": ctx["close"].astype(float).to_numpy(),
                "volume": (
                    ctx["volume"].astype(float).to_numpy()
                    if "volume" in ctx.columns
                    else 0.0
                ),
            }
        )
        x_timestamp = pd.Series(pd.to_datetime(ctx.index)).reset_index(drop=True)
        y_timestamp = resolve_target_timestamps(target_timestamps, ctx.index, horizon)

        try:
            pred_df = predictor.predict(
                df=x_df,
                x_timestamp=x_timestamp,
                y_timestamp=y_timestamp,
                pred_len=horizon,
                T=self.temperature,
                top_p=self.top_p,
                sample_count=self.sample_count,
                verbose=False,
            )
            predictions = [float(v) for v in pred_df["close"].tolist()]
        except ForecasterError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ForecasterError(f"Kronos prediction failed: {exc}") from exc

        return ForecastResult(
            model_name=self.name,
            horizon=horizon,
            predictions=predictions,
            meta={
                "model_id": self.model_id,
                "tokenizer_id": self.tokenizer_id,
                "context_len": int(len(ctx)),
                "target_dates": [d.date().isoformat() for d in y_timestamp],
            },
        )
