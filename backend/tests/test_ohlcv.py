"""Pure-logic tests for the multi-interval OHLCV resolver (Phase 6.5).

The intraday fetch itself needs live yfinance (covered in db/live verification);
here we test the pure pieces: interval config, time formatting, and resampling.
"""

from __future__ import annotations

import pandas as pd
from app.services import ohlcv


def test_interval_config_and_helpers():
    assert ohlcv.DEFAULT_INTERVAL == "1D"
    assert set(ohlcv.VALID_INTERVALS) == {"1m", "5m", "15m", "30m", "1H", "1D", "1W", "1M"}
    assert ohlcv.is_intraday("5m") is True
    assert ohlcv.is_intraday("1D") is False
    assert ohlcv.is_intraday("1W") is False
    assert ohlcv.is_intraday("bogus") is False


def test_time_str_daily_is_a_plain_date():
    assert ohlcv.time_str(pd.Timestamp("2026-07-17"), intraday=False) == "2026-07-17"


def test_time_str_intraday_is_naive_wall_clock():
    # tz-aware (IST) → naive wall-clock ISO datetime (so the chart shows 09:15).
    ts = pd.Timestamp("2026-07-20 09:15:00", tz="Asia/Kolkata")
    assert ohlcv.time_str(ts, intraday=True) == "2026-07-20T09:15:00"
    # already naive → unchanged
    naive = pd.Timestamp("2026-07-20 09:15:00")
    assert ohlcv.time_str(naive, intraday=True) == "2026-07-20T09:15:00"


def _daily(dates, closes):
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d in dates], name="date")
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c + 1 for c in closes],
            "low": [c - 1 for c in closes],
            "close": closes,
            "adj_close": closes,
            "volume": [100] * len(closes),
        },
        index=idx,
    )


def test_resample_weekly_aggregates_ohlcv():
    # Mon–Wed of one trading week.
    df = _daily(["2026-07-13", "2026-07-14", "2026-07-15"], [100.0, 110.0, 105.0])
    wk = ohlcv._resample(df, "W-FRI")
    assert len(wk) == 1
    row = wk.iloc[0]
    assert row["open"] == 100.0  # first
    assert row["high"] == 111.0  # max of highs (110+1)
    assert row["low"] == 99.0  # min of lows (100-1)
    assert row["close"] == 105.0  # last
    assert row["volume"] == 300  # sum


def test_resample_monthly_spans_month_boundary():
    df = _daily(["2026-06-30", "2026-07-01", "2026-07-31"], [50.0, 60.0, 70.0])
    mo = ohlcv._resample(df, "ME")
    # two month buckets: June (1 bar) and July (2 bars)
    assert len(mo) == 2
    assert mo.iloc[0]["close"] == 50.0
    assert mo.iloc[1]["open"] == 60.0
    assert mo.iloc[1]["close"] == 70.0
    assert mo.iloc[1]["volume"] == 200


def test_resample_empty_is_empty():
    assert ohlcv._resample(pd.DataFrame(), "W-FRI").empty
