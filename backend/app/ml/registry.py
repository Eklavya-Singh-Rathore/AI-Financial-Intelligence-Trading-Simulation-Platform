"""Forecaster registry - select a Forecaster implementation by name.

Instances are cached. ``kronos`` is the default (configurable); ``baseline`` is
always available and used for fast tests and as a fallback.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.ml.base import Forecaster
from app.ml.baseline_forecaster import BaselineForecaster
from app.ml.kronos_forecaster import KronosForecaster

AVAILABLE_FORECASTERS = ("kronos", "baseline")

_CACHE: dict[str, Forecaster] = {}


def get_forecaster(name: str | None = None) -> Forecaster:
    resolved = (name or get_settings().default_forecaster or "kronos").strip().lower()
    if resolved not in AVAILABLE_FORECASTERS:
        raise ValueError(
            f"unknown forecaster '{resolved}'. Available: {', '.join(AVAILABLE_FORECASTERS)}"
        )
    cached = _CACHE.get(resolved)
    if cached is not None:
        return cached
    forecaster: Forecaster = (
        KronosForecaster() if resolved == "kronos" else BaselineForecaster()
    )
    _CACHE[resolved] = forecaster
    return forecaster
