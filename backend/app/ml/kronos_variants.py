"""Kronos model-variant registry (Environment -> Config -> Registry -> Loader).

Maps a short variant name to its Hugging Face Hub ids + context window, so model
selection is data in one place, not hardcoded strings scattered across loaders.

Deployment intent: ``base`` for local development (a dev box has the RAM for the
larger checkpoint), ``small`` in production (the free-tier inference budget).
Selection is automatic from the runtime ``ENV`` unless overridden - see
:func:`resolve_kronos_config`.

Only the variants NeoQuasar actually publishes are listed. ``tiny`` and ``large``
belong to a *different* time-series model family and are NOT published for Kronos
(github.com/shiyu-coder/Kronos); do not invent Hub ids for them. To support a new
Kronos checkpoint, add one row here - no other code changes are needed.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KronosVariant:
    """A resolvable Kronos checkpoint: Hub model + tokenizer + context window."""

    model_id: str
    tokenizer_id: str
    max_context: int


KRONOS_VARIANTS: dict[str, KronosVariant] = {
    "mini": KronosVariant("NeoQuasar/Kronos-mini", "NeoQuasar/Kronos-Tokenizer-2k", 2048),
    "small": KronosVariant("NeoQuasar/Kronos-small", "NeoQuasar/Kronos-Tokenizer-base", 512),
    "base": KronosVariant("NeoQuasar/Kronos-base", "NeoQuasar/Kronos-Tokenizer-base", 512),
}

DEFAULT_LOCAL_VARIANT = "base"
DEFAULT_PROD_VARIANT = "small"
# Environments treated as "local development" for automatic selection.
_DEV_ENVS = frozenset({"", "development", "dev", "local", "test", "testing"})


def auto_variant(env: str) -> str:
    """Pick a variant name from the runtime environment: base for dev, small else."""
    is_dev = (env or "").strip().lower() in _DEV_ENVS
    return DEFAULT_LOCAL_VARIANT if is_dev else DEFAULT_PROD_VARIANT


def resolve_variant(name: str) -> KronosVariant:
    """Look up a variant by name (case-insensitive); raise ValueError if unknown."""
    key = (name or "").strip().lower()
    if key not in KRONOS_VARIANTS:
        raise ValueError(
            f"unknown Kronos variant '{name}'. Available: {', '.join(sorted(KRONOS_VARIANTS))}"
        )
    return KRONOS_VARIANTS[key]


def resolve_kronos_config(settings) -> KronosVariant:
    """Resolve the effective Kronos (model_id, tokenizer_id, max_context).

    Precedence, evaluated per-field so old pinned deployments keep working:

    1. explicit ``KRONOS_MODEL_ID`` / ``KRONOS_TOKENIZER_ID`` / ``KRONOS_MAX_CONTEXT``
    2. ``KRONOS_VARIANT`` (mini | small | base), if set
    3. automatic by ``ENV`` (base for local dev, small in production)
    """
    variant_name = (settings.kronos_variant or "").strip() or auto_variant(settings.env)
    variant = resolve_variant(variant_name)
    return KronosVariant(
        model_id=(settings.kronos_model_id or "").strip() or variant.model_id,
        tokenizer_id=(settings.kronos_tokenizer_id or "").strip() or variant.tokenizer_id,
        max_context=int(settings.kronos_max_context or 0) or variant.max_context,
    )
