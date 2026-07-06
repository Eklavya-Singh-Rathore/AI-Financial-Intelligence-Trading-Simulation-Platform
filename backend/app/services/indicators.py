"""Technical indicator computations (pure, vectorized, dependency-light).

All functions take/return pandas Series aligned to the price index. ``rsi`` uses
Wilder's smoothing (the conventional definition). ``compute_indicators`` is the
dispatcher used by the API and forecasting feature prep.
"""

from __future__ import annotations

import pandas as pd

# Indicator name -> the output column(s) it produces (with default params).
SUPPORTED_INDICATORS = ("sma", "ema", "rsi", "macd", "bollinger")


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
    # When there are no losses, RSI is 100 (rs -> inf gives NaN above).
    result = result.where(avg_loss != 0, 100.0)
    return result


def macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> pd.DataFrame:
    macd_line = (
        close.ewm(span=fast, adjust=False).mean()
        - close.ewm(span=slow, adjust=False).mean()
    )
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return pd.DataFrame(
        {"macd": macd_line, "macd_signal": signal_line, "macd_hist": hist}
    )


def bollinger(
    close: pd.Series, window: int = 20, num_std: float = 2.0
) -> pd.DataFrame:
    mid = close.rolling(window=window, min_periods=window).mean()
    std = close.rolling(window=window, min_periods=window).std(ddof=0)
    return pd.DataFrame(
        {
            "bb_upper": mid + num_std * std,
            "bb_mid": mid,
            "bb_lower": mid - num_std * std,
        }
    )


def compute_indicators(df: pd.DataFrame, names: list[str]) -> pd.DataFrame:
    """Compute the requested indicators from a price frame (needs a ``close``).

    Returns a DataFrame indexed like ``df`` with one column per indicator output.
    Unknown names are ignored.
    """
    if "close" not in df.columns:
        raise ValueError("price frame must contain a 'close' column")
    close = df["close"].astype(float)
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
        # unknown names silently ignored
    return out
