"""Backtester registry - select a Backtester implementation by engine name."""

from __future__ import annotations

from app.backtesting.base import Backtester
from app.backtesting.nautilus_backtester import NautilusBacktester
from app.backtesting.simple_backtester import SimpleBacktester

AVAILABLE_ENGINES = ("nautilus", "simple")

_CACHE: dict[str, Backtester] = {}


def get_backtester(engine: str | None = None) -> Backtester:
    resolved = (engine or "nautilus").strip().lower()
    if resolved not in AVAILABLE_ENGINES:
        raise ValueError(
            f"unknown backtest engine '{resolved}'. Available: {', '.join(AVAILABLE_ENGINES)}"
        )
    cached = _CACHE.get(resolved)
    if cached is not None:
        return cached
    backtester: Backtester = (
        NautilusBacktester() if resolved == "nautilus" else SimpleBacktester()
    )
    _CACHE[resolved] = backtester
    return backtester
