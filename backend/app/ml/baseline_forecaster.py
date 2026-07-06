"""Baseline drift forecaster.

A simple, deterministic random-walk-with-drift model: future close = last close +
step * mean recent daily change. Used for fast tests and as a graceful fallback
when the Kronos model is unavailable. Never downloads anything.
"""

from __future__ import annotations

import pandas as pd

from app.ml.base import Forecaster, ForecastResult


class BaselineForecaster(Forecaster):
    name = "baseline"

    def __init__(self, lookback: int = 30) -> None:
        self.lookback = lookback

    def forecast(self, df: pd.DataFrame, horizon: int) -> ForecastResult:
        self._validate(df, horizon)
        close = df["close"].astype(float)
        last_close = float(close.iloc[-1])
        diffs = close.diff().dropna()
        drift = float(diffs.tail(self.lookback).mean()) if len(diffs) else 0.0
        if pd.isna(drift):
            drift = 0.0
        predictions = [last_close + drift * (i + 1) for i in range(horizon)]
        return ForecastResult(
            model_name=self.name,
            horizon=horizon,
            predictions=predictions,
            meta={"last_close": last_close, "drift": drift, "lookback": self.lookback},
        )
