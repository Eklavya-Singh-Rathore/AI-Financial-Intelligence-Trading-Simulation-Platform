"""Unit tests for the paper-trading engine's pure logic. No database, no network."""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import pytest
from app.services.simulation import (
    Bar,
    SimulationError,
    avg_cost_after_buy,
    build_equity_curve,
    compute_metrics,
    derive_proposal,
    trigger_fill_price,
)


def bar(o: float, h: float, low: float, c: float) -> Bar:
    return Bar(
        date=pd.Timestamp("2026-07-01"),
        open=Decimal(str(o)),
        high=Decimal(str(h)),
        low=Decimal(str(low)),
        close=Decimal(str(c)),
    )


# --- daily-bar trigger semantics (all four rules) ----------------------------


def test_buy_limit_triggers_when_low_touches_limit():
    price = trigger_fill_price("buy", "limit", Decimal("100"), None, bar(105, 106, 99, 104))
    assert price == Decimal("100")  # min(open=105, limit=100)


def test_buy_limit_fills_at_open_when_open_below_limit():
    price = trigger_fill_price("buy", "limit", Decimal("100"), None, bar(95, 101, 94, 98))
    assert price == Decimal("95")  # gapped down - better fill at open


def test_buy_limit_no_trigger_above_limit():
    assert trigger_fill_price("buy", "limit", Decimal("100"), None, bar(105, 108, 101, 107)) is None


def test_sell_limit_triggers_when_high_touches_limit():
    price = trigger_fill_price("sell", "limit", Decimal("110"), None, bar(105, 112, 104, 111))
    assert price == Decimal("110")  # max(open=105, limit=110)


def test_sell_limit_fills_at_open_when_open_above_limit():
    price = trigger_fill_price("sell", "limit", Decimal("110"), None, bar(115, 116, 109, 112))
    assert price == Decimal("115")  # gapped up - better fill at open


def test_buy_stop_triggers_when_high_crosses_stop():
    price = trigger_fill_price("buy", "stop", None, Decimal("120"), bar(118, 121, 117, 120))
    assert price == Decimal("120")  # max(open=118, stop=120)


def test_buy_stop_gap_up_fills_at_open():
    price = trigger_fill_price("buy", "stop", None, Decimal("120"), bar(125, 127, 124, 126))
    assert price == Decimal("125")


# --- stop-limit (Phase 6.5) --------------------------------------------------
def test_buy_stop_limit_fills_when_stop_hit_and_limit_reachable():
    # stop=120 (high 121 triggers), limit=122 (low 119 <= 122 reachable)
    price = trigger_fill_price(
        "buy", "stop_limit", Decimal("122"), Decimal("120"), bar(119, 121, 119, 120)
    )
    assert price == Decimal("119")  # min(open=119, limit=122)


def test_buy_stop_limit_no_fill_when_stop_not_triggered():
    price = trigger_fill_price(
        "buy", "stop_limit", Decimal("122"), Decimal("120"), bar(110, 115, 109, 112)
    )
    assert price is None


def test_sell_stop_limit_fills_when_stop_hit_and_limit_reachable():
    # stop=90 (low 89 triggers), limit=88 (high 91 >= 88 reachable)
    price = trigger_fill_price(
        "sell", "stop_limit", Decimal("88"), Decimal("90"), bar(91, 91, 89, 90)
    )
    assert price == Decimal("91")  # max(open=91, limit=88)


def test_stop_loss_sell_triggers_when_low_crosses_stop():
    price = trigger_fill_price("sell", "stop", None, Decimal("90"), bar(92, 93, 89, 91))
    assert price == Decimal("90")  # min(open=92, stop=90)


def test_stop_loss_gap_down_fills_at_open():
    price = trigger_fill_price("sell", "stop", None, Decimal("90"), bar(85, 88, 84, 86))
    assert price == Decimal("85")  # gapped through the stop


def test_stop_no_trigger():
    assert trigger_fill_price("sell", "stop", None, Decimal("90"), bar(95, 97, 93, 96)) is None


