"""Unit tests for RemoteKronosForecaster (payload/response contract). No network."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from app.ml.base import ForecasterError
from app.ml.remote_kronos_forecaster import RemoteKronosForecaster
from app.services.space_client import SpaceClientError


class StubSpaceClient:
    def __init__(self, response: dict | None = None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.calls: list[tuple[str, dict, str]] = []

    def post_json(self, path: str, payload: dict, *, op: str, retry_read_timeout: bool = False):
        self.calls.append((path, payload, op))
        if self.error is not None:
            raise self.error
        return self.response


@pytest.fixture
def stub(monkeypatch) -> StubSpaceClient:
    client = StubSpaceClient(
        response={
            "predictions": [101.0, 102.0, 103.0, 104.0, 105.0],
            "model_id": "NeoQuasar/Kronos-small",
            "tokenizer_id": "NeoQuasar/Kronos-Tokenizer-base",
            "context_len": 200,
            "elapsed_ms": 123,
        }
    )
    monkeypatch.setattr("app.services.space_client.get_space_client", lambda: client)
    return client


def test_payload_and_result_contract(price_df, stub):
    result = RemoteKronosForecaster().forecast(price_df, horizon=5)

    # -- request payload mirrors the local KronosForecaster exactly
    path, payload, op = stub.calls[0]
    assert (path, op) == ("/forecast", "forecast")
    ctx = payload["context"]
    assert set(ctx) == {"open", "high", "low", "close", "volume"}
    assert all(len(ctx[k]) == len(price_df) for k in ctx)  # 200 < max_context
    assert all(isinstance(v, float) for v in ctx["close"])
    assert len(payload["x_timestamps"]) == len(price_df)
    assert payload["x_timestamps"][0] == pd.to_datetime(price_df.index[0]).isoformat()
    assert payload["horizon"] == 5
    assert (payload["temperature"], payload["top_p"], payload["sample_count"]) == (1.0, 0.9, 1)

    # y_timestamps = business days strictly after the last context date
    expected_y = pd.bdate_range(
        start=pd.to_datetime(price_df.index[-1]) + pd.offsets.BDay(1), periods=5
    )
    assert payload["y_timestamps"] == [t.isoformat() for t in expected_y]

    # -- result parity with the local forecaster's contract
    assert result.model_name == "kronos"
    assert result.horizon == 5
    assert result.predictions == [101.0, 102.0, 103.0, 104.0, 105.0]
    assert result.meta["mode"] == "remote"
    assert result.meta["space_latency_ms"] == 123
    assert result.meta["model_id"] == "NeoQuasar/Kronos-small"
    assert result.meta["context_len"] == len(price_df)
    assert result.meta["target_dates"] == [d.date().isoformat() for d in expected_y]


def test_context_capped_at_max_context(stub):
    n = 600
    idx = pd.bdate_range("2022-01-03", periods=n)
    close = np.linspace(100, 160, n)
    df = pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close}, index=idx
    )
    RemoteKronosForecaster().forecast(df, horizon=5)
    _, payload, _ = stub.calls[0]
    max_context = RemoteKronosForecaster().max_context
    assert len(payload["context"]["close"]) == max_context
    assert len(payload["x_timestamps"]) == max_context
    # volume column missing -> zeros of the same (capped) length
    assert payload["context"]["volume"] == [0.0] * max_context


def test_wrong_prediction_count_raises(price_df, stub):
    stub.response = {"predictions": [1.0, 2.0], "elapsed_ms": 5}
    with pytest.raises(ForecasterError, match="unexpected prediction count"):
        RemoteKronosForecaster().forecast(price_df, horizon=5)


def test_null_prediction_raises(price_df, stub):
    stub.response = {"predictions": [1.0, None, 3.0, 4.0, 5.0]}
    with pytest.raises(ForecasterError, match="non-numeric"):
        RemoteKronosForecaster().forecast(price_df, horizon=5)


def test_nan_prediction_raises(price_df, stub):
    stub.response = {"predictions": [1.0, float("nan"), 3.0, 4.0, 5.0]}
    with pytest.raises(ForecasterError, match="non-finite"):
        RemoteKronosForecaster().forecast(price_df, horizon=5)


def test_space_error_becomes_forecaster_error(price_df, stub):
    stub.error = SpaceClientError(
        "inference service is unavailable (still starting after 180s)",
        kind="waking",
        status_code=503,
    )
    with pytest.raises(ForecasterError, match="Kronos remote inference failed"):
        RemoteKronosForecaster().forecast(price_df, horizon=5)


def test_validation_still_rejects_bad_inputs(stub):
    with pytest.raises(ForecasterError):
        RemoteKronosForecaster().forecast(pd.DataFrame({"close": []}), horizon=3)
    with pytest.raises(ValueError):
        RemoteKronosForecaster().forecast(pd.DataFrame({"close": [1.0]}), horizon=0)
    assert stub.calls == []  # never reached the network layer


def test_missing_elapsed_ms_is_filled_locally(price_df, stub):
    stub.response = {"predictions": [1.0, 2.0, 3.0, 4.0, 5.0]}
    result = RemoteKronosForecaster().forecast(price_df, horizon=5)
    assert isinstance(result.meta["space_latency_ms"], int)
    # falls back to the resolved local config when the Space omits ids; the test
    # env is "development" so the variant registry resolves base (Phase 6.1).
    assert result.meta["model_id"] == "NeoQuasar/Kronos-base"
