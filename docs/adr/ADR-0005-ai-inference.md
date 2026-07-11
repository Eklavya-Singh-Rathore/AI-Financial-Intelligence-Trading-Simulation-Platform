# ADR-0005: Remote AI inference via a Hugging Face Space

- **Status:** Accepted
- **Date:** 2026 (Phase 4.5; packaging revised Phase 4.5)

## Context

Kronos forecasting and MiniLM embeddings both pull in **torch**, which dominates
the backend's memory (~500 MB loaded) and image size (multi-GB CUDA wheel on
x86). That makes the backend impossible to host on a 512 MB free tier. The
project must keep using the **official Kronos** implementation (no substitute
model) and must not lose any functionality.

## Decision

Move Kronos and MiniLM inference to a **Hugging Face Space** exposing
`POST /forecast`, `POST /embed`, `GET /health`. The backend calls it through a
reusable client (`app/services/space_client.py`: timeouts, bounded retries,
503-wake polling, structured token-free errors, logging). Selection is a config
switch — `KRONOS_MODE` / `EMBEDDINGS_MODE` = `local` (in-process torch, dev
default) or `remote` (Space, production) — behind the existing registry, so the
public forecaster name stays `kronos` and persisted `model_name` is unchanged.
The Space loads official checkpoints from the Hub (no duplicated weights) and
runs **CPU-only** inference.

Packaging note: Hugging Face paywalled Docker/cpu-basic Spaces (July 2026), so
the Space is a **Gradio-SDK app on ZeroGPU** with the REST routes attached to
gradio's server; CPU inference consumes no GPU quota. The original Docker
packaging is preserved in git history.

## Consequences

- **+** The backend image ships without torch → fits the free tier; inference
  scales/reboots independently; local mode keeps dev and CI simple (no network).
- **+** Identical behavior contract: failures normalize to `ForecasterError`
  (→ HTTP 503 / baseline fallback) and embeddings degrade to "memory off".
- **−** A network hop + possible Space cold-start (~1–2 min) on the first
  request after idle; mitigated by keep-alive and a bounded wake-poll.
- **−** Two copies of the vendored `kronos_src/` (backend + Space) kept in sync
  by a CI drift check.