# --- average-cost math --------------------------------------------------------


def test_avg_cost_re_average_on_buys():
    avg = avg_cost_after_buy(10, Decimal("100"), 10, Decimal("110"))
    assert avg == Decimal("105.0000")
    avg2 = avg_cost_after_buy(20, avg, 10, Decimal("90"))
    assert avg2 == Decimal("100.0000")


def test_avg_cost_rounds_to_4dp():
    avg = avg_cost_after_buy(3, Decimal("100"), 1, Decimal("101"))
    assert avg == Decimal("100.2500")


# --- equity curve reconstruction ----------------------------------------------


def _closes(dates: list[str], values: list[float]) -> pd.Series:
    return pd.Series(values, index=pd.to_datetime(dates))


def test_equity_curve_cash_only():
    curve = build_equity_curve(
        Decimal("1000000"), pd.Timestamp("2026-07-01"), [], {}
    )
    assert len(curve) == 1
    assert float(curve["equity"].iloc[0]) == 1_000_000.0
    assert float(curve["drawdown_pct"].iloc[0]) == 0.0


def _trade(date: str, side: str, qty: int, price: float, inst: str = "inst1") -> dict:
    return {
        "date": pd.Timestamp(date),
        "instrument_id": inst,
        "side": side,
        "qty": qty,
        "price": price,
    }


def test_equity_curve_buy_then_price_moves():
    closes = {"inst1": _closes(["2026-07-01", "2026-07-02", "2026-07-03"], [100.0, 110.0, 90.0])}
    trades = [_trade("2026-07-01", "buy", 10, 100.0)]
    curve = build_equity_curve(Decimal("2000"), pd.Timestamp("2026-07-01"), trades, closes)
    # day1: cash 1000 + 10*100 = 2000; day2: 1000 + 1100 = 2100; day3: 1000 + 900 = 1900
    assert list(curve["equity"].round(2)) == [2000.0, 2100.0, 1900.0]
    assert float(curve["drawdown_pct"].iloc[2]) == pytest.approx((1900 / 2100 - 1) * 100, abs=1e-6)


def test_equity_curve_round_trip_realizes_cash():
    closes = {"inst1": _closes(["2026-07-01", "2026-07-02", "2026-07-03"], [100.0, 120.0, 120.0])}
    trades = [
        _trade("2026-07-01", "buy", 5, 100.0),
        _trade("2026-07-02", "sell", 5, 120.0),
    ]
    curve = build_equity_curve(Decimal("1000"), pd.Timestamp("2026-07-01"), trades, closes)
    # day1: 500 cash + 500 mv = 1000; day2: sold at 120 -> cash 1100, qty 0
    assert list(curve["equity"].round(2)) == [1000.0, 1100.0, 1100.0]


def test_equity_curve_day_one_portfolio_ffills_last_close():
    """Regression: portfolio created AFTER the last bar (e.g. bought today
    before today's ingest). The single calendar day must value holdings at the
    last known close, not 0 (reindex-then-ffill dropped the history)."""
    closes = {"inst1": _closes(["2026-07-15", "2026-07-16"], [95.0, 100.0])}
    trades = [_trade("2026-07-17", "buy", 10, 100.0)]
    curve = build_equity_curve(Decimal("2000"), pd.Timestamp("2026-07-17"), trades, closes)
    assert len(curve) == 1
    # cash 2000 - 1000 = 1000; holdings 10 * ffilled close 100 = 1000
    assert float(curve["holdings"].iloc[0]) == 1000.0
    assert float(curve["equity"].iloc[0]) == 2000.0


def test_equity_curve_weekend_gap_ffills():
    """Calendar days past an instrument's last bar keep the last close."""
    closes = {
        "inst1": _closes(["2026-07-01", "2026-07-02"], [100.0, 110.0]),
        "inst2": _closes(["2026-07-01", "2026-07-02", "2026-07-03"], [50.0, 50.0, 60.0]),
    }
    trades = [_trade("2026-07-01", "buy", 10, 100.0, inst="inst1")]
    curve = build_equity_curve(Decimal("1000"), pd.Timestamp("2026-07-01"), trades, closes)
    # inst2's 07-03 bar extends the calendar; inst1 has no 07-03 bar -> ffill 110.
    assert list(curve["equity"].round(2)) == [1000.0, 1100.0, 1100.0]


