"""Shared test fixtures."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def price_df() -> pd.DataFrame:
    """Deterministic 200-bar daily OHLCV frame with a trend + oscillation."""
    n = 200
    idx = pd.bdate_range("2023-01-02", periods=n)
    rng = np.random.default_rng(42)
    trend = np.linspace(100.0, 140.0, n)
    wave = 6.0 * np.sin(np.linspace(0, 14, n))
    noise = rng.normal(0, 0.5, n)
    close = trend + wave + noise
    return pd.DataFrame(
        {
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "adj_close": close,
            "volume": rng.integers(10_000, 100_000, n),
        },
        index=idx,
    )
