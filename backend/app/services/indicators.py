"""Technical indicator computations (pure, vectorized, dependency-light).

All functions take/return pandas Series/DataFrame aligned to the price index.
``rsi``/``atr``/``adx`` use Wilder's smoothing (the conventional definition).
``compute_indicators`` is the dispatcher used by the API and forecasting prep;
it passes whatever OHLCV columns each indicator needs.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Indicator name -> the output column(s) it produces (with default params).
SUPPORTED_INDICATORS = (
    "sma",
    "ema",
    "rsi",
    "macd",
    "bollinger",
    "vwap",
    "atr",
    "supertrend",
    "adx",
    "stochrsi",
    "cci",
    "obv",
    "psar",
    "donchian",
    "ichimoku",
)


# --- price-only ------------------------------------------------------------
def sma(close: pd.Series, window: int = 20) -> pd.Series:
    return close.rolling(window=window, min_periods=window).mean()


def ema(close: pd.Series, span: int = 20) -> pd.Series:
    return close.ewm(span=span, adjust=False, min_periods=span).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss
    result = 100.0 - (100.0 / (1.0 + rs))
    result = result.where(avg_loss != 0, 100.0)
    return result


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    macd_line = (
        close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    )
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return pd.DataFrame({"macd": macd_line, "macd_signal": signal_line, "macd_hist": hist})


def bollinger(close: pd.Series, window: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    mid = close.rolling(window=window, min_periods=window).mean()
    std = close.rolling(window=window, min_periods=window).std(ddof=0)
    return pd.DataFrame(
        {"bb_upper": mid + num_std * std, "bb_mid": mid, "bb_lower": mid - num_std * std}
    )


def stoch_rsi(
    close: pd.Series, period: int = 14, smooth_k: int = 3, smooth_d: int = 3
) -> pd.DataFrame:
    r = rsi(close, period)
    lo = r.rolling(period, min_periods=period).min()
    hi = r.rolling(period, min_periods=period).max()
    k_raw = 100.0 * (r - lo) / (hi - lo)
    k = k_raw.rolling(smooth_k, min_periods=smooth_k).mean()
    d = k.rolling(smooth_d, min_periods=smooth_d).mean()
    return pd.DataFrame({"stochrsi_k": k, "stochrsi_d": d})


# --- range-based (need high/low[/close]) -----------------------------------
def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    return pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr = _true_range(high, low, close)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.DataFrame:
    up = high.diff()
    down = -low.diff()
    plus_dm = up.where((up > down) & (up > 0), 0.0)
    minus_dm = down.where((down > up) & (down > 0), 0.0)
    atr_ = _true_range(high, low, close).ewm(alpha=1.0 / period, adjust=False).mean()
    plus_di = 100.0 * plus_dm.ewm(alpha=1.0 / period, adjust=False).mean() / atr_
    minus_di = 100.0 * minus_dm.ewm(alpha=1.0 / period, adjust=False).mean() / atr_
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    adx_ = dx.ewm(alpha=1.0 / period, adjust=False).mean()
    return pd.DataFrame({"adx_14": adx_, "plus_di_14": plus_di, "minus_di_14": minus_di})


def cci(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 20) -> pd.Series:
    tp = (high + low + close) / 3.0
    sma_tp = tp.rolling(period, min_periods=period).mean()
    mad = tp.rolling(period, min_periods=period).apply(
        lambda x: np.abs(x - x.mean()).mean(), raw=True
    )
    return (tp - sma_tp) / (0.015 * mad)


def donchian(high: pd.Series, low: pd.Series, period: int = 20) -> pd.DataFrame:
    upper = high.rolling(period, min_periods=period).max()
    lower = low.rolling(period, min_periods=period).min()
    return pd.DataFrame(
        {"donchian_upper": upper, "donchian_mid": (upper + lower) / 2.0, "donchian_lower": lower}
    )


def ichimoku(high: pd.Series, low: pd.Series) -> pd.DataFrame:
    def mid(n: int) -> pd.Series:
        return (high.rolling(n, min_periods=n).max() + low.rolling(n, min_periods=n).min()) / 2.0

    tenkan = mid(9)
    kijun = mid(26)
    return pd.DataFrame(
        {
            "ichimoku_tenkan": tenkan,
            "ichimoku_kijun": kijun,
            "ichimoku_senkou_a": ((tenkan + kijun) / 2.0).shift(26),
            "ichimoku_senkou_b": mid(52).shift(26),
        }
    )


# --- volume ----------------------------------------------------------------
def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff().fillna(0.0))
    return (direction * volume).cumsum()


def vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    """Session-cumulative VWAP, reset per calendar day. Meaningful intraday;
    degenerate (≈ typical price) on daily bars where each day has one bar."""
    tp = (high + low + close) / 3.0
    pv = tp * volume
    if isinstance(close.index, pd.DatetimeIndex):
        day = close.index.normalize()
    else:
        day = pd.Index([0] * len(close))
    grouper = pd.Series(day, index=close.index)
    cum_pv = pv.groupby(grouper).cumsum()
    cum_v = volume.groupby(grouper).cumsum().replace(0.0, np.nan)
    return cum_pv / cum_v


# --- iterative (stateful) --------------------------------------------------
def supertrend(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 10, multiplier: float = 3.0
) -> pd.Series:
    atr_ = atr(high, low, close, period).to_numpy()
    hl2 = ((high + low) / 2.0).to_numpy()
    c = close.to_numpy()
    n = len(c)
    basic_upper = hl2 + multiplier * atr_
    basic_lower = hl2 - multiplier * atr_
    final_upper = np.full(n, np.nan)
    final_lower = np.full(n, np.nan)
    st = np.full(n, np.nan)
    for i in range(n):
        if np.isnan(atr_[i]):
            continue
        # Seed the first valid bar (or after any NaN gap) directly from the
        # basic bands so a NaN previous band never propagates forward.
        if i == 0 or np.isnan(final_upper[i - 1]) or np.isnan(st[i - 1]):
            final_upper[i] = basic_upper[i]
            final_lower[i] = basic_lower[i]
            st[i] = final_lower[i] if c[i] >= final_lower[i] else final_upper[i]
            continue
        final_upper[i] = (
            basic_upper[i]
            if (basic_upper[i] < final_upper[i - 1] or c[i - 1] > final_upper[i - 1])
            else final_upper[i - 1]
        )
        final_lower[i] = (
            basic_lower[i]
            if (basic_lower[i] > final_lower[i - 1] or c[i - 1] < final_lower[i - 1])
            else final_lower[i - 1]
        )
        if st[i - 1] == final_upper[i - 1]:
            st[i] = final_upper[i] if c[i] <= final_upper[i] else final_lower[i]
        else:
            st[i] = final_lower[i] if c[i] >= final_lower[i] else final_upper[i]
    return pd.Series(st, index=close.index)


def psar(
    high: pd.Series, low: pd.Series, af_step: float = 0.02, af_max: float = 0.2
) -> pd.Series:
    h = high.to_numpy()
    low_ = low.to_numpy()
    n = len(h)
    out = np.full(n, np.nan)
    if n < 2:
        return pd.Series(out, index=high.index)
    up = True
    af = af_step
    ep = h[0]
    sar = low_[0]
    out[0] = sar
    for i in range(1, n):
        sar = sar + af * (ep - sar)
        if up:
            sar = min(sar, low_[i - 1], low_[i - 2] if i >= 2 else low_[i - 1])
            if h[i] > ep:
                ep = h[i]
                af = min(af + af_step, af_max)
            if low_[i] < sar:  # flip
                up = False
                sar = ep
                ep = low_[i]
                af = af_step
        else:
            sar = max(sar, h[i - 1], h[i - 2] if i >= 2 else h[i - 1])
            if low_[i] < ep:
                ep = low_[i]
                af = min(af + af_step, af_max)
            if h[i] > sar:  # flip
                up = True
                sar = ep
                ep = h[i]
                af = af_step
        out[i] = sar
    return pd.Series(out, index=high.index)


# --- dispatcher ------------------------------------------------------------
def compute_indicators(df: pd.DataFrame, names: list[str]) -> pd.DataFrame:
    """Compute the requested indicators from an OHLCV price frame.

    Requires a ``close`` column; range/volume indicators need ``high``/``low``/
    ``volume`` (they degrade to NaN if those are absent). Returns a DataFrame
    indexed like ``df`` with one column per indicator output. Unknown names are
    silently ignored.
    """
    if "close" not in df.columns:
        raise ValueError("price frame must contain a 'close' column")
    close = df["close"].astype(float)
    high = df["high"].astype(float) if "high" in df.columns else close
    low = df["low"].astype(float) if "low" in df.columns else close
    volume = (
        df["volume"].astype(float)
        if "volume" in df.columns
        else pd.Series(0.0, index=df.index)
    )
    out = pd.DataFrame(index=df.index)
    for name in names:
        key = name.strip().lower()
        if key == "sma":
            out["sma_20"] = sma(close, 20)
        elif key == "ema":
            out["ema_20"] = ema(close, 20)
        elif key == "rsi":
            out["rsi_14"] = rsi(close, 14)
        elif key == "macd":
            out = out.join(macd(close))
        elif key == "bollinger":
            out = out.join(bollinger(close))
        elif key == "stochrsi":
            out = out.join(stoch_rsi(close))
        elif key == "vwap":
            out["vwap"] = vwap(high, low, close, volume)
        elif key == "atr":
            out["atr_14"] = atr(high, low, close, 14)
        elif key == "adx":
            out = out.join(adx(high, low, close, 14))
        elif key == "cci":
            out["cci_20"] = cci(high, low, close, 20)
        elif key == "obv":
            out["obv"] = obv(close, volume)
        elif key == "donchian":
            out = out.join(donchian(high, low, 20))
        elif key == "ichimoku":
            out = out.join(ichimoku(high, low))
        elif key == "supertrend":
            out["supertrend"] = supertrend(high, low, close, 10, 3.0)
        elif key == "psar":
            out["psar"] = psar(high, low)
        # unknown names silently ignored
    return out
