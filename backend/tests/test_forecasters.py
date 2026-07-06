"""Unit tests for the forecasting subsystem (baseline + registry + Kronos gating)."""

from __future__ import annotations

import pandas as pd
import pytest
from app.ml.base import ForecasterError
from app.ml.baseline_forecaster import BaselineForecaster
from app.ml.registry import AVAILABLE_FORECASTERS, get_forecaster


def test_baseline_forecast_shape(price_df):
    result = BaselineForecaster().forecast(price_df, horizon=5)
    assert result.model_name == "baseline"
    assert result.horizon == 5
    assert len(result.predictions) == 5
    assert all(isinstance(p, float) for p in result.predictions)


def test_baseline_drift_direction_up():
    df = pd.DataFrame({"close": [100.0 + i for i in range(60)]})
    result = BaselineForecaster().forecast(df, horizon=3)
    # Uptrend -> predictions above last close and increasing.
    assert result.predictions[0] > 100.0 + 59
    assert result.predictions[2] > result.predictions[0]


def test_baseline_flat_series_predicts_last_close():
    df = pd.DataFrame({"close": [50.0] * 40})
    result = BaselineForecaster().forecast(df, horizon=4)
    assert all(p == pytest.approx(50.0) for p in result.predictions)


def test_baseline_rejects_empty():
    with pytest.raises(ForecasterError):
        BaselineForecaster().forecast(pd.DataFrame({"close": []}), horizon=3)


def test_baseline_rejects_bad_horizon(price_df):
    with pytest.raises(ValueError):
        BaselineForecaster().forecast(price_df, horizon=0)


def test_registry_names():
    assert set(AVAILABLE_FORECASTERS) == {"kronos", "baseline"}
    assert get_forecaster("baseline").name == "baseline"
    assert get_forecaster("kronos").name == "kronos"


def test_registry_unknown_name():
    with pytest.raises(ValueError, match="unknown forecaster"):
        get_forecaster("prophet")


def test_kronos_without_vendored_source_raises_cleanly(price_df):
    """Until app/ml/kronos_src is vendored, kronos must fail with a clear error."""
    try:
        import app.ml.kronos_src  # noqa: F401

        pytest.skip("kronos source is vendored; this test covers the un-vendored state")
    except ImportError:
        pass
    forecaster = get_forecaster("kronos")
    with pytest.raises(ForecasterError, match="kronos_src"):
        forecaster.forecast(price_df, horizon=2)
