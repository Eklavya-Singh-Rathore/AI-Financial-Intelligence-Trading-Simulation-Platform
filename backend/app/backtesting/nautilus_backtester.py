"""NautilusTrader-backed backtester (production-grade engine).

Runs an SMA-crossover strategy over daily bars using NautilusTrader's low-level
``BacktestEngine``. A single simulated equity on a CASH account trades long/flat;
metrics come from the engine's portfolio analyzer. The instrument is a simulated
vehicle (USD/XNAS) - only relative price dynamics matter for the strategy stats.
"""

from __future__ import annotations

import re

import pandas as pd

from app.backtesting.base import BacktestConfig, Backtester, BacktesterError, BacktestResult
from app.backtesting.strategies.sma_crossover import DEFAULT_FAST, DEFAULT_SLOW

_IMPORT_ERROR: str | None = None
try:
    from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
    from nautilus_trader.config import LoggingConfig
    from nautilus_trader.core.datetime import dt_to_unix_nanos
    from nautilus_trader.indicators.averages import SimpleMovingAverage
    from nautilus_trader.model.currencies import USD
    from nautilus_trader.model.data import Bar, BarType
    from nautilus_trader.model.enums import AccountType, OmsType, OrderSide
    from nautilus_trader.model.identifiers import InstrumentId, Venue
    from nautilus_trader.model.objects import Money
    from nautilus_trader.test_kit.providers import TestInstrumentProvider
    from nautilus_trader.trading.strategy import Strategy, StrategyConfig

    class _SMAConfig(StrategyConfig, frozen=True):  # type: ignore[call-arg]
        instrument_id: str
        bar_type: str
        fast: int = 10
        slow: int = 30
        trade_size: int = 100

    class _SMACrossStrategy(Strategy):
        def __init__(self, config: _SMAConfig) -> None:
            super().__init__(config)
            self.fast = SimpleMovingAverage(config.fast)
            self.slow = SimpleMovingAverage(config.slow)

        def on_start(self) -> None:
            self._iid = InstrumentId.from_str(self.config.instrument_id)
            self._bt = BarType.from_str(self.config.bar_type)
            self._instrument = self.cache.instrument(self._iid)
            self.register_indicator_for_bars(self._bt, self.fast)
            self.register_indicator_for_bars(self._bt, self.slow)
            self.subscribe_bars(self._bt)

        def on_bar(self, bar: Bar) -> None:
            if not self.slow.initialized:
                return
            net_long = self.portfolio.is_net_long(self._iid)
            if self.fast.value > self.slow.value and not net_long:
                order = self.order_factory.market(
                    self._iid,
                    OrderSide.BUY,
                    self._instrument.make_qty(self.config.trade_size),
                )
                self.submit_order(order)
            elif self.fast.value < self.slow.value and net_long:
                self.close_all_positions(self._iid)

except Exception as exc:  # noqa: BLE001 - nautilus optional at import time
    _IMPORT_ERROR = str(exc)


def _sanitize_symbol(symbol: str) -> str:
    cleaned = re.sub(r"[^A-Z0-9]", "", symbol.upper())
    return cleaned or "ASSET"


