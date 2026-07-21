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
    def forecast(
        self,
        df: pd.DataFrame,
        horizon: int,
        *,
        target_timestamps: pd.Series | None = None,
    ) -> ForecastResult:
        """Forecast ``horizon`` future closes.

        ``target_timestamps`` (optional) are the future bar timestamps the caller
        wants predicted - supplied for non-daily intervals so the model sees the
        right temporal context. When omitted, implementations default to the next
        business days (daily behaviour), preserving existing callers.
        """
        raise NotImplementedError

    @staticmethod
    def _validate(df: pd.DataFrame, horizon: int) -> None:
        if horizon < 1:
            raise ValueError("horizon must be >= 1")
        if "close" not in df.columns:
            raise ValueError("price frame must contain a 'close' column")
        if df.empty:
            raise ForecasterError("no price history available to forecast from")


def resolve_target_timestamps(
    target_timestamps: pd.Series | None, index: pd.Index, horizon: int
) -> pd.Series:
    """The future timestamps to predict: the caller's if given, else business days.

    Shared by the Kronos forecasters so local and remote build identical model
    inputs. Business-day default keeps daily forecasting unchanged.
    """
    if target_timestamps is not None:
        return pd.Series(pd.to_datetime(list(target_timestamps))).reset_index(drop=True)
    last = pd.to_datetime(index[-1])
    return pd.Series(pd.bdate_range(start=last + pd.offsets.BDay(1), periods=horizon))
