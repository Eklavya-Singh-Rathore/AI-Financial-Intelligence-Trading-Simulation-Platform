"""Tests for the backtesting subsystem (simple engine fast; nautilus marked slow)."""

from __future__ import annotations

import pandas as pd
import pytest
from app.backtesting.base import BacktestConfig, BacktesterError
from app.backtesting.registry import AVAILABLE_ENGINES, get_backtester
from app.backtesting.simple_backtester import SimpleBacktester
from app.backtesting.strategies.sma_crossover import sma_crossover_position


def _config(**overrides) -> BacktestConfig:
    base = {
        "strategy": "sma_crossover",
        "symbol": "TEST",
        "params": {"fast": 10, "slow": 30},
        "initial_cash": 1_000_000.0,
    }
    base.update(overrides)
    return BacktestConfig(**base)


def test_signal_long_in_uptrend():
    close = pd.Series([float(i) for i in range(1, 101)])
    pos = sma_crossover_position(close, fast=5, slow=20)
    assert pos.iloc[-1] == 1.0
    # Before the slow window fills, position must be flat.
    assert (pos.iloc[:19] == 0.0).all()


def test_signal_rejects_bad_windows():
    close = pd.Series([1.0] * 50)
    with pytest.raises(ValueError):
        sma_crossover_position(close, fast=30, slow=10)


def test_simple_backtester_metrics(price_df):
    result = SimpleBacktester().run(price_df, _config())
    assert result.engine == "simple"
    m = result.metrics
    for key in (
        "total_return_pct",
        "annualized_return_pct",
        "sharpe_ratio",
        "max_drawdown_pct",
        "num_trades",
        "final_equity",
    ):
        assert key in m
    assert m["max_drawdown_pct"] <= 0.0
    assert m["num_trades"] >= 1
    assert m["bars"] == len(price_df)


def test_simple_backtester_deterministic(price_df):
    r1 = SimpleBacktester().run(price_df, _config())
    r2 = SimpleBacktester().run(price_df, _config())
    assert r1.metrics == r2.metrics


def test_simple_backtester_insufficient_bars():
    df = pd.DataFrame({"close": [1.0] * 10})
    with pytest.raises(BacktesterError, match="not enough bars"):
        SimpleBacktester().run(df, _config())


def test_registry():
    assert set(AVAILABLE_ENGINES) == {"nautilus", "simple"}
    assert get_backtester("simple").engine == "simple"
    with pytest.raises(ValueError, match="unknown backtest engine"):
        get_backtester("zipline")


@pytest.mark.slow
def test_nautilus_backtester_end_to_end(price_df):
    """Full NautilusTrader engine run over the synthetic frame."""
    result = get_backtester("nautilus").run(price_df, _config())
    assert result.engine == "nautilus"
    m = result.metrics
    assert m["num_fills"] >= 1
    assert "sharpe_ratio" in m
    assert "final_equity" in m
    assert m["final_equity"] > 0
    # Drawdown must reflect PORTFOLIO equity, not cash utilization: with ~95%
    # of capital deployed per trade, the cash-based bug reported ~-95% here.
    assert m["max_drawdown_pct"] > -60.0
    assert m["max_drawdown_pct"] <= 0.0
