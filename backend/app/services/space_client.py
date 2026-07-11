"""HTTP client for the remote inference Space (Kronos forecasts + MiniLM embeddings).

Phase 4.5: production runs Kronos and the embedding model on a Hugging Face
Docker Space instead of in-process (Render's 512 MB free tier cannot hold
torch). This module is the single reusable client shared by
``RemoteKronosForecaster`` and ``app.services.embeddings``.

Design mirrors the LLM failover client (``app/llm/registry.py``): synchronous
httpx (call sites already run in ``asyncio.to_thread``), bounded retries with
jittered backoff, structured errors, structlog events. A dedicated path
handles Hugging Face's 503 "Space is waking up" responses by polling until the
Space is live (free Spaces sleep after ~48h idle and take a minute+ to wake).

Error-message hygiene: ``SpaceClientError`` text can surface in public API
error details (the forecast route returns ``str(ForecasterError)`` as the 503
detail), so messages stay generic - never include URLs, headers, tokens or
response bodies.
"""

from __future__ import annotations

import random
import time
from typing import Any

import httpx
import structlog

from app.core.config import get_settings

log = structlog.get_logger(__name__)

_RETRYABLE_STATUS = (502, 504)  # transient gateway hiccups
_WAKING_STATUS = 503  # HF returns 503 while a slept Space restarts
_WAKE_POLL_SECONDS = 5.0
_JITTER_MAX_SECONDS = 0.5


