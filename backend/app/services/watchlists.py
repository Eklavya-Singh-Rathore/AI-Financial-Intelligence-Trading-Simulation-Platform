"""Watchlist service (Phase 6): user-curated instrument groups.

Ownership follows the simulation convention: every function is scoped by the
caller's ``user_id`` (None = the service/admin context's own rows), so
cross-user access is impossible by construction - unknown or foreign ids
surface as LookupError -> 404 at the router.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instrument import Instrument
from app.models.watchlist import Watchlist, WatchlistItem
from app.services import market_data

log = structlog.get_logger(__name__)

MAX_LISTS_PER_USER = 20


class WatchlistError(ValueError):
    """User-correctable watchlist failure (duplicate name, limits)."""


def _owner_filter(stmt, user_id: uuid.UUID | None):
    return stmt.where(
        Watchlist.user_id == user_id if user_id is not None else Watchlist.user_id.is_(None)
    )


async def list_watchlists(session: AsyncSession, user_id: uuid.UUID | None) -> list[dict]:
    """All of the owner's watchlists with their member symbols (one query each way)."""
    stmt = _owner_filter(select(Watchlist), user_id).order_by(Watchlist.created_at)
    lists = (await session.execute(stmt)).scalars().all()
    if not lists:
        return []
    rows = (
        await session.execute(
            select(WatchlistItem.watchlist_id, Instrument.symbol)
            .join(Instrument, Instrument.id == WatchlistItem.instrument_id)
            .where(WatchlistItem.watchlist_id.in_([w.id for w in lists]))
            .order_by(WatchlistItem.position, WatchlistItem.created_at)
        )
    ).all()
    symbols_by_list: dict[uuid.UUID, list[str]] = {}
    for wl_id, symbol in rows:
        symbols_by_list.setdefault(wl_id, []).append(symbol)
    return [
        {
            "id": w.id,
            "name": w.name,
            "created_at": w.created_at,
            "symbols": symbols_by_list.get(w.id, []),
        }
        for w in lists
    ]


async def get_watchlist(
    session: AsyncSession, user_id: uuid.UUID | None, watchlist_id: uuid.UUID
) -> Watchlist:
    wl = (
        await session.execute(
            _owner_filter(select(Watchlist).where(Watchlist.id == watchlist_id), user_id)
        )
    ).scalar_one_or_none()
    if wl is None:
        raise LookupError(f"watchlist '{watchlist_id}' not found")
    return wl


async def create_watchlist(
    session: AsyncSession, user_id: uuid.UUID | None, name: str
) -> Watchlist:
    name = name.strip() or "Watchlist"
    count = (
        await session.execute(_owner_filter(select(func.count(Watchlist.id)), user_id))
    ).scalar() or 0
    if count >= MAX_LISTS_PER_USER:
        raise WatchlistError(f"watchlist limit reached ({MAX_LISTS_PER_USER})")
    existing = (
        await session.execute(
            _owner_filter(select(Watchlist.id).where(Watchlist.name == name), user_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise WatchlistError(f"a watchlist named '{name}' already exists")
    wl = Watchlist(id=uuid.uuid4(), user_id=user_id, name=name)
    session.add(wl)
    await session.commit()
    log.info("watchlist_created", watchlist_id=str(wl.id), name=name)
    return wl


async def rename_watchlist(session: AsyncSession, wl: Watchlist, name: str) -> Watchlist:
    name = name.strip()
    if not name:
        raise WatchlistError("watchlist name cannot be empty")
    clash = (
        await session.execute(
            _owner_filter(
                select(Watchlist.id).where(Watchlist.name == name, Watchlist.id != wl.id),
                wl.user_id,
            )
        )
    ).scalar_one_or_none()
    if clash is not None:
        raise WatchlistError(f"a watchlist named '{name}' already exists")
    wl.name = name
    await session.commit()
    return wl


async def delete_watchlist(session: AsyncSession, wl: Watchlist) -> None:
    await session.delete(wl)
    await session.commit()
    log.info("watchlist_deleted", watchlist_id=str(wl.id))


async def add_item(session: AsyncSession, wl: Watchlist, symbol: str) -> bool:
    """Add a symbol to the list; idempotent. Returns True when newly added."""
    instrument = await market_data.get_instrument_by_symbol(session, symbol.upper())
    if instrument is None:
        raise LookupError(f"instrument '{symbol}' not found")
    existing = (
        await session.execute(
            select(WatchlistItem.id).where(
                WatchlistItem.watchlist_id == wl.id,
                WatchlistItem.instrument_id == instrument.id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return False
    max_pos = (
        await session.execute(
            select(func.coalesce(func.max(WatchlistItem.position), 0)).where(
                WatchlistItem.watchlist_id == wl.id
            )
        )
    ).scalar() or 0
    session.add(
        WatchlistItem(
            id=uuid.uuid4(),
            watchlist_id=wl.id,
            instrument_id=instrument.id,
            position=max_pos + 1,
        )
    )
    await session.commit()
    return True


async def remove_item(session: AsyncSession, wl: Watchlist, symbol: str) -> bool:
    """Remove a symbol from the list. Returns True when something was removed."""
    instrument = await market_data.get_instrument_by_symbol(session, symbol.upper())
    if instrument is None:
        raise LookupError(f"instrument '{symbol}' not found")
    item = (
        await session.execute(
            select(WatchlistItem).where(
                WatchlistItem.watchlist_id == wl.id,
                WatchlistItem.instrument_id == instrument.id,
            )
        )
    ).scalar_one_or_none()
    if item is None:
        return False
    await session.delete(item)
    await session.commit()
    return True


async def reorder_items(session: AsyncSession, wl: Watchlist, symbols: list[str]) -> list[str]:
    """Set item positions to the given symbol order.

    ``symbols`` must be exactly the list's current members (any order); a
    mismatch (stale client, unknown symbol) raises so the caller refetches.
    Returns the persisted order.
    """
    rows = (
        await session.execute(
            select(WatchlistItem, Instrument.symbol)
            .join(Instrument, Instrument.id == WatchlistItem.instrument_id)
            .where(WatchlistItem.watchlist_id == wl.id)
        )
    ).all()
    item_by_symbol = {symbol: item for item, symbol in rows}
    wanted = [s.strip().upper() for s in symbols]
    if len(set(wanted)) != len(wanted) or set(wanted) != set(item_by_symbol):
        raise WatchlistError("reorder must list exactly the current members, once each")
    for pos, symbol in enumerate(wanted):
        item_by_symbol[symbol].position = pos
    await session.commit()
    return wanted


async def watchlist_instrument_ids(
    session: AsyncSession, user_id: uuid.UUID | None, watchlist_id: uuid.UUID
) -> list[uuid.UUID]:
    """Member instrument ids (ownership enforced) - used by the summary filter."""
    wl = await get_watchlist(session, user_id, watchlist_id)
    rows = (
        await session.execute(
            select(WatchlistItem.instrument_id)
            .where(WatchlistItem.watchlist_id == wl.id)
            .order_by(WatchlistItem.position, WatchlistItem.created_at)
        )
    ).scalars()
    return list(rows)
