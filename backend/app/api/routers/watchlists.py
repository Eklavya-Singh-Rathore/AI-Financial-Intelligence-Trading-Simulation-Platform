"""Watchlist endpoints (Phase 6). Owner-scoped; cross-user access -> 404."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, get_auth
from app.db.base import get_session
from app.schemas.watchlist import (
    WatchlistCreate,
    WatchlistItemAdd,
    WatchlistOut,
    WatchlistReorder,
    WatchlistUpdate,
)
from app.services import watchlists
from app.services.watchlists import WatchlistError

router = APIRouter(prefix="/watchlists", tags=["watchlists"])

Auth = Annotated[AuthContext, Depends(get_auth)]


async def _watchlist_or_404(session: AsyncSession, auth: AuthContext, watchlist_id: uuid.UUID):
    try:
        return await watchlists.get_watchlist(session, auth.user_id, watchlist_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _out(wl, symbols: list[str]) -> WatchlistOut:
    return WatchlistOut(id=wl.id, name=wl.name, created_at=wl.created_at, symbols=symbols)


@router.get("", response_model=list[WatchlistOut])
async def list_watchlists(
    auth: Auth, session: AsyncSession = Depends(get_session)
) -> list[WatchlistOut]:
    return [WatchlistOut(**w) for w in await watchlists.list_watchlists(session, auth.user_id)]


@router.post("", response_model=WatchlistOut, status_code=201)
async def create_watchlist(
    payload: WatchlistCreate, auth: Auth, session: AsyncSession = Depends(get_session)
) -> WatchlistOut:
    try:
        wl = await watchlists.create_watchlist(session, auth.user_id, payload.name)
    except WatchlistError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _out(wl, [])


@router.patch("/{watchlist_id}", response_model=WatchlistOut)
async def rename_watchlist(
    watchlist_id: uuid.UUID,
    payload: WatchlistUpdate,
    auth: Auth,
    session: AsyncSession = Depends(get_session),
) -> WatchlistOut:
    wl = await _watchlist_or_404(session, auth, watchlist_id)
    try:
        wl = await watchlists.rename_watchlist(session, wl, payload.name)
    except WatchlistError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    symbols = [
        w["symbols"]
        for w in await watchlists.list_watchlists(session, auth.user_id)
        if w["id"] == wl.id
    ]
    return _out(wl, symbols[0] if symbols else [])


@router.delete("/{watchlist_id}", status_code=204)
async def delete_watchlist(
    watchlist_id: uuid.UUID, auth: Auth, session: AsyncSession = Depends(get_session)
) -> None:
    wl = await _watchlist_or_404(session, auth, watchlist_id)
    await watchlists.delete_watchlist(session, wl)


@router.post("/{watchlist_id}/items", response_model=WatchlistOut, status_code=201)
async def add_item(
    watchlist_id: uuid.UUID,
    payload: WatchlistItemAdd,
    auth: Auth,
    session: AsyncSession = Depends(get_session),
) -> WatchlistOut:
    wl = await _watchlist_or_404(session, auth, watchlist_id)
    try:
        await watchlists.add_item(session, wl, payload.symbol)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    lists = await watchlists.list_watchlists(session, auth.user_id)
    symbols: list[str] = next((w["symbols"] for w in lists if w["id"] == wl.id), [])
    return _out(wl, symbols)


@router.patch("/{watchlist_id}/order", response_model=WatchlistOut)
async def reorder_watchlist(
    watchlist_id: uuid.UUID,
    payload: WatchlistReorder,
    auth: Auth,
    session: AsyncSession = Depends(get_session),
) -> WatchlistOut:
    wl = await _watchlist_or_404(session, auth, watchlist_id)
    try:
        symbols = await watchlists.reorder_items(session, wl, payload.symbols)
    except WatchlistError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _out(wl, symbols)


@router.delete("/{watchlist_id}/items/{symbol}", response_model=WatchlistOut)
async def remove_item(
    watchlist_id: uuid.UUID,
    symbol: str,
    auth: Auth,
    session: AsyncSession = Depends(get_session),
) -> WatchlistOut:
    wl = await _watchlist_or_404(session, auth, watchlist_id)
    try:
        await watchlists.remove_item(session, wl, symbol)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    lists = await watchlists.list_watchlists(session, auth.user_id)
    symbols: list[str] = next((w["symbols"] for w in lists if w["id"] == wl.id), [])
    return _out(wl, symbols)
