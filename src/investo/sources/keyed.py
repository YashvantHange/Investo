"""Optional API-key data sources (Finnhub / Alpha Vantage / FMP).

All functions are no-ops that return empty results when the relevant key is not configured,
so the rest of Investo works without any keys.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..config import CONFIG
from . import ratelimit

_log = logging.getLogger("investo.sources.keyed")


def finnhub_peers(symbol: str) -> list[str]:
    """Finnhub peer list (US-centric). Returns [] without a key or on error."""
    if not CONFIG.has_finnhub:
        return []
    base = symbol.split(".")[0]  # Finnhub uses bare US-style symbols
    ratelimit.wait("finnhub", CONFIG.finnhub_min_interval)
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                "https://finnhub.io/api/v1/stock/peers",
                params={"symbol": base, "token": CONFIG.finnhub_key},
            )
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else []
    except Exception:
        return []


def alphavantage_overview(symbol: str) -> dict[str, Any]:
    """Alpha Vantage company overview (fundamentals). Empty without a key."""
    if not CONFIG.has_alphavantage:
        return {}
    if not ratelimit.allow_daily("alphavantage", CONFIG.av_daily_cap):
        _log.warning("Alpha Vantage daily cap (%d) reached; falling back to Yahoo.", CONFIG.av_daily_cap)
        return {}
    ratelimit.wait("alphavantage", CONFIG.av_min_interval)
    base = symbol.split(".")[0]
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(
                "https://www.alphavantage.co/query",
                params={"function": "OVERVIEW", "symbol": base, "apikey": CONFIG.alphavantage_key},
            )
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) and data.get("Symbol") else {}
    except Exception:
        return {}


def fmp_profile(symbol: str) -> dict[str, Any]:
    """Financial Modeling Prep company profile. Empty without a key."""
    if not CONFIG.has_fmp:
        return {}
    ratelimit.wait("fmp", CONFIG.fmp_min_interval)
    base = symbol.split(".")[0]
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(
                f"https://financialmodelingprep.com/api/v3/profile/{base}",
                params={"apikey": CONFIG.fmp_key},
            )
            resp.raise_for_status()
            data = resp.json()
            return data[0] if isinstance(data, list) and data else {}
    except Exception:
        return {}


def _f(value: Any) -> Any:
    """Coerce Alpha Vantage/FMP string numerics to float; drop 'None'/'-'/'' placeholders."""
    if value in (None, "None", "-", "", "NaN"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return value  # keep genuine strings (e.g. names)


def overview_as_info(symbol: str) -> dict[str, Any]:
    """Return licensed fundamentals mapped to Yahoo-style ``info`` keys, or {} if unavailable.

    Used as the *primary* overlay for a symbol when an API key is configured: values here
    take precedence over Yahoo's for the fields they cover. Restricted to US-style symbols
    (no exchange suffix); NSE/BSE fundamentals coverage on these APIs is poor, so Yahoo remains
    the source of record for Indian listings.
    """
    if "." in symbol:  # exchange-suffixed (e.g. .NS/.BO) -> keyed coverage unreliable
        return {}

    av = alphavantage_overview(symbol)
    if av:
        return {k: v for k, v in {
            "longName": av.get("Name"),
            "sector": (av.get("Sector") or "").title() or None,
            "industry": av.get("Industry"),
            "longBusinessSummary": av.get("Description"),
            "country": av.get("Country"),
            "currency": av.get("Currency"),
            "financialCurrency": av.get("Currency"),
            "marketCap": _f(av.get("MarketCapitalization")),
            "trailingPE": _f(av.get("PERatio")),
            "forwardPE": _f(av.get("ForwardPE")),
            "priceToBook": _f(av.get("PriceToBookRatio")),
            "priceToSalesTrailing12Months": _f(av.get("PriceToSalesRatioTTM")),
            "enterpriseToEbitda": _f(av.get("EVToEBITDA")),
            "returnOnEquity": _f(av.get("ReturnOnEquityTTM")),
            "returnOnAssets": _f(av.get("ReturnOnAssetsTTM")),
            "profitMargins": _f(av.get("ProfitMargin")),
            "operatingMargins": _f(av.get("OperatingMarginTTM")),
            "dividendYield": _f(av.get("DividendYield")),
            "beta": _f(av.get("Beta")),
            "totalRevenue": _f(av.get("RevenueTTM")),
            "revenueGrowth": _f(av.get("QuarterlyRevenueGrowthYOY")),
            "earningsGrowth": _f(av.get("QuarterlyEarningsGrowthYOY")),
            "_source": "alphavantage",
        }.items() if v is not None}

    fmp = fmp_profile(symbol)
    if fmp:
        return {k: v for k, v in {
            "longName": fmp.get("companyName"),
            "sector": fmp.get("sector"),
            "industry": fmp.get("industry"),
            "longBusinessSummary": fmp.get("description"),
            "country": fmp.get("country"),
            "currency": fmp.get("currency"),
            "website": fmp.get("website"),
            "marketCap": _f(fmp.get("mktCap")),
            "currentPrice": _f(fmp.get("price")),
            "beta": _f(fmp.get("beta")),
            "fullTimeEmployees": _f(fmp.get("fullTimeEmployees")),
            "_source": "fmp",
        }.items() if v is not None}

    return {}
