"""Domain constants for the instrument universe.

The authoritative instrument universe lives in the **database** (the pre-existing
``instruments`` table, already seeded with 16 assets, mapped to provider symbols
via ``instrument_provider_mappings``). This module only holds stable domain
constants used when resolving provider symbols and writing price bars. Do not
hard-code the universe here - always read it from the database.
"""

from __future__ import annotations

# data_providers.code for the primary market-data source used for ingestion.
YFINANCE_PROVIDER_CODE = "yfinance"

# Default bar timeframe (must be a label of the DB ``timeframe`` enum).
DEFAULT_TIMEFRAME = "daily"

# Default currency for the Indian-market universe.
DEFAULT_CURRENCY = "INR"
