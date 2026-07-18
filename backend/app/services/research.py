"""Financial research (Phase 5): company profiles, statements, earnings.

Data source is yfinance (already the OHLCV provider). Fundamentals are fetched
via ``yf.Ticker(provider_symbol)`` in a worker thread, serialized to plain
JSON, and cached in ``instrument_fundamentals`` with a TTL
(``FUNDAMENTALS_TTL_HOURS``). yfinance is flaky by nature, so every failure
degrades gracefully: serve the stale cache if one exists, else a DB-only
profile built from the instruments table - never raise to the caller
(same philosophy as the news client).

Earnings analysis is DERIVED from the quarterly income statement (revenue /
net-income trend + QoQ/YoY growth) - yfinance's ``earnings_dates`` needs lxml
and is deliberately avoided.
"""

from __future__ import annotations

import asyncio
import math
from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.instrument import Instrument
from app.models.research import InstrumentFundamentals
from app.services import market_data

log = structlog.get_logger(__name__)

# Profile keys kept from Ticker.info (curated: identity + valuation basics).
_PROFILE_KEYS = (
    "longName",
    "longBusinessSummary",
    "sector",
    "industry",
    "website",
    "fullTimeEmployees",
    "marketCap",
    "trailingPE",
    "forwardPE",
    "priceToBook",
    "dividendYield",
    "beta",
    "fiftyTwoWeekHigh",
    "fiftyTwoWeekLow",
    "currency",
)

# Statement line items surfaced to the UI (when present), in display order.
_INCOME_ROWS = (
    "Total Revenue",
    "Gross Profit",
    "Operating Income",
    "Pretax Income",
    "Net Income",
    "Basic EPS",
)
_BALANCE_ROWS = (
    "Total Assets",
    "Total Liabilities Net Minority Interest",
    "Stockholders Equity",
    "Cash And Cash Equivalents",
    "Total Debt",
)
_CASHFLOW_ROWS = (
    "Operating Cash Flow",
    "Investing Cash Flow",
    "Financing Cash Flow",
    "Free Cash Flow",
    "Capital Expenditure",
)


def _clean_number(value: Any) -> float | int | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return int(f) if f.is_integer() and abs(f) < 1e15 else f


def serialize_statement(df: pd.DataFrame | None, keep_rows: tuple[str, ...]) -> dict:
    """DataFrame (rows=line items, cols=period Timestamps) -> plain JSON.

    Output: {"periods": ["2026-03-31", ...], "rows": {"Total Revenue": [v, ...]}}
    NaN/inf -> null; periods newest-first (yfinance's native order).
    """
    if df is None or getattr(df, "empty", True):
        return {"periods": [], "rows": {}}
    periods = [str(pd.Timestamp(c).date()) for c in df.columns]
    rows: dict[str, list[float | int | None]] = {}
    for name in keep_rows:
        if name in df.index:
            rows[name] = [_clean_number(v) for v in df.loc[name].tolist()]
    return {"periods": periods, "rows": rows}


def _fetch_from_yfinance(provider_symbol: str) -> dict[str, Any]:
    """Blocking yfinance fetch (call via asyncio.to_thread)."""
    import yfinance as yf

    ticker = yf.Ticker(provider_symbol)
    info = ticker.info or {}
    profile = {k: info.get(k) for k in _PROFILE_KEYS if info.get(k) is not None}
    # Sanitize numbers (yfinance occasionally returns NaN in info).
    for key, value in list(profile.items()):
        if isinstance(value, float):
            profile[key] = _clean_number(value)
    return {
        "profile": profile,
        "income_annual": serialize_statement(ticker.income_stmt, _INCOME_ROWS),
        "income_quarterly": serialize_statement(ticker.quarterly_income_stmt, _INCOME_ROWS),
        "balance_sheet": serialize_statement(ticker.balance_sheet, _BALANCE_ROWS),
        "cashflow": serialize_statement(ticker.cashflow, _CASHFLOW_ROWS),
    }


async def _db_profile(session: AsyncSession, instrument: Instrument) -> dict:
    """Fallback profile from the instruments table alone (always available)."""
    from sqlalchemy import text as sa_text

    sector = industry = None
    if instrument.sector_id:
        sector = (
            await session.execute(
                sa_text("SELECT name FROM sectors WHERE id = :id"), {"id": instrument.sector_id}
            )
        ).scalar_one_or_none()
    if instrument.industry_id:
        industry = (
            await session.execute(
                sa_text("SELECT name FROM industries WHERE id = :id"),
                {"id": instrument.industry_id},
            )
        ).scalar_one_or_none()
    return {
        "longName": instrument.display_name,
        "sector": sector,
        "industry": industry,
        "currency": instrument.currency,
        "country": instrument.country,
        "isin": instrument.isin,
        "listing_date": instrument.listing_date.isoformat() if instrument.listing_date else None,
        "instrument_type": str(instrument.instrument_type),
    }


