"""Unit tests for the financial-research service (serialization + earnings math).

No network: yfinance is never touched - these cover the pure transforms.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from app.services.research import _clean_number, derive_earnings, serialize_statement


def _stmt_df() -> pd.DataFrame:
    cols = pd.to_datetime(["2026-03-31", "2025-03-31", "2024-03-31"])
    return pd.DataFrame(
        {
            cols[0]: [1000.0, 400.0, np.nan],
            cols[1]: [900.0, 350.0, 120.0],
            cols[2]: [800.0, np.inf, 100.0],
        },
        index=["Total Revenue", "Net Income", "Basic EPS"],
    )


def test_serialize_statement_shape_and_nulls():
    out = serialize_statement(_stmt_df(), ("Total Revenue", "Net Income", "Basic EPS"))
    assert out["periods"] == ["2026-03-31", "2025-03-31", "2024-03-31"]
    assert out["rows"]["Total Revenue"] == [1000, 900, 800]
    assert out["rows"]["Net Income"] == [400, 350, None]  # inf -> null
    assert out["rows"]["Basic EPS"] == [None, 120, 100]  # NaN -> null


def test_serialize_statement_filters_rows():
    out = serialize_statement(_stmt_df(), ("Total Revenue",))
    assert list(out["rows"]) == ["Total Revenue"]


def test_serialize_statement_empty_and_none():
    assert serialize_statement(None, ("X",)) == {"periods": [], "rows": {}}
    assert serialize_statement(pd.DataFrame(), ("X",)) == {"periods": [], "rows": {}}


def test_clean_number():
    assert _clean_number(float("nan")) is None
    assert _clean_number(float("inf")) is None
    assert _clean_number(None) is None
    assert _clean_number("bad") is None
    assert _clean_number(42.0) == 42
    assert _clean_number(42.5) == 42.5


def _quarterly() -> dict:
    # Newest-first, 6 quarters. Revenue grows 10/qtr; NI flat then jump.
    return {
        "periods": [
            "2026-06-30", "2026-03-31", "2025-12-31",
            "2025-09-30", "2025-06-30", "2025-03-31",
        ],
        "rows": {
            "Total Revenue": [150, 140, 130, 120, 110, 100],
            "Net Income": [30, 20, 20, 20, 20, 20],
            "Basic EPS": [3.0, 2.0, 2.0, 2.0, 2.0, 2.0],
        },
    }


def test_derive_earnings_growth_math():
    out = derive_earnings(_quarterly())
    assert len(out["quarters"]) == 6
    latest = out["latest"]
    assert latest["period"] == "2026-06-30"
    assert latest["revenue"] == 150
    # QoQ: 150/140 - 1 = 7.14%; YoY: 150/110 - 1 = 36.36%
    assert latest["revenue_qoq_pct"] == 7.14
    assert latest["revenue_yoy_pct"] == 36.36
    assert latest["net_income_qoq_pct"] == 50.0
    assert latest["net_income_yoy_pct"] == 50.0
    # Oldest quarter has nothing older to compare against.
    oldest = out["quarters"][-1]
    assert oldest["revenue_qoq_pct"] is None
    assert oldest["revenue_yoy_pct"] is None


def test_derive_earnings_handles_gaps_and_zero():
    data = {
        "periods": ["2026-06-30", "2026-03-31"],
        "rows": {"Total Revenue": [100, 0], "Net Income": [None, 10]},
    }
    out = derive_earnings(data)
    latest = out["latest"]
    assert latest["revenue_qoq_pct"] is None  # divide-by-zero guarded
    assert latest["net_income_qoq_pct"] is None  # newer is None


def test_derive_earnings_empty():
    out = derive_earnings({"periods": [], "rows": {}})
    assert out == {"quarters": [], "latest": None}
