"""Portfolio analytics (Phase 6): VaR, Monte Carlo, optimization - numpy only.

No scipy (the slim Render image ships without it): the inverse-normal CDF is a
documented rational approximation, Monte Carlo is GBM via ``default_rng``, and
mean-variance optimization is long-only Dirichlet frontier sampling plus a
ridge-regularized closed-form reference. All arrays are request-scoped and
small (< a few MB). Pure functions are unit-tested; the session orchestrator
composes them and never raises - insufficient data returns ``available: false``.
"""

from __future__ import annotations

import uuid
from typing import Any

import numpy as np
import pandas as pd
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.simulation import SimPortfolio, SimPosition
from app.services import market_data

log = structlog.get_logger(__name__)

TRADING_DAYS = 252
MIN_HISTORY = 60  # overlapping return days required for meaningful stats
MAX_OPT_ASSETS = 25


# --------------------------------------------------------------------------- #
# Pure math
# --------------------------------------------------------------------------- #

def norm_ppf(p: float) -> float:
    """Inverse standard-normal CDF (Acklam's rational approximation).

    Max absolute error ~1.15e-9 over (0,1); avoids a scipy dependency for the
    only place we'd need it (parametric-VaR z-scores).
    """
    if p <= 0.0:
        return float("-inf")
    if p >= 1.0:
        return float("inf")
    a = [-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
         1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00]
    b = [-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
         6.680131188771972e01, -1.328068155288572e01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
         -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00,
         3.754408661907416e00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = np.sqrt(-2 * np.log(p))
        return float((((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])
                     / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1))
    if p > phigh:
        q = np.sqrt(-2 * np.log(1 - p))
        return float(-(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])
                     / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1))
    q = p - 0.5
    r = q * q
    return float((((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q
                 / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1))


def historical_var(returns: np.ndarray, confidence: float, horizon_days: int = 1) -> dict:
    """Historical VaR + CVaR as positive loss fractions, √t-scaled."""
    if returns.size == 0:
        return {"var_pct": None, "cvar_pct": None}
    scale = np.sqrt(horizon_days)
    q = np.percentile(returns, (1 - confidence) * 100)
    tail = returns[returns <= q]
    cvar = tail.mean() if tail.size else q
    return {
        "var_pct": round(float(-q * scale) * 100, 3),
        "cvar_pct": round(float(-cvar * scale) * 100, 3),
    }


def parametric_var(returns: np.ndarray, confidence: float, horizon_days: int = 1) -> dict:
    """Gaussian VaR from the return mean/σ (positive loss fraction)."""
    if returns.size < 2:
        return {"var_pct": None}
    mu = float(returns.mean())
    sigma = float(returns.std(ddof=1))
    z = norm_ppf(1 - confidence)  # negative
    var = -(mu * horizon_days + z * sigma * np.sqrt(horizon_days))
    return {"var_pct": round(float(var) * 100, 3)}


def monte_carlo_gbm(
    equity0: float,
    mu_daily: float,
    sigma_daily: float,
    horizon_days: int = TRADING_DAYS,
    n_paths: int = 2000,
    seed: int | None = None,
) -> dict:
    """Portfolio-aggregate GBM projection: percentile bands + terminal stats."""
    horizon_days = max(1, min(int(horizon_days), 504))
    n_paths = max(100, min(int(n_paths), 5000))
    rng = np.random.default_rng(seed)
    drift = mu_daily - 0.5 * sigma_daily**2
    shocks = rng.standard_normal((n_paths, horizon_days)) * sigma_daily
    log_paths = np.cumsum(drift + shocks, axis=1)
    paths = equity0 * np.exp(log_paths)  # (n_paths, horizon_days)

    pct = np.percentile(paths, [5, 25, 50, 75, 95], axis=0)
    bands = [
        {
            "day": int(t + 1),
            "p5": round(float(pct[0, t]), 2),
            "p25": round(float(pct[1, t]), 2),
            "p50": round(float(pct[2, t]), 2),
            "p75": round(float(pct[3, t]), 2),
            "p95": round(float(pct[4, t]), 2),
        }
        for t in range(horizon_days)
    ]
    terminal = paths[:, -1]
    return {
        "equity0": round(equity0, 2),
        "horizon_days": horizon_days,
        "n_paths": n_paths,
        "bands": bands,
        "terminal": {
            "median": round(float(np.median(terminal)), 2),
            "mean": round(float(terminal.mean()), 2),
            "p5": round(float(np.percentile(terminal, 5)), 2),
            "p95": round(float(np.percentile(terminal, 95)), 2),
        },
        "prob_loss": round(float((terminal < equity0).mean()), 4),
    }


def optimize_portfolio(
    returns_matrix: np.ndarray,
    symbols: list[str],
    n_samples: int = 5000,
    ridge: float = 1e-6,
    seed: int | None = None,
) -> dict:
    """Long-only mean-variance via Dirichlet frontier sampling + ridge reference.

    True long-only MV is a QP (needs a solver); with <=25 assets, Dirichlet
    sampling gives a dense, always-feasible frontier in milliseconds. Returns
    annualized risk/return for a subsampled cloud plus max-Sharpe / min-vol.
    """
    n = returns_matrix.shape[1]
    rng = np.random.default_rng(seed)
    mu = returns_matrix.mean(axis=0) * TRADING_DAYS
    cov = np.cov(returns_matrix, rowvar=False) * TRADING_DAYS
    cov = np.atleast_2d(cov) + np.eye(n) * ridge

    weights = rng.dirichlet(np.ones(n), size=n_samples)  # (n_samples, n), sum=1
    rets = weights @ mu
    vols = np.sqrt(np.einsum("ij,jk,ik->i", weights, cov, weights))
    sharpe = np.divide(rets, vols, out=np.zeros_like(rets), where=vols > 0)

    def as_alloc(w: np.ndarray) -> list[dict]:
        return [
            {"symbol": s, "weight": round(float(wi), 4)}
            for s, wi in zip(symbols, w, strict=True)
            if wi > 0.005
        ]

    i_sharpe = int(np.argmax(sharpe))
    i_minvol = int(np.argmin(vols))
    # Subsample the frontier cloud for the UI scatter.
    idx = rng.choice(n_samples, size=min(500, n_samples), replace=False)
    cloud = [
        {"risk": round(float(vols[i]) * 100, 3), "return": round(float(rets[i]) * 100, 3)}
        for i in idx
    ]
    return {
        "assets": symbols,
        "frontier": cloud,
        "max_sharpe": {
            "weights": as_alloc(weights[i_sharpe]),
            "return_pct": round(float(rets[i_sharpe]) * 100, 3),
            "risk_pct": round(float(vols[i_sharpe]) * 100, 3),
            "sharpe": round(float(sharpe[i_sharpe]), 3),
        },
        "min_vol": {
            "weights": as_alloc(weights[i_minvol]),
            "return_pct": round(float(rets[i_minvol]) * 100, 3),
            "risk_pct": round(float(vols[i_minvol]) * 100, 3),
        },
    }


def portfolio_returns(
    closes_by_symbol: dict[str, pd.Series], weights_by_symbol: dict[str, float]
) -> pd.Series:
    """Fixed-weight daily portfolio return series aligned across holdings."""
    frame = pd.DataFrame(closes_by_symbol).sort_index().dropna(how="any")
    rets = frame.pct_change().dropna(how="any")
    if rets.empty:
        return pd.Series(dtype=float)
    w = np.array([weights_by_symbol[c] for c in rets.columns], dtype=float)
    w = w / w.sum() if w.sum() else w
    return pd.Series(rets.to_numpy() @ w, index=rets.index)


# --------------------------------------------------------------------------- #
# Session orchestration
# --------------------------------------------------------------------------- #

def _unavailable(reason: str) -> dict:
    return {"available": False, "reason": reason}


async def _load_holdings(
    session: AsyncSession, portfolio: SimPortfolio
) -> tuple[list[SimPosition], dict[str, pd.Series], dict[str, float], float]:
    positions = list(
        (
            await session.execute(
                select(SimPosition).where(SimPosition.portfolio_id == portfolio.id)
            )
        )
        .scalars()
        .all()
    )
    closes: dict[str, pd.Series] = {}
    values: dict[str, float] = {}
    holdings_value = 0.0
    for pos in positions:
        df = await market_data.price_bars_dataframe(session, pos.instrument_id)
        if df.empty:
            continue
        series = df["adj_close"].astype(float)
        closes[pos.symbol] = series
        last = float(series.iloc[-1])
        values[pos.symbol] = last * pos.qty
        holdings_value += last * pos.qty
    equity = float(portfolio.cash) + holdings_value
    return positions, closes, values, equity


async def analytics_bundle(
    session: AsyncSession,
    portfolio: SimPortfolio,
    kind: str,
    *,
    horizon_days: int = 1,
    n_paths: int = 2000,
) -> dict:
    """Compose a risk / montecarlo / optimization payload; never raises."""
    _positions, closes, values, equity = await _load_holdings(session, portfolio)
    if not closes:
        return _unavailable("no positions with price history")

    weights = {s: values[s] / sum(values.values()) for s in values}
    series = portfolio_returns(closes, weights)
    if series.size < MIN_HISTORY and kind != "optimization":
        return _unavailable(f"need >= {MIN_HISTORY} overlapping return days")
    returns = series.to_numpy()

    if kind == "risk":
        out: dict[str, Any] = {"available": True, "equity": round(equity, 2), "confidence": {}}
        for c in (0.95, 0.99):
            hist = historical_var(returns, c, horizon_days)
            para = parametric_var(returns, c, horizon_days)
            var_pct = hist["var_pct"]
            out["confidence"][str(c)] = {
                "historical": hist,
                "parametric": para,
                "var_amount": round(equity * (var_pct or 0) / 100, 2),
            }
        out["horizon_days"] = horizon_days
        out["annual_vol_pct"] = round(float(returns.std(ddof=1)) * np.sqrt(TRADING_DAYS) * 100, 2)
        return out

    if kind == "montecarlo":
        mu, sigma = float(returns.mean()), float(returns.std(ddof=1))
        mc = monte_carlo_gbm(equity, mu, sigma, horizon_days, n_paths)
        mc["available"] = True
        return mc

    if kind == "optimization":
        # Top holdings by value; need enough overlapping history.
        symbols = sorted(values, key=lambda s: values[s], reverse=True)[:MAX_OPT_ASSETS]
        if len(symbols) < 2:
            return _unavailable("optimization needs at least 2 holdings")
        frame = pd.DataFrame({s: closes[s] for s in symbols}).sort_index().dropna(how="any")
        rets = frame.pct_change().dropna(how="any")
        if rets.shape[0] < MIN_HISTORY:
            return _unavailable(f"need >= {MIN_HISTORY} overlapping return days")
        result = optimize_portfolio(rets.to_numpy(), list(rets.columns))
        result["available"] = True
        result["current"] = [
            {"symbol": s, "weight": round(weights[s], 4)} for s in rets.columns
        ]
        return result

    return _unavailable(f"unknown analytics kind '{kind}'")


def _portfolio_id(portfolio: SimPortfolio) -> uuid.UUID:  # pragma: no cover - trivial
    return portfolio.id
