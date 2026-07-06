"""ORM models package.

Importing this package registers every model on the declarative ``Base``
metadata. Existing tables (instruments, price_bars, data_providers,
instrument_provider_mappings) are mapped read/mixed; forecasts and backtests are
new tables owned by this project.
"""

from app.models.backtest import Backtest
from app.models.forecast import Forecast
from app.models.instrument import Instrument
from app.models.price_bar import PriceBar
from app.models.provider import DataProvider, InstrumentProviderMapping

__all__ = [
    "Instrument",
    "PriceBar",
    "DataProvider",
    "InstrumentProviderMapping",
    "Forecast",
    "Backtest",
]
