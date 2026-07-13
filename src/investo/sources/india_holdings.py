"""NSE/BSE shareholding-pattern source (India).

Fetches the quarterly promoter / FII / DII / public split (and promoter pledge, where reported)
from the exchanges' public endpoints, newest-first. Two providers are tried in order — NSE by
symbol, then BSE by scrip code — and the caller (``analysis.ownership``) falls back to Yahoo's
coarse insider/institutional split if neither responds.

Design for fragility: the exchange endpoints are undocumented, rate-limited and occasionally change
shape, so every network call is wrapped defensively (partial data or ``None``, never an exception),
and the JSON parsers are **schema-tolerant** — they locate fields by keyword rather than exact key,
and are pure functions so they can be unit-tested with recorded payloads (no live calls in CI).
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from ..config import CONFIG
from ..models import HolderBreakdown, Provenance, ShareholdingPattern
from . import ratelimit
from .india_symbols import bse_scrip_code, nse_symbol

_log = logging.getLogger("investo.sources.india_holdings")

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}
_NSE_HOME = "https://www.nseindia.com"
_NSE_API = "https://www.nseindia.com/api/corporate-shareholdings-pattern"
_BSE_API = "https://api.bseindia.com/BseIndiaAPI/api/ShareHoldingObj/w"
_BSE_REFERER = "https://www.bseindia.com/"
_TIMEOUT = 8.0


def fetch_shareholding(symbol: str) -> ShareholdingPattern | None:
    """Best-effort quarterly shareholding for an Indian symbol, or ``None`` if unavailable."""
    if not CONFIG.enable_india_holdings:
        return None

    ratelimit.wait("india_holdings", CONFIG.india_holdings_min_interval)
    nse = _try_nse(symbol)
    if nse and nse.history:
        return nse

    code = bse_scrip_code(symbol)
    if code:
        ratelimit.wait("india_holdings", CONFIG.india_holdings_min_interval)
        bse = _try_bse(symbol, code)
        if bse and bse.history:
            return bse
    return None


# --------------------------------------------------------------------------------------
# NSE (keyed by symbol; needs a primed browser session for cookies)
# --------------------------------------------------------------------------------------
def _try_nse(symbol: str) -> ShareholdingPattern | None:
    sym = nse_symbol(symbol)
    try:
        with httpx.Client(timeout=_TIMEOUT, headers=_BROWSER_HEADERS, follow_redirects=True) as client:
            client.get(_NSE_HOME)  # seed cookies
            resp = client.get(_NSE_API, params={"index": "equities", "symbol": sym})
            resp.raise_for_status()
            payload = resp.json()
    except Exception as exc:  # noqa: BLE001 - defensive: never fail the analysis over a scrape
        _log.debug("NSE shareholding fetch failed for %s: %s", sym, exc)
        return None

    history = parse_nse(payload)
    if not history:
        return None
    return ShareholdingPattern(
        ticker=symbol.upper(), source="nse", latest=history[0], history=history,
    )


def parse_nse(payload: Any) -> list[HolderBreakdown]:
    """Parse NSE's shareholding payload into newest-first breakdowns (schema-tolerant)."""
    records = _records(payload)
    out: list[HolderBreakdown] = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        period = _first_str(rec, "date", "asOnDate", "submissionDate", "xbrl", "period")
        promoter = _find_pct(rec, "promoter")
        fii = _find_pct(rec, "fii", "foreign")
        dii = _find_pct(rec, "dii", "domestic", "mutual")
        public = _find_pct(rec, "public")
        pledge = _find_pct(rec, "pledge", "encumber")
        if _all_none(promoter, fii, dii, public):
            continue
        out.append(HolderBreakdown(
            period=period or "unknown", promoter=promoter, fii=fii, dii=dii, public=public,
            promoter_pledge=pledge,
            provenance=Provenance(source="NSE Shareholding Filing", as_of=period),
        ))
    return _dedupe_by_period(out)


# --------------------------------------------------------------------------------------
# BSE (keyed by scrip code)
# --------------------------------------------------------------------------------------
def _try_bse(symbol: str, scrip_code: str) -> ShareholdingPattern | None:
    headers = {**_BROWSER_HEADERS, "Referer": _BSE_REFERER, "Origin": "https://www.bseindia.com"}
    try:
        with httpx.Client(timeout=_TIMEOUT, headers=headers, follow_redirects=True) as client:
            resp = client.get(_BSE_API, params={"scripcode": scrip_code, "flag": "", "qtrid": ""})
            resp.raise_for_status()
            payload = resp.json()
    except Exception as exc:  # noqa: BLE001
        _log.debug("BSE shareholding fetch failed for %s (%s): %s", symbol, scrip_code, exc)
        return None

    history = parse_bse(payload)
    if not history:
        return None
    return ShareholdingPattern(
        ticker=symbol.upper(), source="bse", latest=history[0], history=history,
    )


def parse_bse(payload: Any) -> list[HolderBreakdown]:
    """Parse BSE's shareholding payload into newest-first breakdowns (schema-tolerant)."""
    records = _records(payload)
    out: list[HolderBreakdown] = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        period = _first_str(rec, "QTR_ID", "Qtr", "quarter", "date", "AsOnDate")
        promoter = _find_pct(rec, "promoter", "prom")
        fii = _find_pct(rec, "fii", "foreign")
        dii = _find_pct(rec, "dii", "institution", "mutual")
        public = _find_pct(rec, "public", "nonprom")
        pledge = _find_pct(rec, "pledge", "encumber")
        if _all_none(promoter, fii, dii, public):
            continue
        out.append(HolderBreakdown(
            period=period or "unknown", promoter=promoter, fii=fii, dii=dii, public=public,
            promoter_pledge=pledge,
            provenance=Provenance(source="BSE Shareholding Filing", as_of=period),
        ))
    return _dedupe_by_period(out)


# --------------------------------------------------------------------------------------
# Shared parsing helpers (schema-tolerant)
# --------------------------------------------------------------------------------------
def _records(payload: Any) -> list[Any]:
    """Pull the list of quarterly records out of a variety of envelope shapes."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "records", "Table", "shareHoldings", "result"):
            val = payload.get(key)
            if isinstance(val, list):
                return val
        # Single record dict.
        return [payload]
    return []


def _find_pct(rec: dict[str, Any], *needles: str) -> float | None:
    """First numeric field whose key contains any needle, coerced to a 0-1 fraction."""
    for key, value in rec.items():
        low = str(key).lower()
        if any(n in low for n in needles):
            pct = _to_pct(value)
            if pct is not None:
                return pct
    return None


def _to_pct(value: Any) -> float | None:
    """Coerce a percentage-ish value to a 0-1 fraction (accepts 50.3, '50.3', '50.3%')."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        num: float | None = float(value)
    elif isinstance(value, str):
        m = re.search(r"[-+]?\d*\.?\d+", value)
        num = float(m.group()) if m else None
    else:
        num = None
    if num is None:
        return None
    return num / 100.0 if num > 1.0 else num


def _first_str(rec: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        for actual, value in rec.items():
            if str(actual).lower() == key.lower() and value:
                return str(value)
    return None


def _all_none(*vals: float | None) -> bool:
    return all(v is None for v in vals)


def _dedupe_by_period(rows: list[HolderBreakdown]) -> list[HolderBreakdown]:
    """Keep one row per period, newest-first (assumes input is roughly newest-first already)."""
    seen: set[str] = set()
    out: list[HolderBreakdown] = []
    for r in rows:
        if r.period not in seen:
            seen.add(r.period)
            out.append(r)
    return out
