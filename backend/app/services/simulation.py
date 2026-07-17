"""Paper-trading engine (Phase 5): orders, fills, positions, equity, metrics.

Execution model (documented in ADR-0006): this is a decision-support
simulation against STORED DAILY BARS, not a broker.

* Market orders fill immediately at the latest stored close.
* Limit/stop orders rest ``open`` and are evaluated against each new daily bar
  - by the ``sim_order_sweep`` scheduler job (right after the daily ingest)
  - and lazily whenever the portfolio is read.
  Daily-bar trigger semantics (conservative, deterministic):
    buy  limit: fills at min(open, limit) when day low  <= limit
    sell limit: fills at max(open, limit) when day high >= limit
    buy  stop : fills at max(open, stop)  when day high >= stop
    sell stop : fills at min(open, stop)  when day low  <= stop
* Long-only: sells are capped at held quantity; no margin (buying power = cash).
* Positions use the average-cost method; sells realize (px - avg_cost) * qty.
* The equity curve is reconstructed on demand from trades + price history -
  no snapshot table to drift out of sync.

AI integration: an agent run's final_decision can be turned into a ``proposed``
order (source=ai) which a human must accept (executes as market) or reject.
The AI never auto-executes anything.

Money discipline: values are stored as Decimal (Numeric columns); statistics
are computed in float via pandas.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import pandas as pd
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.agent_run import AgentRun
from app.models.instrument import Instrument
from app.models.price_bar import PriceBar
from app.models.simulation import SimOrder, SimPortfolio, SimPosition, SimTrade
from app.services import market_data

log = structlog.get_logger(__name__)

_TWO_DP = Decimal("0.01")
_FOUR_DP = Decimal("0.0001")

TRADING_DAYS = 252


class SimulationError(ValueError):
    """Order/portfolio validation failure (mapped to HTTP 422 by the router)."""


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested without a database)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Bar:
    date: Any
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal


def trigger_fill_price(
    side: str,
    order_type: str,
    limit_price: Decimal | None,
    stop_price: Decimal | None,
    bar: Bar,
) -> Decimal | None:
    """Return the fill price if this daily bar triggers the resting order."""
    if order_type == "limit":
        assert limit_price is not None
        if side == "buy" and bar.low <= limit_price:
            return min(bar.open, limit_price)
        if side == "sell" and bar.high >= limit_price:
            return max(bar.open, limit_price)
    elif order_type == "stop":
        assert stop_price is not None
        if side == "buy" and bar.high >= stop_price:
            return max(bar.open, stop_price)
        if side == "sell" and bar.low <= stop_price:
            return min(bar.open, stop_price)
    return None


def avg_cost_after_buy(
    old_qty: int, old_avg: Decimal, buy_qty: int, buy_price: Decimal
) -> Decimal:
    """Average-cost re-average on a buy (4 dp, half-up)."""
    total_cost = old_avg * old_qty + buy_price * buy_qty
    return (total_cost / (old_qty + buy_qty)).quantize(_FOUR_DP, rounding=ROUND_HALF_UP)


def build_equity_curve(
    starting_cash: Decimal,
    portfolio_created: pd.Timestamp,
    trades: list[dict],
    closes: dict[str, pd.Series],
) -> pd.DataFrame:
    """Reconstruct the daily equity curve from trades + close-price series.

    ``trades``: [{date: pd.Timestamp, instrument_id: str, side, qty, price: float}]
    ``closes``: instrument_id -> Series of float closes indexed by date.
    Returns a DataFrame indexed by date with columns cash, holdings, equity,
    drawdown_pct. Always includes at least one row (portfolio creation day).
    """
    calendar = pd.DatetimeIndex(sorted({d for s in closes.values() for d in s.index}))
    calendar = calendar[calendar >= portfolio_created.normalize()]
    if calendar.empty:
        today = pd.Timestamp(datetime.now(UTC).date())
        calendar = pd.DatetimeIndex([max(portfolio_created.normalize(), today)])

    cash = pd.Series(float(starting_cash), index=calendar)
    qty: dict[str, pd.Series] = {
        inst: pd.Series(0.0, index=calendar) for inst in closes
    }
    for t in trades:
        d = pd.Timestamp(t["date"]).normalize()
        # Effective from the trade day onward (clamp pre-calendar trades to start).
        eff = calendar[calendar >= d]
        start = eff[0] if len(eff) else calendar[-1]
        signed_qty = t["qty"] if t["side"] == "buy" else -t["qty"]
        cash_delta = -t["qty"] * t["price"] if t["side"] == "buy" else t["qty"] * t["price"]
        cash.loc[start:] += cash_delta
        if t["instrument_id"] in qty:
            qty[t["instrument_id"]].loc[start:] += signed_qty

    holdings = pd.Series(0.0, index=calendar)
    for inst, q in qty.items():
        # ffill over the union of history + calendar so calendar days past the
        # last bar (day-one portfolios, weekends) value at the last known close
        # instead of 0 (reindex-then-ffill would drop the history first).
        series = closes[inst]
        px = (
            series.reindex(series.index.union(calendar))
            .ffill()
            .reindex(calendar)
            .fillna(0.0)
        )
        holdings += q * px

    equity = cash + holdings
    peak = equity.cummax()
    drawdown = ((equity / peak) - 1.0) * 100.0
    return pd.DataFrame(
        {"cash": cash, "holdings": holdings, "equity": equity, "drawdown_pct": drawdown}
    )


def compute_metrics(equity: pd.Series, realized_pnls: list[float]) -> dict:
    """Performance metrics from a daily equity series + closed-trade P&Ls.

    Same conventions as the backtest engines: rf=0, sqrt(252) annualization.
    Adds Sortino and CAGR (which the backtesters lack).
    """
    out: dict[str, Any] = {
        "total_return_pct": 0.0,
        "cagr_pct": 0.0,
        "sharpe_ratio": 0.0,
        "sortino_ratio": 0.0,
        "volatility_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "win_rate": None,
        "closed_trades": len(realized_pnls),
    }
    if len(equity) >= 2 and float(equity.iloc[0]) > 0:
        start, end = float(equity.iloc[0]), float(equity.iloc[-1])
        out["total_return_pct"] = round((end / start - 1.0) * 100.0, 4)
        returns = equity.pct_change().dropna()
        n = len(returns)
        if n >= 2:
            mean, std = float(returns.mean()), float(returns.std())
            if std > 0:
                out["sharpe_ratio"] = round(mean / std * math.sqrt(TRADING_DAYS), 4)
            downside = returns[returns < 0]
            dstd = float(downside.std()) if len(downside) >= 2 else 0.0
            if dstd > 0:
                out["sortino_ratio"] = round(mean / dstd * math.sqrt(TRADING_DAYS), 4)
            out["volatility_pct"] = round(std * math.sqrt(TRADING_DAYS) * 100.0, 4)
            if end > 0:
                out["cagr_pct"] = round(
                    ((end / start) ** (TRADING_DAYS / n) - 1.0) * 100.0, 4
                )
        peak = equity.cummax()
        out["max_drawdown_pct"] = round(float(((equity / peak) - 1.0).min()) * 100.0, 4)
    if realized_pnls:
        wins = sum(1 for p in realized_pnls if p > 0)
        out["win_rate"] = round(wins / len(realized_pnls), 4)
    return out


def derive_proposal(
    final_decision: dict, equity: float, latest_close: float, held_qty: int
) -> tuple[str, int]:
    """Turn an agent run's final_decision into (side, qty) for a proposed order."""
    action = str(final_decision.get("action", "")).upper()
    size_pct = float(final_decision.get("size_pct") or 0.0)
    verdict = str(final_decision.get("risk_verdict", "approve")).lower()
    if action not in ("BUY", "SELL"):
        raise SimulationError("only BUY or SELL decisions can be sent to the simulation")
    if verdict == "veto" or size_pct <= 0:
        raise SimulationError("this decision was vetoed or sized to zero by the risk manager")
    if latest_close <= 0:
        raise SimulationError("no price data available for this instrument")
    qty = math.floor((size_pct / 100.0) * equity / latest_close)
    if action == "SELL":
        qty = min(qty, held_qty)
        if qty < 1:
            raise SimulationError("no held shares to sell for this instrument")
    if qty < 1:
        raise SimulationError("decision size is too small for one share at the current price")
    return ("buy" if action == "BUY" else "sell", qty)


