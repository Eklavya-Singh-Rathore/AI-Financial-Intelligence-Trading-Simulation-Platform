"""Vectorized long/flat backtester (deterministic, dependency-light).

Used as the fast-test engine and as a fallback. Trades a single instrument
long/flat on the SMA-crossover signal, entering on the bar after a signal
(next-bar execution) to avoid look-ahead.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.backtesting.base import BacktestConfig, Backtester, BacktesterError, BacktestResult
from app.backtesting.strategies.sma_crossover import (
    DEFAULT_FAST,
    DEFAULT_SLOW,
    sma_crossover_position,
)

TRADING_DAYS = 252


class SimpleBacktester(Backtester):
    engine = "simple"

    def run(self, df: pd.DataFrame, config: BacktestConfig) -> BacktestResult:
        if df.empty or "close" not in df.columns:
            raise BacktesterError("price frame is empty or missing 'close'")

        fast = int(config.params.get("fast", DEFAULT_FAST))
        slow = int(config.params.get("slow", DEFAULT_SLOW))
        close = df["close"].astype(float)
        if len(close) <= slow:
            raise BacktesterError(
                f"not enough bars ({len(close)}) for slow window {slow}"
            )

        position = sma_crossover_position(close, fast, slow)
        # Enter on the next bar (no look-ahead).
        lagged = position.shift(1).fillna(0.0)
        daily_ret = close.pct_change().fillna(0.0)
        strat_ret = lagged * daily_ret

        equity = (1.0 + strat_ret).cumprod() * config.initial_cash
        final_equity = float(equity.iloc[-1])
        total_return = final_equity / config.initial_cash - 1.0

        n = len(strat_ret)
        ann_factor = TRADING_DAYS / n if n else 0.0
        annualized_return = (1.0 + total_return) ** ann_factor - 1.0 if n else 0.0

        std = float(strat_ret.std(ddof=0))
        mean = float(strat_ret.mean())
        sharpe = (mean / std * np.sqrt(TRADING_DAYS)) if std > 0 else 0.0
        volatility = std * np.sqrt(TRADING_DAYS)

        running_max = equity.cummax()
        drawdown = equity / running_max - 1.0
        max_drawdown = float(drawdown.min())

        trades = int((lagged.diff().abs() > 0).sum())

        metrics = {
            "total_return_pct": round(total_return * 100, 4),
            "annualized_return_pct": round(annualized_return * 100, 4),
            "sharpe_ratio": round(sharpe, 4),
            "volatility_pct": round(volatility * 100, 4),
            "max_drawdown_pct": round(max_drawdown * 100, 4),
            "num_trades": trades,
            "final_equity": round(final_equity, 2),
            "bars": int(n),
        }
        return BacktestResult(
            strategy_name=config.strategy,
            engine=self.engine,
            metrics=metrics,
            meta={"fast": fast, "slow": slow, "initial_cash": config.initial_cash},
        )
