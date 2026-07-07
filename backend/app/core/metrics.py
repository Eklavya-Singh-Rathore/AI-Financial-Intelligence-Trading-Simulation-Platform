"""Prometheus metrics: HTTP metrics via instrumentator + domain counters.

``/metrics`` is exposed by the instrumentator in ``main.py`` (behind the API
key when configured). Domain counters are incremented by the orchestrator.
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

AGENT_RUNS_TOTAL = Counter(
    "agent_runs_total",
    "Agent pipeline runs by terminal status",
    labelnames=("status",),
)

LLM_TOKENS_TOTAL = Counter(
    "llm_tokens_total",
    "LLM tokens consumed by agent runs",
    labelnames=("direction",),  # input | output
)

AGENT_RUN_DURATION_SECONDS = Histogram(
    "agent_run_duration_seconds",
    "Wall-clock duration of completed agent runs",
    buckets=(5, 15, 30, 60, 120, 300, 600),
)


def record_run_result(status: str, usage: dict | None, duration_seconds: float | None) -> None:
    """Record a finished (completed/failed) agent run."""
    AGENT_RUNS_TOTAL.labels(status=status).inc()
    if usage:
        LLM_TOKENS_TOTAL.labels(direction="input").inc(int(usage.get("input_tokens", 0)))
        LLM_TOKENS_TOTAL.labels(direction="output").inc(int(usage.get("output_tokens", 0)))
    if duration_seconds is not None and duration_seconds >= 0:
        AGENT_RUN_DURATION_SECONDS.observe(duration_seconds)
