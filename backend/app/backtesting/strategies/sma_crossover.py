"""SMA crossover strategy - shared signal logic.

Long when the fast SMA is above the slow SMA, flat otherwise. The pure signal
function here is used by the vectorized simple engine; the NautilusTrader engine
implements the equivalent logic as a live Strategy over bars.
"""

from __future__ import annotations

import pandas as pd

DEFAULT_FAST = 10
DEFAULT_SLOW = 30


def sma_crossover_position(close: pd.Series, fast: int, slow: int) -> pd.Series:
    """Return a target position series (1.0 = long, 0.0 = flat) per bar.

    The signal is computed on the bar's close; callers should lag it by one bar
    to avoid look-ahead when converting to realised returns.
    """
    if fast >= slow:
        raise ValueError("fast window must be smaller than slow window")
    fast_ma = close.rolling(window=fast, min_periods=fast).mean()
    slow_ma = close.rolling(window=slow, min_periods=slow).mean()
    position = (fast_ma > slow_ma).astype(float)
    # Undefined until both MAs exist.
    position[slow_ma.isna()] = 0.0
    return position
