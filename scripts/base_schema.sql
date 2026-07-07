-- ============================================================================
-- Base schema bootstrap (audit MED-8 / TD-8)
--
-- The production Supabase database inherited these tables from a prior
-- repository's migrations (0001..0004_warehouse), which are not vendored here.
-- This script creates the MINIMAL, app-compatible subset of that base schema
-- so a fresh Postgres (CI service container, local docker-compose) can run
-- `alembic upgrade head` and the full application.
--
-- It is intentionally idempotent (IF NOT EXISTS everywhere) and must NEVER be
-- run against the production database.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS vector;

DO $$ BEGIN
    CREATE TYPE instrument_type AS ENUM
        ('equity','index','commodity','etf','bond','mutual_fund','forex','crypto','future','option');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE instrument_status AS ENUM ('active','delisted','suspended');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE market_cap_category AS ENUM
        ('mega_cap','large_cap','mid_cap','small_cap','micro_cap');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE timeframe AS ENUM ('daily','weekly','monthly');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS exchanges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    code VARCHAR NOT NULL UNIQUE,
    name VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS instruments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    symbol VARCHAR NOT NULL UNIQUE,
    display_name VARCHAR NOT NULL,
    isin VARCHAR,
    instrument_type instrument_type NOT NULL,
    exchange_id UUID NOT NULL REFERENCES exchanges (id),
    sector_id UUID,
    industry_id UUID,
    market_cap_category market_cap_category,
    currency VARCHAR NOT NULL,
    country VARCHAR NOT NULL,
    listing_date DATE,
    status instrument_status NOT NULL DEFAULT 'active',
    last_metadata_update TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS data_providers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    code VARCHAR NOT NULL UNIQUE,
    name VARCHAR NOT NULL,
    base_url VARCHAR,
    is_active BOOLEAN DEFAULT TRUE,
    priority INTEGER DEFAULT 100
);

CREATE TABLE IF NOT EXISTS instrument_provider_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    instrument_id UUID NOT NULL REFERENCES instruments (id),
    provider_id UUID NOT NULL REFERENCES data_providers (id),
    provider_symbol VARCHAR NOT NULL,
    is_primary BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    CONSTRAINT uq_mapping_instrument_provider UNIQUE (instrument_id, provider_id)
);

CREATE TABLE IF NOT EXISTS price_bars (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    instrument_id UUID NOT NULL REFERENCES instruments (id),
    provider_id UUID NOT NULL REFERENCES data_providers (id),
    date DATE NOT NULL,
    timeframe timeframe NOT NULL DEFAULT 'daily',
    open NUMERIC NOT NULL,
    high NUMERIC NOT NULL,
    low NUMERIC NOT NULL,
    close NUMERIC NOT NULL,
    adj_close NUMERIC,
    volume BIGINT NOT NULL,
    currency VARCHAR NOT NULL,
    is_adjusted BOOLEAN NOT NULL DEFAULT FALSE,
    provider_version VARCHAR,
    source_timestamp TIMESTAMPTZ,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ingestion_job_id UUID,
    CONSTRAINT uq_price_bars_instrument_provider_date_timeframe
        UNIQUE (instrument_id, provider_id, date, timeframe)
);

CREATE TABLE IF NOT EXISTS agent_embeddings (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_table VARCHAR NOT NULL,
    source_id VARCHAR NOT NULL,
    content_hash VARCHAR NOT NULL,
    embedding vector(384) NOT NULL
);
