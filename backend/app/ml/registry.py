"""Forecaster registry - select a Forecaster implementation by name.

Instances are cached. ``kronos`` is the default (configurable); ``baseline`` is
always available and used for fast tests and as a fallback. ``KRONOS_MODE``
picks the kronos implementation: ``local`` (in-process torch, dev default) or
``remote`` (Hugging Face inference Space, production) - the public name stays
``kronos`` either way so API params and persisted model names never change.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.ml.base import Forecaster
from app.ml.baseline_forecaster import BaselineForecaster
from app.ml.kronos_forecaster import KronosForecaster
from app.ml.remote_kronos_forecaster import RemoteKronosForecaster

AVAILABLE_FORECASTERS = ("kronos", "baseline")

_CACHE: dict[str, Forecaster] = {}


def get_forecaster(name: str | None = None) -> Forecaster:
    settings = get_settings()
    resolved = (name or settings.default_forecaster or "kronos").strip().lower()
    if resolved not in AVAILABLE_FORECASTERS:
        raise ValueError(
            f"unknown forecaster '{resolved}'. Available: {', '.join(AVAILABLE_FORECASTERS)}"
        )
    mode = "local"
    if resolved == "kronos" and settings.kronos_mode.strip().lower() == "remote":
        mode = "remote"
    key = f"{resolved}:{mode}"
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    forecaster: Forecaster
    if resolved == "kronos":
        forecaster = RemoteKronosForecaster() if mode == "remote" else KronosForecaster()
    else:
        forecaster = BaselineForecaster()
    _CACHE[key] = forecaster
    return forecaster
