"""Curated universe: Nifty 100 + existing indices/ETFs (Phase 6).

CONTRACT: the DATABASE remains the authoritative runtime universe (see
``app/core/instruments.py``). This module is desired-state INPUT to the
idempotent admin sync (``services/instrument_admin.sync_catalog``) and is
never read on the request path. Editing this list does nothing until an
operator re-runs ``POST /admin/catalog/sync``.

Membership is a **late-2025 snapshot** of the Nifty 100 (Nifty 50 + Next 50)
plus the platform's original 16 assets kept verbatim (the sync never modifies
existing rows, so entries matching present symbols are no-ops). Index
reconstitutions happen twice a year - update the list and re-sync; stale
members simply stop being ingested when marked inactive by an operator.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogEntry:
    symbol: str
    display_name: str
    sector: str
    yf_symbol: str | None = None  # default: f"{symbol}.NS"
    instrument_type: str = "equity"
    currency: str = "INR"
    country: str = "IN"
    exchange_code: str = "NSE"

    @property
    def provider_symbol(self) -> str:
        return self.yf_symbol if self.yf_symbol is not None else f"{self.symbol}.NS"


def _e(symbol: str, name: str, sector: str, **kw) -> CatalogEntry:
    return CatalogEntry(symbol=symbol, display_name=name, sector=sector, **kw)


# --- The original 16 (verbatim; already present on the production DB) --------
_ORIGINAL = (
    _e("ASIANPAINT", "Asian Paints Ltd", "Consumer Discretionary"),
    _e("BHARTIARTL", "Bharti Airtel Ltd", "Telecommunication"),
    _e("GOLD", "Gold (Nippon India ETF Gold BeES)", "Commodities",
       yf_symbol="GOLDBEES.NS", instrument_type="commodity"),
    _e("HDFCBANK", "HDFC Bank Ltd", "Financial Services"),
    _e("HINDUNILVR", "Hindustan Unilever Ltd", "FMCG"),
    _e("ICICIBANK", "ICICI Bank Ltd", "Financial Services"),
    _e("INFY", "Infosys Ltd", "Information Technology"),
    _e("ITC", "ITC Ltd", "FMCG"),
    _e("LT", "Larsen & Toubro Ltd", "Industrials"),
    _e("NIFTY50", "NIFTY 50 Index", "Index", yf_symbol="^NSEI", instrument_type="index"),
    _e("RELIANCE", "Reliance Industries Ltd", "Energy"),
    _e("SBIN", "State Bank of India", "Financial Services"),
    _e("SENSEX", "BSE Sensex Index", "Index",
       yf_symbol="^BSESN", instrument_type="index", exchange_code="BSE"),
    _e("SILVER", "Silver (Nippon India Silver ETF)", "Commodities",
       yf_symbol="SILVERBEES.NS", instrument_type="commodity"),
    _e("TATAMOTORS", "Tata Motors Passenger Vehicles", "Automobile"),
    _e("TCS", "Tata Consultancy Services Ltd", "Information Technology"),
)

# --- Nifty 50 members not in the original 16 ---------------------------------
_NIFTY50_ADD = (
    _e("ADANIENT", "Adani Enterprises Ltd", "Industrials"),
    _e("ADANIPORTS", "Adani Ports & SEZ Ltd", "Industrials"),
    _e("APOLLOHOSP", "Apollo Hospitals Enterprise Ltd", "Healthcare"),
    _e("AXISBANK", "Axis Bank Ltd", "Financial Services"),
    _e("BAJAJ-AUTO", "Bajaj Auto Ltd", "Automobile"),
    _e("BAJFINANCE", "Bajaj Finance Ltd", "Financial Services"),
    _e("BAJAJFINSV", "Bajaj Finserv Ltd", "Financial Services"),
    _e("BEL", "Bharat Electronics Ltd", "Industrials"),
    _e("CIPLA", "Cipla Ltd", "Healthcare"),
    _e("COALINDIA", "Coal India Ltd", "Energy"),
    _e("DRREDDY", "Dr Reddy's Laboratories Ltd", "Healthcare"),
    _e("EICHERMOT", "Eicher Motors Ltd", "Automobile"),
    _e("ETERNAL", "Eternal Ltd (Zomato)", "Consumer Services"),
    _e("GRASIM", "Grasim Industries Ltd", "Materials"),
    _e("HCLTECH", "HCL Technologies Ltd", "Information Technology"),
    _e("HDFCLIFE", "HDFC Life Insurance Co Ltd", "Financial Services"),
    _e("HEROMOTOCO", "Hero MotoCorp Ltd", "Automobile"),
    _e("HINDALCO", "Hindalco Industries Ltd", "Materials"),
    _e("INDUSINDBK", "IndusInd Bank Ltd", "Financial Services"),
    _e("JIOFIN", "Jio Financial Services Ltd", "Financial Services"),
    _e("JSWSTEEL", "JSW Steel Ltd", "Materials"),
    _e("KOTAKBANK", "Kotak Mahindra Bank Ltd", "Financial Services"),
    _e("M&M", "Mahindra & Mahindra Ltd", "Automobile"),
    _e("MARUTI", "Maruti Suzuki India Ltd", "Automobile"),
    _e("NESTLEIND", "Nestle India Ltd", "FMCG"),
    _e("NTPC", "NTPC Ltd", "Utilities"),
    _e("ONGC", "Oil & Natural Gas Corporation Ltd", "Energy"),
    _e("POWERGRID", "Power Grid Corporation of India Ltd", "Utilities"),
    _e("SBILIFE", "SBI Life Insurance Co Ltd", "Financial Services"),
    _e("SHRIRAMFIN", "Shriram Finance Ltd", "Financial Services"),
    _e("SUNPHARMA", "Sun Pharmaceutical Industries Ltd", "Healthcare"),
    _e("TATACONSUM", "Tata Consumer Products Ltd", "FMCG"),
    _e("TATASTEEL", "Tata Steel Ltd", "Materials"),
    _e("TECHM", "Tech Mahindra Ltd", "Information Technology"),
    _e("TITAN", "Titan Company Ltd", "Consumer Discretionary"),
    _e("TRENT", "Trent Ltd", "Consumer Discretionary"),
    _e("ULTRACEMCO", "UltraTech Cement Ltd", "Materials"),
    _e("WIPRO", "Wipro Ltd", "Information Technology"),
)

# --- Nifty Next 50 (snapshot) ------------------------------------------------
_NEXT50 = (
    _e("ABB", "ABB India Ltd", "Industrials"),
    _e("ADANIENSOL", "Adani Energy Solutions Ltd", "Utilities"),
    _e("ADANIGREEN", "Adani Green Energy Ltd", "Utilities"),
    _e("ADANIPOWER", "Adani Power Ltd", "Utilities"),
    _e("AMBUJACEM", "Ambuja Cements Ltd", "Materials"),
    _e("BAJAJHLDNG", "Bajaj Holdings & Investment Ltd", "Financial Services"),
    _e("BAJAJHFL", "Bajaj Housing Finance Ltd", "Financial Services"),
    _e("BANKBARODA", "Bank of Baroda", "Financial Services"),
    _e("BHEL", "Bharat Heavy Electricals Ltd", "Industrials"),
    _e("BOSCHLTD", "Bosch Ltd", "Automobile"),
    _e("BPCL", "Bharat Petroleum Corporation Ltd", "Energy"),
    _e("BRITANNIA", "Britannia Industries Ltd", "FMCG"),
    _e("CANBK", "Canara Bank", "Financial Services"),
    _e("CGPOWER", "CG Power & Industrial Solutions Ltd", "Industrials"),
    _e("CHOLAFIN", "Cholamandalam Investment & Finance Co Ltd", "Financial Services"),
    _e("DABUR", "Dabur India Ltd", "FMCG"),
    _e("DIVISLAB", "Divi's Laboratories Ltd", "Healthcare"),
    _e("DLF", "DLF Ltd", "Real Estate"),
    _e("DMART", "Avenue Supermarts Ltd (DMart)", "Consumer Services"),
    _e("GAIL", "GAIL (India) Ltd", "Energy"),
    _e("GODREJCP", "Godrej Consumer Products Ltd", "FMCG"),
    _e("HAVELLS", "Havells India Ltd", "Consumer Discretionary"),
    _e("HAL", "Hindustan Aeronautics Ltd", "Industrials"),
    _e("HYUNDAI", "Hyundai Motor India Ltd", "Automobile"),
    _e("ICICIGI", "ICICI Lombard General Insurance Co Ltd", "Financial Services"),
    _e("ICICIPRULI", "ICICI Prudential Life Insurance Co Ltd", "Financial Services"),
    _e("INDHOTEL", "Indian Hotels Co Ltd", "Consumer Services"),
    _e("INDIGO", "InterGlobe Aviation Ltd (IndiGo)", "Services"),
    _e("IOC", "Indian Oil Corporation Ltd", "Energy"),
    _e("IRFC", "Indian Railway Finance Corporation Ltd", "Financial Services"),
    _e("JINDALSTEL", "Jindal Steel & Power Ltd", "Materials"),
    _e("JSWENERGY", "JSW Energy Ltd", "Utilities"),
    _e("LICI", "Life Insurance Corporation of India", "Financial Services"),
    _e("LODHA", "Macrotech Developers Ltd (Lodha)", "Real Estate"),
    _e("LTIM", "LTIMindtree Ltd", "Information Technology"),
    _e("MOTHERSON", "Samvardhana Motherson International Ltd", "Automobile"),
    _e("NAUKRI", "Info Edge (India) Ltd", "Consumer Services"),
    _e("PFC", "Power Finance Corporation Ltd", "Financial Services"),
    _e("PIDILITIND", "Pidilite Industries Ltd", "Materials"),
    _e("PNB", "Punjab National Bank", "Financial Services"),
    _e("RECLTD", "REC Ltd", "Financial Services"),
    _e("SIEMENS", "Siemens Ltd", "Industrials"),
    _e("SHREECEM", "Shree Cement Ltd", "Materials"),
    _e("SWIGGY", "Swiggy Ltd", "Consumer Services"),
    _e("TATAPOWER", "Tata Power Co Ltd", "Utilities"),
    _e("TORNTPHARM", "Torrent Pharmaceuticals Ltd", "Healthcare"),
    _e("TVSMOTOR", "TVS Motor Co Ltd", "Automobile"),
    _e("UNITDSPR", "United Spirits Ltd", "FMCG"),
    _e("VBL", "Varun Beverages Ltd", "FMCG"),
    _e("VEDL", "Vedanta Ltd", "Materials"),
    _e("ZYDUSLIFE", "Zydus Lifesciences Ltd", "Healthcare"),
)

CURATED_UNIVERSE: tuple[CatalogEntry, ...] = _ORIGINAL + _NIFTY50_ADD + _NEXT50