# --- metrics -------------------------------------------------------------------


def test_metrics_flat_equity_all_zero():
    dates = pd.to_datetime(["2026-07-01", "2026-07-02", "2026-07-03"])
    equity = pd.Series([100.0, 100.0, 100.0], index=dates)
    m = compute_metrics(equity, [])
    assert m["total_return_pct"] == 0.0
    assert m["sharpe_ratio"] == 0.0
    assert m["max_drawdown_pct"] == 0.0
    assert m["win_rate"] is None


def test_metrics_growth_and_drawdown():
    equity = pd.Series(
        [100.0, 110.0, 99.0, 121.0],
        index=pd.to_datetime(["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-06"]),
    )
    m = compute_metrics(equity, [50.0, -20.0, 10.0])
    assert m["total_return_pct"] == pytest.approx(21.0)
    assert m["max_drawdown_pct"] == pytest.approx((99 / 110 - 1) * 100, abs=1e-4)
    assert m["win_rate"] == pytest.approx(2 / 3, abs=1e-4)
    assert m["closed_trades"] == 3
    assert m["sharpe_ratio"] != 0.0
    assert m["volatility_pct"] > 0
    assert m["cagr_pct"] > 0


def test_metrics_sortino_uses_downside_only():
    # Two negative returns with different sizes -> downside std > 0.
    equity = pd.Series(
        [100.0, 108.0, 104.0, 112.0, 106.0],
        index=pd.to_datetime(
            ["2026-07-01", "2026-07-02", "2026-07-03", "2026-07-06", "2026-07-07"]
        ),
    )
    m = compute_metrics(equity, [])
    assert m["sortino_ratio"] != 0.0
    # Sortino divides by the (smaller) downside std -> larger magnitude than Sharpe.
    assert abs(m["sortino_ratio"]) >= abs(m["sharpe_ratio"])


# --- AI proposal derivation -----------------------------------------------------


def _decision(**over) -> dict:
    base = {
        "action": "BUY",
        "size_pct": 10.0,
        "confidence": 0.7,
        "summary": "test",
        "risk_verdict": "approve",
        "limited_by": [],
    }
    base.update(over)
    return base


def test_proposal_buy_qty_floor():
    side, qty = derive_proposal(_decision(), equity=1_000_000.0, latest_close=1295.5, held_qty=0)
    assert side == "buy"
    assert qty == int(0.10 * 1_000_000 / 1295.5)  # floor


def test_proposal_sell_capped_at_held():
    side, qty = derive_proposal(
        _decision(action="SELL", size_pct=50.0), equity=1_000_000.0, latest_close=100.0, held_qty=7
    )
    assert (side, qty) == ("sell", 7)


def test_proposal_hold_rejected():
    with pytest.raises(SimulationError, match="BUY or SELL"):
        derive_proposal(_decision(action="HOLD"), 1_000_000.0, 100.0, 0)


def test_proposal_veto_rejected():
    with pytest.raises(SimulationError, match="vetoed"):
        derive_proposal(_decision(risk_verdict="veto"), 1_000_000.0, 100.0, 0)


def test_proposal_zero_size_rejected():
    with pytest.raises(SimulationError, match="vetoed|zero"):
        derive_proposal(_decision(size_pct=0.0), 1_000_000.0, 100.0, 0)


def test_proposal_too_small_rejected():
    with pytest.raises(SimulationError, match="too small"):
        derive_proposal(_decision(size_pct=0.001), 10_000.0, 5000.0, 0)


def test_proposal_sell_nothing_held_rejected():
    with pytest.raises(SimulationError, match="no held shares"):
        derive_proposal(_decision(action="SELL"), 1_000_000.0, 100.0, 0)
