"""Resolve a free-text company name (or a raw ticker) to an exchange ticker.

India-first: when the market is 'IN' (the default), NSE (``.NS``) symbols are preferred,
then BSE (``.BO``). Ranking is driven primarily by *name relevance* (so "Infosys" does not
match "HCL Infosystems"), then by the market preference, then Yahoo's own score.

If the best match for an India query is a foreign ADR (e.g. Yahoo returns the US-listed
``INFY`` for "Infosys" but not ``INFY.NS``), we probe the base symbol on NSE/BSE to recover
the local INR listing.
"""

from __future__ import annotations

import re
from typing import Optional

from .models import SearchResult, TickerCandidate
from .sources import yahoo

# A bare ticker already carrying an exchange suffix, e.g. INFY.NS / TATAMOTORS.BO
_SUFFIXED_TICKER = re.compile(r"^[A-Za-z0-9&-]{1,15}\.[A-Za-z]{1,3}$")

# Corporate-form words ignored when comparing names.
_STOP_WORDS = {
    "ltd", "limited", "inc", "incorporated", "corp", "corporation", "plc", "co",
    "company", "the", "group", "holdings", "holding", "sa", "ag", "nv", "and",
}


def _norm_tokens(text: Optional[str]) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [t for t in tokens if t not in _STOP_WORDS]


def _relevance_tier(query: str, candidate: TickerCandidate) -> int:
    """0 = best (exact), 3 = worst (no meaningful overlap)."""
    qt = _norm_tokens(query)
    if not qt:
        return 3
    nt = _norm_tokens(candidate.name)
    qset, nset = set(qt), set(nt)

    if qt == nt:
        return 0
    base_sym = (candidate.symbol or "").upper().split(".")[0]
    if base_sym and base_sym == "".join(qt).upper():
        return 0
    if qset and qset.issubset(nset):
        return 1
    overlap = len(qset & nset)
    if overlap >= max(1, len(qset) - 1):
        return 2
    if overlap:
        return 2
    return 3


def _market_rank(candidate: TickerCandidate, market: str) -> int:
    """Lower is better. Encodes the exchange preference for the requested market."""
    sym = (candidate.symbol or "").upper()
    if market == "IN":
        if sym.endswith(".NS"):
            return 0
        if sym.endswith(".BO"):
            return 1
        if candidate.market == "IN":
            return 2
        return 5
    if market == "US":
        return 0 if candidate.market == "US" else 4
    return 3


def _quote_type_rank(candidate: TickerCandidate) -> int:
    qt = (candidate.quote_type or "").upper()
    return 0 if qt in {"EQUITY", ""} else 1  # prefer equities over ETFs/indices/futures


def rank_candidates(candidates: list[TickerCandidate], market: str, query: str) -> list[TickerCandidate]:
    """Sort candidates best-first for the requested market and query."""
    return sorted(
        candidates,
        key=lambda c: (
            _relevance_tier(query, c),
            _market_rank(c, market),
            _quote_type_rank(c),
            -(c.score or 0.0),
        ),
    )


def _valid_listing(symbol: str) -> Optional[str]:
    """Return the company name if *symbol* looks like a real, priced listing, else None."""
    info = yahoo.get_info(symbol)
    name = info.get("longName") or info.get("shortName")
    priced = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("sector")
    return name if (name and priced) else None


def _probe_local_listing(base_symbol: str) -> Optional[TickerCandidate]:
    """Try to find an NSE/BSE listing for a base symbol (e.g. 'INFY' -> 'INFY.NS')."""
    base = base_symbol.upper().split(".")[0]
    for suffix in (".NS", ".BO"):
        sym = base + suffix
        name = _valid_listing(sym)
        if name:
            return TickerCandidate(symbol=sym, name=name, market="IN", quote_type="EQUITY")
    return None


def resolve(query: str, market: str = "IN") -> SearchResult:
    """Resolve *query* to a best ticker + ranked alternatives."""
    market = (market or "IN").upper()
    q = query.strip()

    # 1) Already a suffixed ticker -> accept directly (still search for alternatives).
    if _SUFFIXED_TICKER.match(q):
        resolved = TickerCandidate(symbol=q.upper(), market=yahoo.market_of_symbol(q))
        alts = rank_candidates(yahoo.search(q, limit=10), market, query)
        return SearchResult(query=query, resolved=resolved, candidates=alts or [resolved])

    # 2) Search Yahoo and rank by relevance + market preference.
    candidates = yahoo.search(q, limit=10)
    if not candidates:
        return SearchResult(
            query=query,
            resolved=None,
            candidates=[],
            note="No matches found. Try a ticker like INFY.NS (NSE) or RELIANCE.BO (BSE).",
        )

    ranked = rank_candidates(candidates, market, query)
    resolved = ranked[0]
    note = None

    # 3) India-first recovery: best match is a good name but a foreign listing -> probe NSE/BSE.
    if market == "IN" and resolved.market != "IN" and _relevance_tier(query, resolved) <= 1:
        local = _probe_local_listing(resolved.symbol)
        if local is not None:
            note = f"Recovered NSE/BSE listing {local.symbol} for the {resolved.symbol} ADR."
            resolved = local
            ranked = [local] + ranked
        else:
            note = "No NSE/BSE listing found; using the best global match."

    return SearchResult(query=query, resolved=resolved, candidates=ranked, note=note)


def resolve_ticker(query: str, market: str = "IN") -> Optional[str]:
    """Convenience: return just the resolved symbol string (or None)."""
    result = resolve(query, market)
    return result.resolved.symbol if result.resolved else None
