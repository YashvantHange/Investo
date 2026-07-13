"""Provider facade — the single data entry point used by the analysis layer.

Precedence: when an API key is configured, licensed data (Alpha Vantage / FMP via
``keyed.overview_as_info``) is overlaid on top of Yahoo and *takes precedence* for the fields
it covers; otherwise Yahoo Finance is the source. This gives "keyed-primary when available,
Yahoo fallback" while keeping the tool zero-config. For NSE/BSE listings, keyed coverage is
poor, so Yahoo remains the source of record there (see README "Data sources & legal").

Analysis modules import this module (not ``yahoo`` directly) so provider policy, caching and
disclosure live in one place.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from ..config import CONFIG
from ..models import CompanyProfile
from . import keyed, yahoo

_log = logging.getLogger("investo.sources.data")

# Re-export the calls that are Yahoo-sourced regardless of keys.
search = yahoo.search
get_financials = yahoo.get_financials
fx_rate = yahoo.fx_rate
get_esg_score = yahoo.get_esg_score
get_growth_estimates = yahoo.get_growth_estimates
get_news_raw = yahoo.get_news_raw
get_holders = yahoo.get_holders
market_of_symbol = yahoo.market_of_symbol

_MERGED_TTL = 900.0
_MISSING = object()
_MERGED_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _keys_configured() -> bool:
    return CONFIG.has_alphavantage or CONFIG.has_fmp


def get_info(symbol: str) -> dict[str, Any]:
    """Yahoo info with licensed fundamentals overlaid (keyed values win) when a key is set."""
    if not _keys_configured():
        return yahoo.get_info(symbol)

    key = symbol.upper()
    entry = _MERGED_CACHE.get(key)
    if entry is not None and time.monotonic() - entry[0] <= _MERGED_TTL:
        return entry[1]

    base = dict(yahoo.get_info(symbol))
    overlay = keyed.overview_as_info(symbol)
    if overlay:
        base.update(overlay)  # licensed values take precedence for the fields they cover
        _log.info("%s: using %s fundamentals overlaid on Yahoo", symbol, overlay.get("_source", "keyed"))
    else:
        _log.debug("%s: Yahoo fundamentals (no keyed overlay)", symbol)
    _MERGED_CACHE[key] = (time.monotonic(), base)
    return base


def get_profile(symbol: str) -> CompanyProfile:
    return yahoo.profile_from_info(symbol, get_info(symbol))


def active_source(symbol: str) -> str:
    """Which source primarily backs a symbol's fundamentals (for disclosure/warnings)."""
    if _keys_configured() and "." not in symbol:
        overlay = keyed.overview_as_info(symbol)
        if overlay:
            return str(overlay.get("_source", "keyed"))
    return "yahoo"


def provider_status() -> dict[str, Any]:
    """Report which data providers are active (used by tooling / disclosure)."""
    return {
        "primary_when_available": "keyed (Alpha Vantage / FMP)" if _keys_configured() else "yahoo",
        "fallback": "yahoo",
        "alphavantage": CONFIG.has_alphavantage,
        "fmp": CONFIG.has_fmp,
        "finnhub": CONFIG.has_finnhub,
        "note": (
            "No API keys set -> using Yahoo Finance's public endpoints (best-effort, may be "
            "rate-limited). Set a key for licensed data; see README 'Data sources & legal'."
            if not _keys_configured() else
            "Licensed data overlaid on Yahoo where available; NSE/BSE fundamentals still Yahoo-sourced."
        ),
    }
