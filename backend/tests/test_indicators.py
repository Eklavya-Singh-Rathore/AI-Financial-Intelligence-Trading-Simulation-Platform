"""Unit tests for the technical indicator engine."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from app.services.indicators import bollinger, compute_indicators, ema, macd, rsi, sma


def test_sma_known_values():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    out = sma(s, window=3)
    assert np.isnan(out.iloc[0]) and np.isnan(out.iloc[1])
    assert out.iloc[2] == pytest.approx(2.0)
    assert out.iloc[4] == pytest.approx(4.0)


def test_ema_converges_to_constant():
    s = pd.Series([10.0] * 50)
    out = ema(s, span=10)
    assert out.iloc[-1] == pytest.approx(10.0)


def test_rsi_all_gains_is_100():
    s = pd.Series(np.arange(1.0, 40.0))
    out = rsi(s, period=14)
    assert out.iloc[-1] == pytest.approx(100.0)


def test_rsi_all_losses_near_zero():
    s = pd.Series(np.arange(40.0, 1.0, -1.0))
    out = rsi(s, period=14)
    assert out.iloc[-1] == pytest.approx(0.0, abs=1e-9)


def test_rsi_bounded(price_df):
    out = rsi(price_df["close"]).dropna()
    assert ((out >= 0) & (out <= 100)).all()


def test_macd_columns_and_hist_identity(price_df):
    out = macd(price_df["close"])
    assert list(out.columns) == ["macd", "macd_signal", "macd_hist"]
    diff = (out["macd"] - out["macd_signal"] - out["macd_hist"]).abs().max()
    assert diff < 1e-9


def test_bollinger_band_ordering(price_df):
    out = bollinger(price_df["close"]).dropna()
    assert (out["bb_upper"] >= out["bb_mid"]).all()
    assert (out["bb_mid"] >= out["bb_lower"]).all()


def test_compute_indicators_dispatch(price_df):
    out = compute_indicators(price_df, ["sma", "ema", "rsi", "macd", "bollinger"])
    expected = {
        "sma_20",
        "ema_20",
        "rsi_14",
        "macd",
        "macd_signal",
        "macd_hist",
        "bb_upper",
        "bb_mid",
        "bb_lower",
    }
    assert expected == set(out.columns)
    assert len(out) == len(price_df)


def test_compute_indicators_requires_close():
    with pytest.raises(ValueError, match="close"):
        compute_indicators(pd.DataFrame({"open": [1.0]}), ["sma"])
