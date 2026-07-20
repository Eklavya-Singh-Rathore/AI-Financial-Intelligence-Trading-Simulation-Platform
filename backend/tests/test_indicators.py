"""Unit tests for the technical indicator engine."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from app.services.indicators import (
    adx,
    atr,
    bollinger,
    cci,
    compute_indicators,
    donchian,
    ema,
    ichimoku,
    macd,
    obv,
    psar,
    rsi,
    sma,
    stoch_rsi,
    supertrend,
    vwap,
)


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


# --- Phase 6.5 indicators --------------------------------------------------
def test_atr_positive(price_df):
    out = atr(price_df["high"], price_df["low"], price_df["close"]).dropna()
    assert len(out) > 0
    assert (out > 0).all()


def test_adx_bounded_and_columns(price_df):
    out = adx(price_df["high"], price_df["low"], price_df["close"])
    assert list(out.columns) == ["adx_14", "plus_di_14", "minus_di_14"]
    a = out["adx_14"].dropna()
    assert ((a >= 0) & (a <= 100)).all()


def test_stoch_rsi_bounded(price_df):
    out = stoch_rsi(price_df["close"]).dropna()
    assert ((out["stochrsi_k"] >= -1e-6) & (out["stochrsi_k"] <= 100 + 1e-6)).all()


def test_cci_finite(price_df):
    out = cci(price_df["high"], price_df["low"], price_df["close"]).dropna()
    assert len(out) > 0
    assert np.isfinite(out).all()


def test_obv_is_running_signed_volume():
    close = pd.Series([10.0, 11.0, 10.5, 12.0])
    volume = pd.Series([100.0, 200.0, 300.0, 400.0])
    out = obv(close, volume)
    # diffs: nan->0, +1, -1, +1 → 0, +200, -300, +400 cumsum
    assert out.tolist() == [0.0, 200.0, -100.0, 300.0]


def test_donchian_ordering(price_df):
    out = donchian(price_df["high"], price_df["low"]).dropna()
    assert (out["donchian_upper"] >= out["donchian_mid"]).all()
    assert (out["donchian_mid"] >= out["donchian_lower"]).all()


def test_ichimoku_columns(price_df):
    out = ichimoku(price_df["high"], price_df["low"])
    assert set(out.columns) == {
        "ichimoku_tenkan",
        "ichimoku_kijun",
        "ichimoku_senkou_a",
        "ichimoku_senkou_b",
    }


def test_vwap_equals_typical_price_on_daily(price_df):
    # Daily bars: one bar per day, so session-cumulative VWAP == typical price.
    out = vwap(price_df["high"], price_df["low"], price_df["close"], price_df["volume"])
    tp = (price_df["high"] + price_df["low"] + price_df["close"]) / 3.0
    assert (out - tp).abs().max() < 1e-6


def test_supertrend_and_psar_produce_finite_values_in_range(price_df):
    st = supertrend(price_df["high"], price_df["low"], price_df["close"]).dropna()
    sar = psar(price_df["high"], price_df["low"]).dropna()
    assert len(st) > 0 and len(sar) > 0
    lo, hi = price_df["low"].min() - 5, price_df["high"].max() + 5
    assert ((st >= lo) & (st <= hi)).all()
    assert ((sar >= lo) & (sar <= hi)).all()


def test_compute_indicators_new_dispatch(price_df):
    names = ["vwap", "atr", "supertrend", "adx", "stochrsi", "cci"]
    names += ["obv", "psar", "donchian", "ichimoku"]
    out = compute_indicators(price_df, names)
    expected = {
        "vwap",
        "atr_14",
        "supertrend",
        "adx_14",
        "plus_di_14",
        "minus_di_14",
        "stochrsi_k",
        "stochrsi_d",
        "cci_20",
        "obv",
        "psar",
        "donchian_upper",
        "donchian_mid",
        "donchian_lower",
        "ichimoku_tenkan",
        "ichimoku_kijun",
        "ichimoku_senkou_a",
        "ichimoku_senkou_b",
    }
    assert expected == set(out.columns)
    assert len(out) == len(price_df)