class NautilusBacktester(Backtester):
    engine = "nautilus"

    def run(self, df: pd.DataFrame, config: BacktestConfig) -> BacktestResult:
        if _IMPORT_ERROR is not None:
            raise BacktesterError(f"NautilusTrader unavailable: {_IMPORT_ERROR}")
        if df.empty or "close" not in df.columns:
            raise BacktesterError("price frame is empty or missing 'close'")

        fast = int(config.params.get("fast", DEFAULT_FAST))
        slow = int(config.params.get("slow", DEFAULT_SLOW))
        if fast >= slow:
            raise BacktesterError("fast window must be smaller than slow window")
        if len(df) <= slow:
            raise BacktesterError(f"not enough bars ({len(df)}) for slow window {slow}")

        symbol = _sanitize_symbol(config.symbol)
        bt_engine = BacktestEngine(
            config=BacktestEngineConfig(
                trader_id="BACKTESTER-001",
                logging=LoggingConfig(bypass_logging=True),
            )
        )
        venue = Venue("XNAS")
        bt_engine.add_venue(
            venue=venue,
            oms_type=OmsType.NETTING,
            account_type=AccountType.CASH,
            base_currency=USD,
            starting_balances=[Money(config.initial_cash, USD)],
        )
        instrument = TestInstrumentProvider.equity(symbol, "XNAS")
        bt_engine.add_instrument(instrument)
        bar_type = BarType.from_str(f"{instrument.id}-1-DAY-LAST-EXTERNAL")

        first_close = float(df["close"].iloc[0])
        trade_size = max(1, int(config.initial_cash * 0.95 / first_close))

        bt_engine.add_data(self._build_bars(df, instrument, bar_type))
        strategy = _SMACrossStrategy(
            _SMAConfig(
                instrument_id=str(instrument.id),
                bar_type=str(bar_type),
                fast=fast,
                slow=slow,
                trade_size=trade_size,
            )
        )
        bt_engine.add_strategy(strategy)

        try:
            bt_engine.run()
            metrics = self._extract_metrics(bt_engine, venue, config.initial_cash)
        finally:
            bt_engine.dispose()

        return BacktestResult(
            strategy_name=config.strategy,
            engine=self.engine,
            metrics=metrics,
            meta={
                "fast": fast,
                "slow": slow,
                "trade_size": trade_size,
                "initial_cash": config.initial_cash,
                "sim_symbol": symbol,
            },
        )

    @staticmethod
    def _build_bars(df: pd.DataFrame, instrument, bar_type) -> list:
        has_vol = "volume" in df.columns
        bars = []
        for ts_index, row in df.iterrows():
            ts = dt_to_unix_nanos(pd.Timestamp(ts_index).tz_localize("UTC"))
            volume = int(row["volume"]) if has_vol and pd.notna(row["volume"]) else 0
            bars.append(
                Bar(
                    bar_type,
                    instrument.make_price(float(row["open"])),
                    instrument.make_price(float(row["high"])),
                    instrument.make_price(float(row["low"])),
                    instrument.make_price(float(row["close"])),
                    instrument.make_qty(volume),
                    ts,
                    ts,
                )
            )
        return bars

    @staticmethod
    def _extract_metrics(bt_engine, venue, initial_cash: float) -> dict:
        result = bt_engine.get_result()
        pnl = (result.stats_pnls or {}).get("USD", {})
        rets = result.stats_returns or {}

        final_equity = float(initial_cash)
        max_dd = 0.0
        acct = bt_engine.trader.generate_account_report(venue)
        if acct is not None and len(acct) and "total" in acct.columns:
            totals = pd.to_numeric(acct["total"], errors="coerce").dropna()
            if len(totals):
                final_equity = float(totals.iloc[-1])
                running_max = totals.cummax()
                drawdown = totals / running_max - 1.0
                max_dd = float(drawdown.min())

        fills = bt_engine.trader.generate_order_fills_report()
        num_fills = 0 if fills is None else len(fills)
        total_return_pct = (final_equity / initial_cash - 1.0) * 100.0

        def _num(mapping: dict, key: str, default: float = 0.0) -> float:
            value = mapping.get(key, default)
            return float(value) if value is not None else default

        return {
            "total_return_pct": round(total_return_pct, 4),
            "pnl_total": _num(pnl, "PnL (total)"),
            "pnl_pct": _num(pnl, "PnL% (total)"),
            "sharpe_ratio": round(_num(rets, "Sharpe Ratio (252 days)"), 4),
            "sortino_ratio": round(_num(rets, "Sortino Ratio (252 days)"), 4),
            "volatility_pct": round(_num(rets, "Returns Volatility (252 days)") * 100, 4),
            "profit_factor": round(_num(pnl, "Profit Factor"), 4),
            "win_rate": round(_num(pnl, "Win Rate"), 4),
            "max_drawdown_pct": round(max_dd * 100, 4),
            "final_equity": round(final_equity, 2),
            "num_fills": num_fills,
            "bars": int(len(acct)) if acct is not None else 0,
        }
