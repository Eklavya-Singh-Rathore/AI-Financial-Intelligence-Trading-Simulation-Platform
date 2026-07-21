"""Watchlist API schemas (Phase 6)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WatchlistCreate(BaseModel):
    name: str = Field(default="Watchlist", min_length=1, max_length=64)


class WatchlistUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class WatchlistItemAdd(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)


class WatchlistReorder(BaseModel):
    # The list's members in their new order; must be exactly the current members.
    symbols: list[str] = Field(min_length=1, max_length=500)


class WatchlistOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    created_at: datetime
    symbols: list[str] = []
