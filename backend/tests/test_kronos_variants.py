"""Unit tests for the Kronos variant registry (Phase 6.1)."""

from __future__ import annotations

import pytest
from app.core.config import Settings
from app.ml.kronos_variants import (
    KRONOS_VARIANTS,
    auto_variant,
    resolve_kronos_config,
    resolve_variant,
)


def _s(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


def test_registry_lists_only_published_variants():
    assert set(KRONOS_VARIANTS) == {"mini", "small", "base"}
    assert KRONOS_VARIANTS["small"].tokenizer_id == "NeoQuasar/Kronos-Tokenizer-base"
    assert KRONOS_VARIANTS["base"].tokenizer_id == "NeoQuasar/Kronos-Tokenizer-base"
    assert KRONOS_VARIANTS["mini"].tokenizer_id == "NeoQuasar/Kronos-Tokenizer-2k"
    assert KRONOS_VARIANTS["mini"].max_context == 2048
    assert KRONOS_VARIANTS["base"].max_context == 512


@pytest.mark.parametrize(
    "env,expected",
    [
        ("", "base"),
        ("development", "base"),
        ("dev", "base"),
        ("local", "base"),
        ("DEVELOPMENT", "base"),
        ("production", "small"),
        ("prod", "small"),
        ("staging", "small"),
    ],
)
def test_auto_variant_by_env(env, expected):
    assert auto_variant(env) == expected


def test_resolve_variant_rejects_unpublished_names():
    # 'tiny'/'large' belong to a different model family, not Kronos.
    for bad in ("tiny", "large", "nope"):
        with pytest.raises(ValueError):
            resolve_variant(bad)


def test_dev_defaults_to_base():
    cfg = resolve_kronos_config(_s(env="development"))
    assert cfg.model_id == "NeoQuasar/Kronos-base"
    assert cfg.tokenizer_id == "NeoQuasar/Kronos-Tokenizer-base"
    assert cfg.max_context == 512


def test_prod_defaults_to_small():
    cfg = resolve_kronos_config(_s(env="production"))
    assert cfg.model_id == "NeoQuasar/Kronos-small"
    assert cfg.max_context == 512


def test_explicit_variant_overrides_env_auto():
    cfg = resolve_kronos_config(_s(env="development", kronos_variant="small"))
    assert cfg.model_id == "NeoQuasar/Kronos-small"

    mini = resolve_kronos_config(_s(env="production", kronos_variant="mini"))
    assert mini.model_id == "NeoQuasar/Kronos-mini"
    assert mini.tokenizer_id == "NeoQuasar/Kronos-Tokenizer-2k"
    assert mini.max_context == 2048


def test_explicit_low_level_ids_win_for_backcompat():
    cfg = resolve_kronos_config(
        _s(
            env="development",
            kronos_variant="small",
            kronos_model_id="acme/custom-kronos",
            kronos_max_context=256,
        )
    )
    assert cfg.model_id == "acme/custom-kronos"  # explicit id beats the variant
    assert cfg.tokenizer_id == "NeoQuasar/Kronos-Tokenizer-base"  # from the 'small' variant
    assert cfg.max_context == 256  # explicit context beats the variant
