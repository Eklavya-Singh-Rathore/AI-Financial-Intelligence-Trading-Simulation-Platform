"""Unit tests for ingestion normalization (pure function - no network/DB)."""

from __future__ import annotations

import uuid

import numpy as np
import pandas as pd
from app.services.data_ingest import normalize_bars

INSTRUMENT_ID = uuid.uuid4()
PROVIDER_ID = uuid.uuid4()


def _yf_frame() -> pd.DataFrame:
    idx = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"])
    return pd.DataFrame(
        {
            "Open": [100.0, 101.0, 102.0],
            "High": [101.0, 102.5, 103.0],
            "Low": [99.0, 100.5, 101.0],
            "Close": [100.5, 102.0, 102.5],
            "Adj Close": [100.4, 101.9, 102.4],
            "Volume": [1000, 2000, 1500],
        },
        index=idx,
    )


def test_normalize_bars_basic():
    rows = normalize_bars(_yf_frame(), INSTRUMENT_ID, PROVIDER_ID)
    assert len(rows) == 3
    first = rows[0]
    assert first["instrument_id"] == INSTRUMENT_ID
    assert first["provider_id"] == PROVIDER_ID
    assert first["date"].isoformat() == "2024-01-01"
    assert first["open"] == 100.0
    assert first["adj_close"] == 100.4
    assert first["volume"] == 1000
    assert first["timeframe"] == "daily"
    assert first["currency"] == "INR"
    assert first["is_adjusted"] is False
    assert isinstance(first["id"], uuid.UUID)


def test_normalize_bars_unique_ids():
    rows = normalize_bars(_yf_frame(), INSTRUMENT_ID, PROVIDER_ID)
    ids = {r["id"] for r in rows}
    assert len(ids) == 3


def test_normalize_bars_drops_nan_ohlc():
    df = _yf_frame()
    df.loc[df.index[1], "Close"] = np.nan
    rows = normalize_bars(df, INSTRUMENT_ID, PROVIDER_ID)
    assert len(rows) == 2
    assert [r["date"].isoformat() for r in rows] == ["2024-01-01", "2024-01-03"]


def test_normalize_bars_handles_missing_volume_and_adj():
    df = _yf_frame().drop(columns=["Adj Close", "Volume"])
    rows = normalize_bars(df, INSTRUMENT_ID, PROVIDER_ID)
    assert len(rows) == 3
    assert rows[0]["adj_close"] is None
    assert rows[0]["volume"] == 0


def test_normalize_bars_empty_frame():
    assert normalize_bars(pd.DataFrame(), INSTRUMENT_ID, PROVIDER_ID) == []