class SpaceClientError(RuntimeError):
    """Structured failure talking to the inference Space.

    ``kind`` is one of: ``connect`` | ``timeout`` | ``waking`` | ``auth`` |
    ``http`` | ``bad_response``.
    """

    def __init__(self, message: str, *, kind: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.status_code = status_code


class SpaceClient:
    """Reusable client for the inference Space; thread-safe (httpx.Client is)."""

    def __init__(
        self,
        *,
        base_url: str,
        hf_token: str | None = None,
        api_key: str | None = None,
        connect_timeout: float = 10.0,
        read_timeout: float = 120.0,
        max_retries: int = 2,
        backoff_base: float = 1.5,
        wake_max_wait: float = 180.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.strip().rstrip("/")
        self.max_retries = max(0, int(max_retries))
        self.backoff_base = backoff_base
        self.wake_max_wait = wake_max_wait
        headers: dict[str, str] = {}
        if hf_token:
            headers["Authorization"] = f"Bearer {hf_token}"
        if api_key:
            headers["X-API-Key"] = api_key
        self._client = httpx.Client(
            headers=headers,
            timeout=httpx.Timeout(read_timeout, connect=connect_timeout),
            transport=transport,
        )

    # -- public API ---------------------------------------------------------

    def post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        op: str,
        retry_read_timeout: bool = False,
    ) -> dict[str, Any]:
        """POST ``payload`` to ``path`` and return the decoded JSON object."""
        return self._request(
            "POST", path, op=op, json=payload, retry_read_timeout=retry_read_timeout
        )

    def health(self) -> dict[str, Any]:
        """GET /health (also used as the keep-warm ping)."""
        return self._request("GET", "/health", op="health", retry_read_timeout=True)

    # -- internals ----------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        op: str,
        json: dict[str, Any] | None = None,
        retry_read_timeout: bool = False,
    ) -> dict[str, Any]:
        if not self.base_url:
            raise SpaceClientError(
                "inference service URL is not configured", kind="http"
            )
        url = f"{self.base_url}/{path.lstrip('/')}"
        attempt = 0
        wake_deadline: float | None = None
        started = time.perf_counter()
        while True:
            attempt += 1
            try:
                response = self._client.request(method, url, json=json)
            except httpx.ConnectError as exc:
                if attempt <= self.max_retries:
                    self._sleep_backoff(attempt, op=op, reason="connect_error")
                    continue
                raise SpaceClientError(
                    "inference service is unreachable", kind="connect"
                ) from exc
            except httpx.TimeoutException as exc:
                if retry_read_timeout and attempt <= self.max_retries:
                    self._sleep_backoff(attempt, op=op, reason="timeout")
                    continue
                raise SpaceClientError(
                    "inference service timed out", kind="timeout"
                ) from exc

            status = response.status_code
            if status == _WAKING_STATUS:
                # A slept Space answers 503 while its container restarts. Poll
                # (without consuming retry attempts) until the wake budget runs out.
                now = time.perf_counter()
                if wake_deadline is None:
                    wake_deadline = now + self.wake_max_wait
                if now + _WAKE_POLL_SECONDS > wake_deadline:
                    log.warning(
                        "space_wake_timeout", op=op, waited_s=round(now - started, 1)
                    )
                    raise SpaceClientError(
                        "inference service is unavailable "
                        f"(still starting after {int(self.wake_max_wait)}s)",
                        kind="waking",
                        status_code=status,
                    )
                log.info("space_waking", op=op, waited_s=round(now - started, 1))
                time.sleep(_WAKE_POLL_SECONDS)
                continue
            if status in _RETRYABLE_STATUS and attempt <= self.max_retries:
                self._sleep_backoff(attempt, op=op, reason=f"http_{status}")
                continue
            if status in (401, 403):
                log.warning("space_request_rejected", op=op, status=status)
                raise SpaceClientError(
                    "inference service rejected the credentials",
                    kind="auth",
                    status_code=status,
                )
            if status >= 400:
                log.warning("space_request_failed", op=op, status=status, attempt=attempt)
                raise SpaceClientError(
                    f"inference service returned HTTP {status}",
                    kind="http",
                    status_code=status,
                )

            try:
                data = response.json()
            except ValueError as exc:
                raise SpaceClientError(
                    "inference service returned a malformed response",
                    kind="bad_response",
                    status_code=status,
                ) from exc
            if not isinstance(data, dict):
                raise SpaceClientError(
                    "inference service returned an unexpected response shape",
                    kind="bad_response",
                    status_code=status,
                )
            log.info(
                "space_request_succeeded",
                op=op,
                status=status,
                attempt=attempt,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
            return data

    def _sleep_backoff(self, attempt: int, *, op: str, reason: str) -> None:
        delay = self.backoff_base * attempt + random.uniform(0, _JITTER_MAX_SECONDS)
        log.warning(
            "space_request_retry", op=op, attempt=attempt, reason=reason, delay_s=round(delay, 2)
        )
        time.sleep(delay)


_CLIENT: SpaceClient | None = None
_CLIENT_KEY: tuple | None = None


def get_space_client() -> SpaceClient:
    """Settings-backed singleton; rebuilt when the relevant settings change."""
    global _CLIENT, _CLIENT_KEY
    s = get_settings()
    key = (
        s.inference_space_url,
        s.hf_token,
        s.inference_space_api_key,
        s.inference_connect_timeout_seconds,
        s.inference_read_timeout_seconds,
        s.inference_max_retries,
        s.inference_retry_backoff_seconds,
        s.inference_wake_max_wait_seconds,
    )
    if _CLIENT is None or key != _CLIENT_KEY:
        _CLIENT = SpaceClient(
            base_url=s.inference_space_url,
            hf_token=s.hf_token,
            api_key=s.inference_space_api_key or None,
            connect_timeout=s.inference_connect_timeout_seconds,
            read_timeout=s.inference_read_timeout_seconds,
            max_retries=s.inference_max_retries,
            backoff_base=s.inference_retry_backoff_seconds,
            wake_max_wait=s.inference_wake_max_wait_seconds,
        )
        _CLIENT_KEY = key
    return _CLIENT


def reset_space_client() -> None:
    """Drop the cached client (tests / settings reloads)."""
    global _CLIENT, _CLIENT_KEY
    _CLIENT = None
    _CLIENT_KEY = None
