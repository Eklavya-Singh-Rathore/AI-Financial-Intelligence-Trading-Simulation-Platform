"""Instrument-catalog administration (Phase 6).

``sync_catalog`` reconciles the curated desired-state list into the warehouse
tables (exchanges / data_providers / instruments / instrument_provider_mappings)
idempotently: select-or-insert everything, NEVER modify existing rows, one
transaction, single-flight via a Postgres advisory lock. Safe on both Supabase
(rows mostly pre-exist) and CI's vanilla Postgres (empty schema).

Sector links are best-effort: the warehouse ``sectors`` table is not part of
``scripts/base_schema.sql``, so its presence is probed with ``to_regclass``
first (no failed-transaction poisoning); when absent, instruments are created
with ``sector_id = NULL``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.curated import CURATED_UNIVERSE, CatalogEntry
from app.core.instruments import YFINANCE_PROVIDER_CODE
from app.models.instrument import Instrument
from app.models.provider import DataProvider, InstrumentProviderMapping

log = structlog.get_logger(__name__)

CATALOG_SYNC_LOCK_KEY = 815_005

_EXCHANGES = {
    "NSE": ("National Stock Exchange of India", "IN", "Asia/Kolkata", "INR"),
    "BSE": ("BSE Ltd (Bombay Stock Exchange)", "IN", "Asia/Kolkata", "INR"),
}


@dataclass
class CatalogSyncSummary:
    instruments_created: int = 0
    already_present: int = 0
    mappings_created: int = 0
    sectors_linked: int = 0
    created_symbols: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


async def _sectors_table_exists(session: AsyncSession) -> bool:
    result = await session.execute(text("SELECT to_regclass('public.sectors')"))
    return result.scalar() is not None


async def _sector_id_map(session: AsyncSession) -> dict[str, uuid.UUID]:
    rows = (await session.execute(text("SELECT id, name FROM sectors"))).all()
    return {name: sid for sid, name in rows}


async def _get_or_create_exchange(session: AsyncSession, code: str) -> uuid.UUID:
    row = (
        await session.execute(text("SELECT id FROM exchanges WHERE code = :c"), {"c": code})
    ).scalar_one_or_none()
    if row is not None:
        return row
    name, country, tz, currency = _EXCHANGES.get(code, (code, "IN", "Asia/Kolkata", "INR"))
    new_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO exchanges (id, code, name, country, timezone, currency) "
            "VALUES (:id, :code, :name, :country, :tz, :currency)"
        ),
        {"id": str(new_id), "code": code, "name": name, "country": country,
         "tz": tz, "currency": currency},
    )
    return new_id


async def _get_or_create_provider(session: AsyncSession) -> uuid.UUID:
    row = (
        await session.execute(
            select(DataProvider.id).where(DataProvider.code == YFINANCE_PROVIDER_CODE)
        )
    ).scalar_one_or_none()
    if row is not None:
        return row
    new_id = uuid.uuid4()
    await session.execute(
        text("INSERT INTO data_providers (id, code, name) VALUES (:id, :code, :name)"),
        {"id": str(new_id), "code": YFINANCE_PROVIDER_CODE, "name": "Yahoo Finance"},
    )
    return new_id


async def plan_catalog(
    session: AsyncSession, entries: tuple[CatalogEntry, ...] = CURATED_UNIVERSE
) -> dict:
    """Dry-run diff: which catalog symbols are missing from the DB (no writes)."""
    existing = set(
        (
            await session.execute(
                select(Instrument.symbol).where(
                    Instrument.symbol.in_([e.symbol for e in entries])
                )
            )
        ).scalars()
    )
    missing = [e.symbol for e in entries if e.symbol not in existing]
    return {
        "catalog_size": len(entries),
        "already_present": len(existing),
        "missing": missing,
    }


async def sync_catalog(
    session: AsyncSession, entries: tuple[CatalogEntry, ...] = CURATED_UNIVERSE
) -> CatalogSyncSummary:
    """Idempotently reconcile the catalog into the DB. Never modifies existing rows.

    Commits per entry (idempotence makes that harmless) so one bad entry
    cannot poison the session for the rest; the session-level advisory lock
    survives those commits and keeps concurrent syncs single-flight.
    """
    summary = CatalogSyncSummary()
    got_lock = (
        await session.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": CATALOG_SYNC_LOCK_KEY}
        )
    ).scalar()
    if not got_lock:
        summary.errors.append("another catalog sync is in progress")
        return summary

    try:
        # Durable setup first: provider + sector map (committed before entries).
        provider_id = await _get_or_create_provider(session)
        sectors: dict[str, uuid.UUID] = {}
        if await _sectors_table_exists(session):
            sectors = await _sector_id_map(session)
        await session.commit()

        existing_by_symbol = {
            i.symbol: i
            for i in (
                await session.execute(
                    select(Instrument).where(
                        Instrument.symbol.in_([e.symbol for e in entries])
                    )
                )
            ).scalars()
        }
        mapped_instrument_ids = set(
            (
                await session.execute(
                    select(InstrumentProviderMapping.instrument_id).where(
                        InstrumentProviderMapping.provider_id == provider_id
                    )
                )
            ).scalars()
        )

        for entry in entries:
            try:
                instrument = existing_by_symbol.get(entry.symbol)
                if instrument is None:
                    exchange_id = await _get_or_create_exchange(session, entry.exchange_code)
                    sector_id = sectors.get(entry.sector)
                    # created_at/updated_at are mapped without defaults (read-only
                    # warehouse model) - set explicitly or the flush sends NULL.
                    now = datetime.now(UTC)
                    instrument = Instrument(
                        id=uuid.uuid4(),
                        symbol=entry.symbol,
                        display_name=entry.display_name,
                        instrument_type=entry.instrument_type,
                        exchange_id=exchange_id,
                        sector_id=sector_id,
                        industry_id=None,
                        currency=entry.currency,
                        country=entry.country,
                        status="active",
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(instrument)
                    await session.flush()
                    created = True
                else:
                    created = False

                added_mapping = False
                if instrument.id not in mapped_instrument_ids:
                    now = datetime.now(UTC)
                    session.add(
                        InstrumentProviderMapping(
                            id=uuid.uuid4(),
                            instrument_id=instrument.id,
                            provider_id=provider_id,
                            provider_symbol=entry.provider_symbol,
                            is_primary=True,
                            is_active=True,
                            created_at=now,
                            updated_at=now,
                        )
                    )
                    added_mapping = True

                await session.commit()

                # Book-keep only after the commit succeeds.
                if created:
                    summary.instruments_created += 1
                    summary.created_symbols.append(entry.symbol)
                    if instrument.sector_id is not None:
                        summary.sectors_linked += 1
                else:
                    summary.already_present += 1
                if added_mapping:
                    mapped_instrument_ids.add(instrument.id)
                    summary.mappings_created += 1
            except Exception as exc:  # noqa: BLE001 - per-entry isolation
                await session.rollback()
                summary.errors.append(f"{entry.symbol}: {str(exc)[:120]}")
                log.warning(
                    "catalog_sync_entry_failed", symbol=entry.symbol, error=str(exc)[:200]
                )
    finally:
        await session.execute(
            text("SELECT pg_advisory_unlock(:key)"), {"key": CATALOG_SYNC_LOCK_KEY}
        )

    log.info(
        "catalog_sync_done",
        created=summary.instruments_created,
        present=summary.already_present,
        mappings=summary.mappings_created,
        errors=len(summary.errors),
    )
    return summary
