"""Catalog-sync database-integration tests (Phase 6).

Uses a tiny TEST-ONLY entry tuple - the real CURATED_UNIVERSE is never synced
here (that happens once in production via POST /admin/catalog/sync). Created
rows are removed afterwards.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from app.catalog.curated import CatalogEntry
from app.core.config import get_settings
from app.db.base import dispose_engine, get_sessionmaker
from app.models.instrument import Instrument
from app.models.provider import InstrumentProviderMapping
from app.services import instrument_admin
from sqlalchemy import delete, select

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(
        not get_settings().database_configured,
        reason="DATABASE_URL not configured; integration tests run in CI",
    ),
]

TEST_ENTRIES = (
    CatalogEntry(symbol="TESTCAT1", display_name="Test Catalog One",
                 sector="Testing", yf_symbol="TESTCAT1.NS"),
    CatalogEntry(symbol="TESTCAT2", display_name="Test Catalog Two",
                 sector="Testing", yf_symbol="TESTCAT2.NS"),
)


@pytest_asyncio.fixture(autouse=True)
async def _fresh_engine():
    import contextlib

    with contextlib.suppress(Exception):
        await dispose_engine()
    yield
    with contextlib.suppress(Exception):
        await dispose_engine()


@pytest_asyncio.fixture()
async def session():
    sm = get_sessionmaker()
    async with sm() as s:
        yield s
        # Cleanup: mappings first (FK), then instruments.
        ids = (
            (
                await s.execute(
                    select(Instrument.id).where(Instrument.symbol.like("TESTCAT%"))
                )
            )
            .scalars()
            .all()
        )
        if ids:
            await s.execute(
                delete(InstrumentProviderMapping).where(
                    InstrumentProviderMapping.instrument_id.in_(ids)
                )
            )
            await s.execute(delete(Instrument).where(Instrument.id.in_(ids)))
            await s.commit()


@pytest.mark.asyncio
async def test_sync_creates_then_noops(session):
    plan = await instrument_admin.plan_catalog(session, TEST_ENTRIES)
    assert plan["catalog_size"] == 2
    assert set(plan["missing"]) == {"TESTCAT1", "TESTCAT2"}

    first = await instrument_admin.sync_catalog(session, TEST_ENTRIES)
    assert first.instruments_created == 2
    assert first.mappings_created == 2
    assert first.errors == []
    assert set(first.created_symbols) == {"TESTCAT1", "TESTCAT2"}

    # Instruments + mappings actually landed with the right provider symbol.
    inst = (
        await session.execute(select(Instrument).where(Instrument.symbol == "TESTCAT1"))
    ).scalar_one()
    assert inst.status == "active"
    mapping = (
        await session.execute(
            select(InstrumentProviderMapping).where(
                InstrumentProviderMapping.instrument_id == inst.id
            )
        )
    ).scalar_one()
    assert mapping.provider_symbol == "TESTCAT1.NS"

    # Re-run: pure no-op.
    second = await instrument_admin.sync_catalog(session, TEST_ENTRIES)
    assert second.instruments_created == 0
    assert second.mappings_created == 0
    assert second.already_present == 2

    plan_after = await instrument_admin.plan_catalog(session, TEST_ENTRIES)
    assert plan_after["missing"] == []


@pytest.mark.asyncio
async def test_sync_never_modifies_existing_rows(session):
    first = await instrument_admin.sync_catalog(session, TEST_ENTRIES)
    assert first.errors == []
    renamed = (
        CatalogEntry(symbol="TESTCAT1", display_name="RENAMED SHOULD NOT APPLY",
                     sector="Testing", yf_symbol="CHANGED.NS"),
    ) + TEST_ENTRIES[1:]
    await instrument_admin.sync_catalog(session, renamed)
    inst = (
        await session.execute(select(Instrument).where(Instrument.symbol == "TESTCAT1"))
    ).scalar_one()
    assert inst.display_name == "Test Catalog One"  # untouched
    mapping = (
        await session.execute(
            select(InstrumentProviderMapping).where(
                InstrumentProviderMapping.instrument_id == inst.id
            )
        )
    ).scalar_one()
    assert mapping.provider_symbol == "TESTCAT1.NS"  # untouched
