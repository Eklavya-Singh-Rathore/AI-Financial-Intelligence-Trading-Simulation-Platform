"""Unit tests for interval-aware forecast timestamp generation (Phase 6.1)."""

from __future__ import annotations

import pandas as pd
from app.ml.base import resolve_target_timestamps
from app.services.ohlcv import future_timestamps

# 2026-07-17 is a Friday; 2026-07-20 a Monday; 2026-07-21 a Tuesday.


def test_daily_future_is_business_days_skipping_weekend():
    ts = future_timestamps(pd.Timestamp("2026-07-17"), "1D", 3)
    assert list(ts) == [
        pd.Timestamp("2026-07-20"),
        pd.Timestamp("2026-07-21"),
        pd.Timestamp("2026-07-22"),
    ]


def test_intraday_5m_steps_within_session():
    ts = future_timestamps(pd.Timestamp("2026-07-20 10:00:00"), "5m", 3)
    assert list(ts) == [
        pd.Timestamp("2026-07-20 10:05:00"),
        pd.Timestamp("2026-07-20 10:10:00"),
        pd.Timestamp("2026-07-20 10:15:00"),
    ]


def test_intraday_rolls_over_session_close_to_next_open():
    ts = future_timestamps(pd.Timestamp("2026-07-20 15:25:00"), "5m", 2)
    assert ts[0] == pd.Timestamp("2026-07-21 09:15:00")  # next session open
    assert ts[1] == pd.Timestamp("2026-07-21 09:20:00")


def test_intraday_rolls_over_weekend():
    ts = future_timestamps(pd.Timestamp("2026-07-17 15:25:00"), "5m", 1)
    assert ts[0] == pd.Timestamp("2026-07-20 09:15:00")  # Monday open, weekend skipped


def test_intraday_hourly_steps():
    ts = future_timestamps(pd.Timestamp("2026-07-20 13:15:00"), "1H", 2)
    assert ts[0] == pd.Timestamp("2026-07-20 14:15:00")
    assert ts[1] == pd.Timestamp("2026-07-20 15:15:00")


def test_intraday_drops_timezone():
    aware = pd.Timestamp("2026-07-20 10:00:00", tz="Asia/Kolkata")
    ts = future_timestamps(aware, "5m", 1)
    assert ts[0].tzinfo is None
    assert ts[0] == pd.Timestamp("2026-07-20 10:05:00")


def test_weekly_future_uses_friday_anchor():
    ts = future_timestamps(pd.Timestamp("2026-07-17"), "1W", 2)
    assert list(ts) == [pd.Timestamp("2026-07-24"), pd.Timestamp("2026-07-31")]


def test_monthly_future_uses_month_end():
    ts = future_timestamps(pd.Timestamp("2026-07-17"), "1M", 2)
    assert ts[0] == pd.Timestamp("2026-07-31")
    assert ts[1] == pd.Timestamp("2026-08-31")


def test_zero_periods_is_empty():
    assert len(future_timestamps(pd.Timestamp("2026-07-20"), "5m", 0)) == 0


def test_resolve_target_timestamps_passthrough():
    given = pd.Series(pd.to_datetime(["2026-07-20 09:20:00", "2026-07-20 09:25:00"]))
    out = resolve_target_timestamps(given, pd.DatetimeIndex(["2026-07-20 09:15:00"]), 2)
    assert list(out) == list(given)


def test_resolve_target_timestamps_defaults_to_business_days():
    out = resolve_target_timestamps(None, pd.DatetimeIndex(["2026-07-17"]), 2)
    assert list(out) == [pd.Timestamp("2026-07-20"), pd.Timestamp("2026-07-21")]
