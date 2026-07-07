"""Async SQLAlchemy engine, session factory, and declarative Base.

The engine is created lazily so the app / test process can import models
without a live database. Call :func:`get_session` (FastAPI dependency) to obtain
a session, and :func:`dispose_engine` on shutdown.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _looks_like_pooler(url: str) -> bool:
    """Heuristic: Supabase/PgBouncer transaction-mode pooler endpoints."""
    lowered = url.lower()
    return ":6543" in lowered or "pooler." in lowered or "pgbouncer" in lowered


def _connect_args(url: str) -> dict:
    """asyncpg connect args, pooler-safe (audit HIGH-6).

    PgBouncer in transaction mode breaks asyncpg's named prepared statements;
    disable the statement cache automatically for pooler-looking URLs, or
    explicitly via DB_STATEMENT_CACHE_SIZE.
    """
    settings = get_settings()
    size = settings.db_statement_cache_size
    if size is None:
        size = 0 if _looks_like_pooler(url) else None
    if size is None:
        return {}
    return {"statement_cache_size": size}


def get_engine() -> AsyncEngine:
    """Return the process-wide async engine, creating it on first use."""
    global _engine, _sessionmaker
    if _engine is None:
        settings = get_settings()
        if not settings.database_configured:
            raise RuntimeError(
                "DATABASE_URL is not configured. Copy .env.example to .env and set it."
            )
        url = settings.async_database_url
        _engine = create_async_engine(
            url,
            pool_pre_ping=True,
            future=True,
            connect_args=_connect_args(url),
        )
        _sessionmaker = async_sessionmaker(
            _engine, expire_on_commit=False, class_=AsyncSession
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the session factory, initialising the engine if needed."""
    if _sessionmaker is None:
        get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a database session."""
    sm = get_sessionmaker()
    async with sm() as session:
        yield session


async def dispose_engine() -> None:
    """Dispose the engine (call on application shutdown).

    Globals are cleared FIRST so a failed cross-event-loop disposal (as seen in
    per-test loops under pytest-asyncio) can never leave a stale engine behind.
    """
    global _engine, _sessionmaker
    engine = _engine
    _engine = None
    _sessionmaker = None
    if engine is not None:
        await engine.dispose()
