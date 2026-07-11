"""Unit tests for the inference-Space HTTP client. No network, no sleeping."""

from __future__ import annotations

import httpx
import pytest
from app.services.space_client import SpaceClient, SpaceClientError


class FakeClock:
    """Drives space_client's time.sleep/perf_counter so wake logic is instant."""

    def __init__(self) -> None:
        self.t = 0.0

    def perf_counter(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture
def clock(monkeypatch) -> FakeClock:
    c = FakeClock()
    monkeypatch.setattr("app.services.space_client.time.sleep", c.sleep)
    monkeypatch.setattr("app.services.space_client.time.perf_counter", c.perf_counter)
    return c


def make_client(handler, **kwargs) -> SpaceClient:
    defaults: dict = {
        "base_url": "https://space.example",
        "connect_timeout": 1.0,
        "read_timeout": 1.0,
        "max_retries": 2,
        "backoff_base": 0.01,
        "wake_max_wait": 30.0,
    }
    defaults.update(kwargs)
    return SpaceClient(transport=httpx.MockTransport(handler), **defaults)


def test_post_json_happy_path_sends_both_auth_headers(clock):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        seen["key"] = request.headers.get("x-api-key")
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"ok": 1})

    client = make_client(handler, hf_token="tok123", api_key="sek456")
    data = client.post_json("/forecast", {"a": 1}, op="forecast")
    assert data == {"ok": 1}
    assert seen["auth"] == "Bearer tok123"
    assert seen["key"] == "sek456"
    assert seen["url"] == "https://space.example/forecast"


def test_missing_base_url_fails_without_request():
    client = SpaceClient(base_url="", transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    with pytest.raises(SpaceClientError) as exc_info:
        client.post_json("/embed", {}, op="embed")
    assert exc_info.value.kind == "http"


def test_wake_503_then_success(clock):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, text="waking")
        return httpx.Response(200, json={"ok": True})

    client = make_client(handler, wake_max_wait=60.0)
    assert client.post_json("/forecast", {}, op="forecast") == {"ok": True}
    assert calls["n"] == 3


def test_wake_budget_exhausted_raises_waking(clock):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="waking")

    client = make_client(handler, wake_max_wait=12.0)
    with pytest.raises(SpaceClientError) as exc_info:
        client.post_json("/forecast", {}, op="forecast")
    assert exc_info.value.kind == "waking"
    assert exc_info.value.status_code == 503


def test_connect_error_retries_then_fails(clock):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.ConnectError("boom", request=request)

    client = make_client(handler, max_retries=2)
    with pytest.raises(SpaceClientError) as exc_info:
        client.post_json("/embed", {}, op="embed")
    assert exc_info.value.kind == "connect"
    assert calls["n"] == 3  # first attempt + 2 retries


def test_connect_error_then_success(clock):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, json={"ok": 1})

    client = make_client(handler)
    assert client.post_json("/embed", {}, op="embed") == {"ok": 1}


def test_read_timeout_not_retried_by_default(clock):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.ReadTimeout("slow", request=request)

    client = make_client(handler)
    with pytest.raises(SpaceClientError) as exc_info:
        client.post_json("/forecast", {}, op="forecast")
    assert exc_info.value.kind == "timeout"
    assert calls["n"] == 1  # forecast attempts are expensive; no auto-retry


def test_read_timeout_retried_when_opted_in(clock):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(200, json={"ok": 1})

    client = make_client(handler)
    assert client.post_json("/embed", {}, op="embed", retry_read_timeout=True) == {"ok": 1}
    assert calls["n"] == 2


def test_502_retried_then_success(clock):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(502)
        return httpx.Response(200, json={"ok": 1})

    client = make_client(handler)
    assert client.post_json("/embed", {}, op="embed") == {"ok": 1}


def test_401_is_auth_error_no_retry(clock):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, json={"detail": "nope"})

    client = make_client(handler)
    with pytest.raises(SpaceClientError) as exc_info:
        client.post_json("/forecast", {}, op="forecast")
    assert exc_info.value.kind == "auth"
    assert calls["n"] == 1


def test_422_is_http_error(clock):
    client = make_client(lambda r: httpx.Response(422, json={"detail": "bad"}))
    with pytest.raises(SpaceClientError) as exc_info:
        client.post_json("/forecast", {}, op="forecast")
    assert exc_info.value.kind == "http"
    assert exc_info.value.status_code == 422


def test_non_json_body_is_bad_response(clock):
    client = make_client(lambda r: httpx.Response(200, text="<html>hi</html>"))
    with pytest.raises(SpaceClientError) as exc_info:
        client.post_json("/forecast", {}, op="forecast")
    assert exc_info.value.kind == "bad_response"


def test_json_array_body_is_bad_response(clock):
    client = make_client(lambda r: httpx.Response(200, json=[1, 2]))
    with pytest.raises(SpaceClientError) as exc_info:
        client.post_json("/forecast", {}, op="forecast")
    assert exc_info.value.kind == "bad_response"


def test_error_messages_never_leak_credentials(clock):
    """SpaceClientError text can surface in public 503 details - keep it clean."""
    secret_token = "hf_SUPERSECRET"  # noqa: S105 - test value
    secret_key = "sk_ALSOSECRET"

    for handler in (
        lambda r: httpx.Response(401),
        lambda r: httpx.Response(503),
        lambda r: httpx.Response(500),
        lambda r: httpx.Response(200, text="not json"),
    ):
        client = make_client(
            handler, hf_token=secret_token, api_key=secret_key, wake_max_wait=0.0
        )
        with pytest.raises(SpaceClientError) as exc_info:
            client.post_json("/forecast", {}, op="forecast")
        message = str(exc_info.value)
        assert secret_token not in message
        assert secret_key not in message
        assert "space.example" not in message  # no URLs either


def test_health_calls_get(clock):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        return httpx.Response(200, json={"status": "ok"})

    client = make_client(handler)
    assert client.health() == {"status": "ok"}
    assert seen == {"method": "GET", "path": "/health"}
