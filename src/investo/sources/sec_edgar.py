"""SEC EDGAR company-facts lookup (US-listed companies and Indian ADRs only).

Free and official, but US-scope: useful as a cross-check for US names or Indian ADRs
(INFY, WIT, HDB, IBN). Not the path for NSE/BSE-native listings.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

# SEC requires a descriptive User-Agent with contact info.
_HEADERS = {"User-Agent": "Investo MCP research tool (contact: user@example.com)"}
_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

_ticker_map: Optional[dict[str, int]] = None


def _load_ticker_map() -> dict[str, int]:
    global _ticker_map
    if _ticker_map is not None:
        return _ticker_map
    mapping: dict[str, int] = {}
    try:
        with httpx.Client(timeout=15.0, headers=_HEADERS) as client:
            resp = client.get(_TICKERS_URL)
            resp.raise_for_status()
            for row in resp.json().values():
                t = str(row.get("ticker", "")).upper()
                if t:
                    mapping[t] = int(row["cik_str"])
    except Exception:
        mapping = {}
    _ticker_map = mapping
    return mapping


def _resolve_cik(ticker_or_cik: str) -> Optional[int]:
    s = ticker_or_cik.strip().upper()
    if s.isdigit():
        return int(s)
    base = s.split(".")[0]  # strip any exchange suffix
    return _load_ticker_map().get(base)


def get_sec_facts(ticker_or_cik: str, concepts: Optional[list[str]] = None) -> dict[str, Any]:
    """Return selected US-GAAP facts (latest values) for a US-listed company/ADR."""
    cik = _resolve_cik(ticker_or_cik)
    if cik is None:
        return {"error": f"No SEC CIK found for '{ticker_or_cik}' (US-listed companies / ADRs only)."}
    wanted = concepts or ["Revenues", "NetIncomeLoss", "Assets", "Liabilities", "StockholdersEquity"]
    try:
        with httpx.Client(timeout=20.0, headers=_HEADERS) as client:
            resp = client.get(_FACTS_URL.format(cik=cik))
            resp.raise_for_status()
            facts = resp.json()
    except Exception as exc:
        return {"error": f"SEC EDGAR request failed: {exc}"}

    gaap = (facts.get("facts", {}) or {}).get("us-gaap", {})
    out: dict[str, Any] = {"cik": cik, "entity": facts.get("entityName")}
    for concept in wanted:
        node = gaap.get(concept)
        if not node:
            continue
        units = node.get("units", {})
        series = units.get("USD") or next(iter(units.values()), [])
        if series:
            latest = sorted(series, key=lambda x: x.get("end", ""))[-1]
            out[concept] = {"value": latest.get("value"), "end": latest.get("end"),
                            "form": latest.get("form")}
    return out
