"""Optional API-key data sources (Finnhub / Alpha Vantage / FMP).

All functions are no-ops that return empty results when the relevant key is not configured,
so the rest of Investo works without any keys.
"""

from __future__ import annotations

from typing import Any

import httpx

from ..config import CONFIG


def finnhub_peers(symbol: str) -> list[str]:
    """Finnhub peer list (US-centric). Returns [] without a key or on error."""
    if not CONFIG.has_finnhub:
        return []
    base = symbol.split(".")[0]  # Finnhub uses bare US-style symbols
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