# ---------------------------------------------------------------------------
# DB flows
# ---------------------------------------------------------------------------


async def get_or_create_portfolio(session: AsyncSession, user_id: uuid.UUID | None) -> SimPortfolio:
    stmt = select(SimPortfolio).where(
        SimPortfolio.user_id == user_id if user_id is not None else SimPortfolio.user_id.is_(None)
    )
    portfolio = (await session.execute(stmt)).scalar_one_or_none()
    if portfolio is not None:
        return portfolio
    starting = Decimal(str(get_settings().sim_starting_cash)).quantize(_TWO_DP)
    portfolio = SimPortfolio(
        id=uuid.uuid4(), user_id=user_id, starting_cash=starting, cash=starting
    )
    session.add(portfolio)
    await session.commit()
    await session.refresh(portfolio)
    log.info("sim_portfolio_created", portfolio_id=str(portfolio.id), user_id=str(user_id))
    return portfolio


async def latest_close(session: AsyncSession, instrument_id: uuid.UUID) -> tuple[Any, Decimal]:
    row = (
        await session.execute(
            select(PriceBar.date, PriceBar.close)
            .where(PriceBar.instrument_id == instrument_id)
            .order_by(PriceBar.date.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        raise SimulationError("no price data available for this instrument")
    return row.date, Decimal(row.close).quantize(_TWO_DP)


async def _get_position(
    session: AsyncSession, portfolio_id: uuid.UUID, instrument_id: uuid.UUID
) -> SimPosition | None:
    return (
        await session.execute(
            select(SimPosition).where(
                SimPosition.portfolio_id == portfolio_id,
                SimPosition.instrument_id == instrument_id,
            )
        )
    ).scalar_one_or_none()


async def _apply_fill(
    session: AsyncSession,
    portfolio: SimPortfolio,
    order: SimOrder,
    price: Decimal,
) -> SimTrade:
    """Create the trade and update position + cash. Caller commits.

    Raises SimulationError (leaving the order untouched) when cash/shares are
    insufficient at fill time.
    """
    price = price.quantize(_TWO_DP)
    value = (price * order.qty).quantize(_TWO_DP)
    position = await _get_position(session, portfolio.id, order.instrument_id)
    realized: Decimal | None = None

    if order.side == "buy":
        if portfolio.cash < value:
            raise SimulationError(
                f"insufficient cash: need {value}, have {portfolio.cash.quantize(_TWO_DP)}"
            )
        portfolio.cash = (portfolio.cash - value).quantize(_TWO_DP)
        if position is None:
            session.add(
                SimPosition(
                    id=uuid.uuid4(),
                    portfolio_id=portfolio.id,
                    instrument_id=order.instrument_id,
                    symbol=order.symbol,
                    qty=order.qty,
                    avg_cost=price.quantize(_FOUR_DP),
                )
            )
        else:
            position.avg_cost = avg_cost_after_buy(
                position.qty, position.avg_cost, order.qty, price
            )
            position.qty += order.qty
    else:  # sell
        held = position.qty if position is not None else 0
        if position is None or held < order.qty:
            raise SimulationError(f"insufficient shares: have {held}, selling {order.qty}")
        realized = ((price - position.avg_cost) * order.qty).quantize(_TWO_DP)
        portfolio.cash = (portfolio.cash + value).quantize(_TWO_DP)
        position.qty -= order.qty
        if position.qty == 0:
            await session.delete(position)

    order.status = "filled"
    order.filled_at = datetime.now(UTC)
    trade = SimTrade(
        id=uuid.uuid4(),
        order_id=order.id,
        portfolio_id=portfolio.id,
        instrument_id=order.instrument_id,
        symbol=order.symbol,
        side=order.side,
        qty=order.qty,
        price=price,
        value=value,
        realized_pnl=realized,
    )
    session.add(trade)
    return trade


async def place_order(
    session: AsyncSession,
    portfolio: SimPortfolio,
    *,
    symbol: str,
    side: str,
    order_type: str,
    qty: int,
    limit_price: Decimal | None = None,
    stop_price: Decimal | None = None,
    source: str = "manual",
    agent_run_id: uuid.UUID | None = None,
    initial_status: str | None = None,
) -> SimOrder:
    """Validate and create an order; market orders execute immediately."""
    instrument = await market_data.get_instrument_by_symbol(session, symbol.upper())
    if instrument is None:
        raise LookupError(f"unknown symbol '{symbol}'")
    if qty < 1:
        raise SimulationError("qty must be >= 1")
    if order_type == "limit" and (limit_price is None or limit_price <= 0):
        raise SimulationError("limit orders require a positive limit_price")
    if order_type == "stop" and (stop_price is None or stop_price <= 0):
        raise SimulationError("stop orders require a positive stop_price")
    if order_type == "market" and (limit_price is not None or stop_price is not None):
        raise SimulationError("market orders take no limit/stop price")

    if side == "sell":
        position = await _get_position(session, portfolio.id, instrument.id)
        held = position.qty if position is not None else 0
        if held < qty:
            raise SimulationError(f"insufficient shares: have {held}, selling {qty} (long-only)")

    order = SimOrder(
        id=uuid.uuid4(),
        portfolio_id=portfolio.id,
        instrument_id=instrument.id,
        symbol=instrument.symbol,
        side=side,
        order_type=order_type,
        qty=qty,
        limit_price=limit_price,
        stop_price=stop_price,
        source=source,
        agent_run_id=agent_run_id,
        status=initial_status or ("open" if order_type in ("limit", "stop") else "open"),
    )
    session.add(order)

    if initial_status == "proposed":
        await session.commit()
        await session.refresh(order)
        return order

    if order_type == "market":
        _, price = await latest_close(session, instrument.id)
        try:
            await _apply_fill(session, portfolio, order, price)
        except SimulationError:
            # Roll back the uncommitted order/fill, then refresh the portfolio:
            # rollback expires all ORM instances, and a lazy refresh from async
            # code raises MissingGreenlet on the next attribute access.
            await session.rollback()
            await session.refresh(portfolio)
            raise
    await session.commit()
    await session.refresh(order)
    log.info(
        "sim_order_placed",
        order_id=str(order.id),
        symbol=order.symbol,
        side=side,
        order_type=order_type,
        status=order.status,
    )
    return order


async def sweep_open_orders(session: AsyncSession, portfolio: SimPortfolio) -> int:
    """Evaluate resting limit/stop orders against daily bars; returns fills."""
    open_orders = (
        (
            await session.execute(
                select(SimOrder).where(
                    SimOrder.portfolio_id == portfolio.id, SimOrder.status == "open"
                )
            )
        )
        .scalars()
        .all()
    )
    fills = 0
    for order in open_orders:
        if order.order_type == "market":  # defensive; markets never rest
            continue
        bars = (
            (
                await session.execute(
                    select(PriceBar)
                    .where(
                        PriceBar.instrument_id == order.instrument_id,
                        PriceBar.date >= order.created_at.date(),
                    )
                    .order_by(PriceBar.date.asc())
                )
            )
            .scalars()
            .all()
        )
        for bar in bars:
            price = trigger_fill_price(
                order.side,
                order.order_type,
                order.limit_price,
                order.stop_price,
                Bar(
                    date=bar.date,
                    open=Decimal(bar.open),
                    high=Decimal(bar.high),
                    low=Decimal(bar.low),
                    close=Decimal(bar.close),
                ),
            )
            if price is None:
                continue
            try:
                await _apply_fill(session, portfolio, order, price)
                fills += 1
            except SimulationError as exc:
                order.status = "rejected"
                order.reason = str(exc)
            break
    if open_orders:
        await session.commit()
    if fills:
        log.info("sim_sweep_filled", portfolio_id=str(portfolio.id), fills=fills)
    return fills


async def portfolio_snapshot(session: AsyncSession, portfolio: SimPortfolio) -> dict:
    """Cash, positions (with latest prices), equity, allocation, P&L."""
    positions = (
        (
            await session.execute(
                select(SimPosition).where(SimPosition.portfolio_id == portfolio.id)
            )
        )
        .scalars()
        .all()
    )
    realized_total = Decimal("0")
    for row in (
        await session.execute(
            select(SimTrade.realized_pnl).where(
                SimTrade.portfolio_id == portfolio.id, SimTrade.realized_pnl.is_not(None)
            )
        )
    ).all():
        realized_total += row.realized_pnl

    out_positions: list[dict[str, Any]] = []
    holdings_value = Decimal("0")
    for pos in positions:
        try:
            price_date, price = await latest_close(session, pos.instrument_id)
        except SimulationError:
            price_date, price = None, pos.avg_cost.quantize(_TWO_DP)
        market_value = (price * pos.qty).quantize(_TWO_DP)
        holdings_value += market_value
        entry: dict[str, Any] = {
            "symbol": pos.symbol,
            "qty": pos.qty,
            "avg_cost": float(pos.avg_cost),
            "last_price": float(price),
            "price_date": price_date.isoformat() if price_date else None,
            "market_value": float(market_value),
            "unrealized_pnl": float(((price - pos.avg_cost) * pos.qty).quantize(_TWO_DP)),
        }
        out_positions.append(entry)
    equity = (portfolio.cash + holdings_value).quantize(_TWO_DP)
    for p in out_positions:
        mv = float(p["market_value"])
        p["allocation_pct"] = round(mv / float(equity) * 100.0, 2) if equity else 0.0

    return {
        "portfolio_id": str(portfolio.id),
        "name": portfolio.name,
        "created_at": portfolio.created_at.isoformat(),
        "starting_cash": float(portfolio.starting_cash),
        "cash": float(portfolio.cash),
        "buying_power": float(portfolio.cash),
        "holdings_value": float(holdings_value),
        "equity": float(equity),
        "total_pnl": float((equity - portfolio.starting_cash).quantize(_TWO_DP)),
        "total_pnl_pct": round(
            (float(equity) / float(portfolio.starting_cash) - 1.0) * 100.0, 4
        )
        if portfolio.starting_cash
        else 0.0,
        "realized_pnl": float(realized_total.quantize(_TWO_DP)),
        "cash_allocation_pct": round(float(portfolio.cash) / float(equity) * 100.0, 2)
        if equity
        else 100.0,
        "positions": sorted(out_positions, key=lambda p: -p["market_value"]),
    }


async def _trades_and_closes(
    session: AsyncSession, portfolio: SimPortfolio
) -> tuple[list[dict], dict[str, pd.Series]]:
    trades = (
        (
            await session.execute(
                select(SimTrade)
                .where(SimTrade.portfolio_id == portfolio.id)
                .order_by(SimTrade.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    trade_dicts = [
        {
            "date": pd.Timestamp(t.created_at.date()),
            "instrument_id": str(t.instrument_id),
            "side": t.side,
            "qty": t.qty,
            "price": float(t.price),
        }
        for t in trades
    ]
    closes: dict[str, pd.Series] = {}
    for inst_id in {t.instrument_id for t in trades}:
        df = await market_data.price_bars_dataframe(session, inst_id)
        if not df.empty:
            series = df["close"].astype(float)
            series.index = pd.to_datetime(series.index)
            closes[str(inst_id)] = series
    return trade_dicts, closes


async def performance(session: AsyncSession, portfolio: SimPortfolio) -> dict:
    """Metrics + equity/drawdown series + AI-vs-manual comparison."""
    trade_dicts, closes = await _trades_and_closes(session, portfolio)
    curve = build_equity_curve(
        portfolio.starting_cash,
        pd.Timestamp(portfolio.created_at.date()),
        trade_dicts,
        closes,
    )
    realized_rows = (
        await session.execute(
            select(SimTrade.realized_pnl, SimOrder.source)
            .join(SimOrder, SimOrder.id == SimTrade.order_id)
            .where(SimTrade.portfolio_id == portfolio.id, SimTrade.realized_pnl.is_not(None))
        )
    ).all()
    metrics = compute_metrics(curve["equity"], [float(r.realized_pnl) for r in realized_rows])

    by_source: dict[str, dict] = {}
    order_counts = (
        await session.execute(
            select(SimOrder.source, SimOrder.status, SimOrder.id).where(
                SimOrder.portfolio_id == portfolio.id
            )
        )
    ).all()
    for source in ("manual", "ai"):
        pnls = [float(r.realized_pnl) for r in realized_rows if r.source == source]
        filled = sum(1 for o in order_counts if o.source == source and o.status == "filled")
        by_source[source] = {
            "filled_orders": filled,
            "closed_trades": len(pnls),
            "realized_pnl": round(sum(pnls), 2),
            "win_rate": round(sum(1 for p in pnls if p > 0) / len(pnls), 4) if pnls else None,
        }

    series = [
        {
            "date": idx.date().isoformat(),
            "equity": round(float(row.equity), 2),
            "drawdown_pct": round(float(row.drawdown_pct), 4),
        }
        for idx, row in curve.iterrows()
    ]
    return {"metrics": metrics, "series": series, "ai_vs_manual": by_source}


async def create_proposal_from_run(
    session: AsyncSession, portfolio: SimPortfolio, run: AgentRun
) -> SimOrder:
    """Turn a completed agent run's final_decision into a proposed AI order."""
    if run.status != "completed" or not run.final_decision:
        raise SimulationError("agent run has no completed decision")
    instrument = await market_data.get_instrument_by_symbol(session, run.symbol)
    if instrument is None:
        raise LookupError(f"unknown symbol '{run.symbol}'")

    snapshot = await portfolio_snapshot(session, portfolio)
    _, price = await latest_close(session, instrument.id)
    position = await _get_position(session, portfolio.id, instrument.id)
    held = position.qty if position is not None else 0
    side, qty = derive_proposal(
        run.final_decision, snapshot["equity"], float(price), held
    )
    return await place_order(
        session,
        portfolio,
        symbol=run.symbol,
        side=side,
        order_type="market",
        qty=qty,
        source="ai",
        agent_run_id=run.id,
        initial_status="proposed",
    )


async def accept_proposal(
    session: AsyncSession, portfolio: SimPortfolio, order: SimOrder
) -> SimOrder:
    """Human accepts a proposed AI order -> executes as a market order now."""
    if order.status != "proposed":
        raise SimulationError(f"order is {order.status}, not proposed")
    _, price = await latest_close(session, order.instrument_id)
    try:
        await _apply_fill(session, portfolio, order, price)
    except SimulationError:
        await session.rollback()  # order stays proposed
        await session.refresh(portfolio)
        await session.refresh(order)
        raise
    await session.commit()
    await session.refresh(order)
    return order


async def reject_or_cancel(session: AsyncSession, order: SimOrder, *, action: str) -> SimOrder:
    """Reject a proposed order or cancel a resting open order."""
    if action == "reject":
        if order.status != "proposed":
            raise SimulationError(f"order is {order.status}, not proposed")
        order.status = "rejected"
        order.reason = "rejected by user"
    else:  # cancel
        if order.status not in ("open", "proposed"):
            raise SimulationError(f"order is {order.status}; only open/proposed can be cancelled")
        order.status = "cancelled"
    await session.commit()
    await session.refresh(order)
    return order


# ---------------------------------------------------------------------------
# Portfolio intelligence (sector exposure, diversification, correlation, risk)
# ---------------------------------------------------------------------------


async def intelligence(session: AsyncSession, portfolio: SimPortfolio) -> dict:
    snapshot = await portfolio_snapshot(session, portfolio)
    positions = snapshot["positions"]
    equity = snapshot["equity"] or 1.0
    settings = get_settings()

    # Sector exposure (instruments -> sectors join done via ORM relationships).
    sector_values: dict[str, float] = {}
    inst_rows = (
        await session.execute(
            select(SimPosition, Instrument)
            .join(Instrument, Instrument.id == SimPosition.instrument_id)
            .where(SimPosition.portfolio_id == portfolio.id)
        )
    ).all()
    sector_names: dict[uuid.UUID, str] = {}
    if inst_rows:
        from sqlalchemy import text as sa_text

        rows = (await session.execute(sa_text("SELECT id, name FROM sectors"))).all()
        sector_names = {r.id: r.name for r in rows}
    pos_by_symbol = {p["symbol"]: p for p in positions}
    for sim_pos, inst in inst_rows:
        mv = pos_by_symbol.get(sim_pos.symbol, {}).get("market_value", 0.0)
        sector = sector_names.get(inst.sector_id, "Other") if inst.sector_id else "Other"
        sector_values[sector] = sector_values.get(sector, 0.0) + mv
    if snapshot["cash"] > 0:
        sector_values["Cash"] = snapshot["cash"]
    sector_exposure: list[dict[str, Any]] = [
        {"sector": name, "value": round(v, 2), "pct": round(v / equity * 100.0, 2)}
        for name, v in sorted(sector_values.items(), key=lambda kv: -kv[1])
    ]

    # Diversification: HHI over position weights (ex-cash) -> effective N.
    weights = [p["market_value"] / equity for p in positions]
    hhi = sum(w * w for w in weights)
    effective_n = round(1.0 / hhi, 2) if hhi > 0 else 0.0

    # Concentration flags.
    cap = settings.max_position_pct * 2
    concentration = [
        {"symbol": p["symbol"], "allocation_pct": p["allocation_pct"], "flag": "oversized"}
        for p in positions
        if p["allocation_pct"] > cap
    ]

    # Correlation matrix of daily returns (held instruments, last ~180 sessions).
    corr_matrix: dict[str, Any] = {"symbols": [], "matrix": []}
    portfolio_vol_pct = 0.0
    if len(inst_rows) >= 1:
        returns = {}
        for sim_pos, _inst in inst_rows:
            df = await market_data.price_bars_dataframe(session, sim_pos.instrument_id)
            if df.empty:
                continue
            series = df["close"].astype(float).tail(181)
            returns[sim_pos.symbol] = series.pct_change().dropna()
        if returns:
            rdf = pd.DataFrame(returns).dropna(how="all")
            if len(rdf.columns) >= 2:
                corr = rdf.corr().round(3)
                corr_matrix = {
                    "symbols": list(corr.columns),
                    "matrix": [
                        [None if pd.isna(v) else float(v) for v in row] for row in corr.values
                    ],
                }
            weights_map = {
                str(p["symbol"]): float(p["market_value"]) / equity for p in positions
            }
            aligned = rdf.fillna(0.0)
            w = pd.Series({c: weights_map.get(c, 0.0) for c in aligned.columns})
            if w.sum() > 0:
                port_returns = aligned.mul(w, axis=1).sum(axis=1)
                if len(port_returns) >= 2 and float(port_returns.std()) > 0:
                    portfolio_vol_pct = round(
                        float(port_returns.std()) * math.sqrt(TRADING_DAYS) * 100.0, 2
                    )

    # Risk score 0-100: volatility + concentration + (lack of) diversification.
    vol_component = min(portfolio_vol_pct / 40.0, 1.0) * 45.0
    conc_component = min(hhi, 1.0) * 35.0
    div_component = (1.0 - min(effective_n / 8.0, 1.0)) * 20.0 if positions else 0.0
    invested_frac = min(float(snapshot["holdings_value"]) / equity, 1.0) if equity else 0.0
    risk_score = round((vol_component + conc_component + div_component) * invested_frac, 1)

    # Rule-based rebalancing suggestions.
    suggestions: list[str] = []
    for c in concentration:
        suggestions.append(
            f"Trim {c['symbol']} ({c['allocation_pct']:.1f}% of equity) toward "
            f"{settings.max_position_pct:.0f}% to reduce single-name risk."
        )
    equity_sectors = [s for s in sector_exposure if s["sector"] != "Cash"]
    if equity_sectors and equity_sectors[0]["pct"] > 50:
        top = equity_sectors[0]
        suggestions.append(
            f"Over half of equity sits in {top['sector']} "
            f"({top['pct']:.1f}%) - diversify across sectors."
        )
    if positions and effective_n < 3 and len(positions) >= 2:
        suggestions.append(
            "Position weights are top-heavy (effective holdings "
            f"{effective_n:.1f}) - consider evening out position sizes."
        )
    cash_pct = snapshot["cash_allocation_pct"]
    if cash_pct > 80 and positions:
        suggestions.append(f"{cash_pct:.0f}% of the portfolio is idle cash.")
    if not positions:
        suggestions.append("No positions yet - place a first order to start the simulation.")

    return {
        "risk_score": risk_score,
        "portfolio_volatility_pct": portfolio_vol_pct,
        "sector_exposure": sector_exposure,
        "diversification": {
            "positions": len(positions),
            "hhi": round(hhi, 4),
            "effective_positions": effective_n,
        },
        "concentration": concentration,
        "correlation": corr_matrix,
        "suggestions": suggestions,
    }
