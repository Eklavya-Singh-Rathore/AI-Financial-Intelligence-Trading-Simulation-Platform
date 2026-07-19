"""Portfolio-analytics pure math (Phase 6): VaR, Monte Carlo, optimization."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from app.services.portfolio_analytics import (
    historical_var,
    monte_carlo_gbm,
    norm_ppf,
    optimize_portfolio,
    parametric_var,
    portfolio_returns,
)


def test_norm_ppf_known_quantiles():
    assert norm_ppf(0.5) == pytest.approx(0.0, abs=1e-6)
    assert norm_ppf(0.95) == pytest.approx(1.6448536, abs=1e-4)
    assert norm_ppf(0.99) == pytest.approx(2.3263479, abs=1e-4)
    # Symmetry.
    assert norm_ppf(0.05) == pytest.approx(-norm_ppf(0.95), abs=1e-6)
    assert norm_ppf(0.0) == float("-inf")
    assert norm_ppf(1.0) == float("inf")


def test_historical_var_and_cvar():
    # 100 returns: -0.05 .. +0.04 in 0.01 steps.
    returns = np.round(np.arange(-0.05, 0.05, 0.001), 5)
    out = historical_var(returns, 0.95, 1)
    # 5th percentile ~ -0.045 -> var ~4.5%; positive.
    assert out["var_pct"] > 0
    assert out["cvar_pct"] >= out["var_pct"]  # CVaR is deeper in the tail


def test_historical_var_scales_with_horizon():
    returns = np.random.default_rng(0).normal(0, 0.01, 500)
    v1 = historical_var(returns, 0.95, 1)["var_pct"]
    v10 = historical_var(returns, 0.95, 10)["var_pct"]
    # √t scaling (both ends rounded to 3dp, so allow rounding-scale slack).
    assert v10 == pytest.approx(v1 * np.sqrt(10), abs=0.01)


def test_parametric_var_matches_closed_form():
    returns = np.random.default_rng(1).normal(0.0002, 0.02, 2000)
    out = parametric_var(returns, 0.95, 1)
    mu, sigma = returns.mean(), returns.std(ddof=1)
    expected = -(mu + norm_ppf(0.05) * sigma) * 100
    assert out["var_pct"] == pytest.approx(expected, abs=1e-3)


def test_parametric_var_needs_two_points():
    assert parametric_var(np.array([0.01]), 0.95)["var_pct"] is None


def test_monte_carlo_seeded_deterministic_and_bands_ordered():
    a = monte_carlo_gbm(100_000, 0.0003, 0.012, horizon_days=60, n_paths=1000, seed=7)
    b = monte_carlo_gbm(100_000, 0.0003, 0.012, horizon_days=60, n_paths=1000, seed=7)
    assert a == b  # same seed -> identical
    for band in a["bands"]:
        assert band["p5"] <= band["p25"] <= band["p50"] <= band["p75"] <= band["p95"]
    assert 0.0 <= a["prob_loss"] <= 1.0
    assert len(a["bands"]) == 60


def test_monte_carlo_zero_vol_is_deterministic_growth():
    mc = monte_carlo_gbm(1000.0, 0.001, 0.0, horizon_days=10, n_paths=200, seed=1)
    # No volatility -> all paths equal; p5 == p95 each day.
    for band in mc["bands"]:
        assert band["p5"] == pytest.approx(band["p95"], abs=1e-6)
    assert mc["prob_loss"] == 0.0  # positive drift, no risk


def test_monte_carlo_bounds_clamped():
    mc = monte_carlo_gbm(1000.0, 0.0, 0.01, horizon_days=9999, n_paths=99999, seed=1)
    assert mc["horizon_days"] == 504
    assert mc["n_paths"] == 5000


def test_optimize_weights_valid_and_beats_equal_weight():
    rng = np.random.default_rng(3)
    # Asset 0: high return low vol; asset 1: low; asset 2: noise.
    a0 = rng.normal(0.001, 0.005, 300)
    a1 = rng.normal(0.0001, 0.02, 300)
    a2 = rng.normal(0.0003, 0.015, 300)
    mat = np.column_stack([a0, a1, a2])
    out = optimize_portfolio(mat, ["A0", "A1", "A2"], n_samples=4000, seed=5)
    ms = out["max_sharpe"]
    total = sum(w["weight"] for w in ms["weights"])
    assert total == pytest.approx(1.0, abs=0.02)  # weights ~sum to 1 (>0.005 filtered)
    assert all(w["weight"] >= 0 for w in ms["weights"])  # long-only
    # Max-Sharpe should tilt toward the strong asset A0.
    a0_w = next((w["weight"] for w in ms["weights"] if w["symbol"] == "A0"), 0)
    assert a0_w > 0.34  # more than equal weight
    assert len(out["frontier"]) <= 500


def test_portfolio_returns_fixed_weight():
    idx = pd.date_range("2026-01-01", periods=4, freq="D")
    closes = {
        "A": pd.Series([100, 110, 121, 133.1], index=idx),  # +10%/day
        "B": pd.Series([50, 50, 50, 50], index=idx),  # flat
    }
    series = portfolio_returns(closes, {"A": 1.0, "B": 1.0})  # 50/50
    # Each day A +10%, B 0% -> portfolio +5%.
    assert np.allclose(series.to_numpy(), 0.05, atol=1e-9)


def test_portfolio_returns_empty():
    assert portfolio_returns({}, {}).empty