async def get_fundamentals(
    session: AsyncSession, symbol: str, *, force_refresh: bool = False
) -> dict[str, Any]:
    """Cached fundamentals for a symbol; refreshes when stale; never raises.

    Returns {profile, income_annual, income_quarterly, balance_sheet, cashflow,
    fetched_at, source: yfinance|cache|stale-cache|db-only}.
    """
    instrument = await market_data.get_instrument_by_symbol(session, symbol.upper())
    if instrument is None:
        raise LookupError(f"unknown symbol '{symbol}'")

    row = (
        await session.execute(
            select(InstrumentFundamentals).where(
                InstrumentFundamentals.instrument_id == instrument.id
            )
        )
    ).scalar_one_or_none()

    ttl = timedelta(hours=get_settings().fundamentals_ttl_hours)
    fresh = (
        row is not None
        and row.fetched_at is not None
        and datetime.now(UTC) - row.fetched_at < ttl
    )
    if fresh and not force_refresh:
        assert row is not None
        return {
            "profile": row.profile or {},
            "income_annual": row.income_annual or {},
            "income_quarterly": row.income_quarterly or {},
            "balance_sheet": row.balance_sheet or {},
            "cashflow": row.cashflow or {},
            "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
            "source": "cache",
        }

    provider = await market_data.get_yfinance_provider(session)
    provider_symbol = (
        await market_data.get_provider_symbol(session, instrument.id, provider.id)
    ) or instrument.symbol
    try:
        data = await asyncio.to_thread(_fetch_from_yfinance, provider_symbol)
        if row is None:
            row = InstrumentFundamentals(instrument_id=instrument.id)
            session.add(row)
        row.profile = data["profile"]
        row.income_annual = data["income_annual"]
        row.income_quarterly = data["income_quarterly"]
        row.balance_sheet = data["balance_sheet"]
        row.cashflow = data["cashflow"]
        row.fetched_at = datetime.now(UTC)
        await session.commit()
        log.info("fundamentals_refreshed", symbol=instrument.symbol)
        return {**data, "fetched_at": row.fetched_at.isoformat(), "source": "yfinance"}
    except Exception as exc:  # noqa: BLE001 - research is best-effort
        log.warning("fundamentals_fetch_failed", symbol=instrument.symbol, error=str(exc)[:200])
        if row is not None and row.profile:
            return {
                "profile": row.profile or {},
                "income_annual": row.income_annual or {},
                "income_quarterly": row.income_quarterly or {},
                "balance_sheet": row.balance_sheet or {},
                "cashflow": row.cashflow or {},
                "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
                "source": "stale-cache",
            }
        # Optional Alpha Vantage enrichment when yfinance had nothing (Phase 6).
        av_profile = await _alpha_vantage_profile(provider_symbol)
        if av_profile:
            return {
                "profile": av_profile,
                "income_annual": {},
                "income_quarterly": {},
                "balance_sheet": {},
                "cashflow": {},
                "fetched_at": None,
                "source": "alpha_vantage",
            }
        return {
            "profile": await _db_profile(session, instrument),
            "income_annual": {},
            "income_quarterly": {},
            "balance_sheet": {},
            "cashflow": {},
            "fetched_at": None,
            "source": "db-only",
        }


# Alpha Vantage OVERVIEW field -> our curated profile key.
_AV_PROFILE_MAP = {
    "Name": "longName",
    "Description": "longBusinessSummary",
    "Sector": "sector",
    "Industry": "industry",
    "MarketCapitalization": "marketCap",
    "PERatio": "trailingPE",
    "ForwardPE": "forwardPE",
    "PriceToBookRatio": "priceToBook",
    "DividendYield": "dividendYield",
    "Beta": "beta",
    "52WeekHigh": "fiftyTwoWeekHigh",
    "52WeekLow": "fiftyTwoWeekLow",
    "Currency": "currency",
}


async def _alpha_vantage_profile(provider_symbol: str) -> dict:
    """Best-effort AV OVERVIEW -> profile dict; {} when unavailable/keyless."""
    import asyncio as _asyncio

    from app.providers.alpha_vantage import AlphaVantageProvider

    av = AlphaVantageProvider()
    if not av.available():
        return {}
    bundle = await _asyncio.to_thread(av.fetch_fundamentals, provider_symbol)
    if bundle is None:
        return {}
    profile: dict = {}
    for av_key, our_key in _AV_PROFILE_MAP.items():
        value = bundle.data.get(av_key)
        if value in (None, "", "None", "-"):
            continue
        profile[our_key] = _clean_number(value) if our_key != "longName" and our_key not in (
            "longBusinessSummary", "sector", "industry", "currency"
        ) else value
    return profile


def derive_earnings(income_quarterly: dict) -> dict[str, Any]:
    """Earnings analysis from the quarterly income statement.

    Series are newest-first (yfinance order); growth is computed QoQ against
    the next-older quarter and YoY against the quarter four back.
    """
    periods: list[str] = income_quarterly.get("periods", [])
    rows: dict = income_quarterly.get("rows", {})
    revenue = rows.get("Total Revenue") or []
    net_income = rows.get("Net Income") or []
    eps = rows.get("Basic EPS") or []

    def growth(series: list, idx: int, lag: int) -> float | None:
        if idx + lag >= len(series):
            return None
        newer, older = series[idx], series[idx + lag]
        if newer is None or older in (None, 0):
            return None
        try:
            return round((float(newer) / float(older) - 1.0) * 100.0, 2)
        except (TypeError, ValueError, ZeroDivisionError):
            return None

    quarters = []
    for i, period in enumerate(periods):
        quarters.append(
            {
                "period": period,
                "revenue": revenue[i] if i < len(revenue) else None,
                "net_income": net_income[i] if i < len(net_income) else None,
                "eps": eps[i] if i < len(eps) else None,
                "revenue_qoq_pct": growth(revenue, i, 1),
                "revenue_yoy_pct": growth(revenue, i, 4),
                "net_income_qoq_pct": growth(net_income, i, 1),
                "net_income_yoy_pct": growth(net_income, i, 4),
            }
        )
    latest = quarters[0] if quarters else None
    return {"quarters": quarters, "latest": latest}
