"""Whole-market expansion pure logic (Phase 6): symbol normalization."""

from __future__ import annotations

import pytest
from app.services.market_expansion import TrackError, normalize


def test_normalize_nse_suffix():
    assert normalize("RELIANCE.NS") == ("RELIANCE", "RELIANCE.NS", "NSE")


def test_normalize_bse_suffix():
    assert normalize("TATASTEEL.BO") == ("TATASTEEL", "TATASTEEL.BO", "BSE")


def test_normalize_index_keeps_caret():
    assert normalize("^NSEI") == ("NSEI", "^NSEI", "NSE")


def test_normalize_bare_symbol_defaults_to_nse():
    assert normalize("infy") == ("INFY", "INFY.NS", "NSE")


def test_normalize_empty_raises():
    with pytest.raises(TrackError):
        normalize("   ")
