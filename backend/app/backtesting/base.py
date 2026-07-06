"""Backtester interface shared by the simple and NautilusTrader engines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date

import pandas as pd


@dataclass
class BacktestConfig:
    strategy: str
    symbol: str
    params: dict
    initial_cash: float = 1_000_000.0
    start: date | None = None
    end: date | None = None


@dataclass
class BacktestResult:
    strategy_name: str
    engine: str
    metrics: dict
    meta: dict = field(default_factory=dict)


class BacktesterError(RuntimeError):
    """Raised when a backtest cannot be run (bad config, engine missing, ...)."""


class Backtester(ABC):
    """Runs a strategy over a price frame (indexed by date, OHLCV columns)."""

    engine: str = "base"

    @abstractmethod
    def run(self, df: pd.DataFrame, config: BacktestConfig) -> BacktestResult:
        raise NotImplementedError
