"""Forecaster interface shared by all forecasting models.

Concrete implementations (baseline drift model, Kronos) live alongside this and
are selected via ``app.ml.registry``. Keeping a narrow interface lets callers
(endpoints, scheduler) stay agnostic to the underlying model.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class ForecastResult:
    """Output of a forecast run: one predicted close per future step."""

    model_name: str
    horizon: int
    predictions: list[float]
    meta: dict = field(default_factory=dict)


class ForecasterError(RuntimeError):
    """Raised when a forecaster cannot produce a forecast (e.g. model missing)."""


class Forecaster(ABC):
    """Abstract price forecaster.

    ``df`` is indexed by date (ascending) with float columns
    ``open, high, low, close, volume`` (and optionally ``adj_close``).
    """

    name: str = "base"

    @abstractmethod
    def forecast(self, df: pd.DataFrame, horizon: int) -> ForecastResult:
        raise NotImplementedError

    @staticmethod
    def _validate(df: pd.DataFrame, horizon: int) -> None:
        if horizon < 1:
            raise ValueError("horizon must be >= 1")
        if "close" not in df.columns:
            raise ValueError("price frame must contain a 'close' column")
        if df.empty:
            raise ForecasterError("no price history available to forecast from")
