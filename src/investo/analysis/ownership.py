"""Shareholding-pattern analysis: who owns the company, and which way ownership is moving.

Prefers real NSE/BSE quarterly filings (promoter / FII / DII / public + promoter pledge) via
:mod:`sources.india_holdings`, and falls back to Yahoo's coarse insider/institutional snapshot when
the exchange endpoints are unavailable or the listing isn't Indian. On top of the raw split it
generates the *smart observations* investors actually watch — "Promoter ↑", "FII reducing ⚠", "Zero
pledge ✓" — and rolls them into an ``ownership_signal`` (bullish … bearish).
"""

from __future__ import annotations

import re
from typing import Any

from ..models import (
    HolderBreakdown,
    OwnershipSignal,
    Provenance,
    ShareholdingPattern,
)
from . import evidence as ev

# QoQ moves smaller than this (in fraction points) are treated as "steady".
_STEADY_EPS = 0.002  # 0.2 percentage points


def shareholding_pattern(symbol: str, *, info: dict[str, Any] | None = None) -> ShareholdingPattern:
    """Return the shareholding pattern for ``symbol`` (exchange filings, else Yahoo)."""
    from ..sources import data

    symbol = symbol.upper()
    pattern: ShareholdingPattern | None = None
    if data.market_of_symbol(symbol) == "IN":
        try:
            from ..sources.india_holdings import fetch_shareholding
            pattern = fetch_shareholding(symbol)
        except Exception:  # noqa: BLE001 - defensive; fall back to Yahoo
            pattern = None
    if pattern is None:
        pattern = _yahoo_fallback(symbol, info)

    _annotate(pattern)
    return pattern


# --------------------------------------------------------------------------------------
# Yahoo fallback
# --------------------------------------------------------------------------------------
def _yahoo_fallback(symbol: str, info: dict[str, Any] | None) -> ShareholdingPattern:
    from ..sources import data

    if info is None:
        info = data.get_info(symbol)
    holders = data.get_holders(symbol)

    promoter = _coerce(info.get("heldPercentInsiders")) or _pct_from_holders(holders, "insider")
    institutional = _coerce(info.get("heldPercentInstitutions")) or \
        _pct_from_holders(holders, "institution")
    public = None
    if promoter is not None and institutional is not None:
        public = max(0.0, 1.0 - promoter - institutional)

    latest = HolderBreakdown(
        period="current (Yahoo)", promoter=promoter, institutional=institutional, public=public,
        provenance=Provenance(source=ev.SRC_YAHOO, detail="held-percent snapshot"),
    )
    top = holders.get("institutional_top")
    return ShareholdingPattern(
        ticker=symbol.upper(), source="yahoo", latest=latest, history=[latest],
        top_institutions=top if isinstance(top, list) else [],
        note="Granular promoter/FII/DII split and pledge/quarterly trend are unavailable from "
             "Yahoo (common for NSE/BSE); see the exchange shareholding filings for those.",
    )


# --------------------------------------------------------------------------------------
# Observations + signal + evidence
# --------------------------------------------------------------------------------------
def _annotate(pattern: ShareholdingPattern) -> None:
    latest = pattern.latest
    observations: list[str] = []
    score = 0.0

    if latest is not None:
        if latest.promoter is not None:
            observations.append(f"Promoter holding {latest.promoter:.1%}")
        if latest.promoter_pledge is not None:
            if latest.promoter_pledge <= 0.001:
                observations.append("Zero promoter pledge ✓")
                score += 1
            else:
                mark = "⚠⚠" if latest.promoter_pledge > 0.25 else "⚠"
                observations.append(f"Promoter pledge {latest.promoter_pledge:.1%} {mark}")
                score -= 2 if latest.promoter_pledge > 0.25 else 1

    # Quarter-over-quarter moves (needs at least two periods of real filings).
    if len(pattern.history) >= 2 and latest is not None:
        prev = pattern.history[1]
        for field, label, favourable_up in (
            ("promoter", "Promoter", True),
            ("fii", "FII", True),
            ("dii", "DII", True),
            ("public", "Retail/public", None),
        ):
            delta = _delta(getattr(latest, field), getattr(prev, field))
            if delta is None or abs(delta) < _STEADY_EPS:
                continue
            up = delta > 0
            if favourable_up is None:  # retail/public — rising float is mildly negative
                observations.append(f"{label} {_arrow(up)} {abs(delta) * 100:.1f}pp QoQ")
                score += -0.5 if up else 0.5
            else:
                good = up == favourable_up
                mark = "✓" if good else "⚠"
                verb = "increasing" if up else "reducing"
                observations.append(f"{label} {verb} {abs(delta) * 100:.1f}pp QoQ {mark}")
                score += 1 if good else -1

    pattern.observations = observations
    pattern.ownership_signal = _signal(score)
    pattern.evidence = _evidence(pattern)


def _signal(score: float) -> OwnershipSignal:
    if score >= 2:
        return "bullish"
    if score >= 1:
        return "positive"
    if score <= -2:
        return "bearish"
    if score <= -1:
        return "cautious"
    return "neutral"


def _evidence(pattern: ShareholdingPattern):
    latest = pattern.latest
    fields = ("promoter", "fii", "dii", "institutional", "public", "promoter_pledge")
    present = sum(getattr(latest, f) is not None for f in fields) if latest else 0
    sources = []
    if latest and latest.provenance:
        sources.append(latest.provenance)
    notes = []
    if pattern.source == "yahoo":
        notes.append("Coarse Yahoo snapshot; no FII/DII split or pledge/quarterly trend.")
    return ev.build_meta(
        sources=sources or [Provenance(source=ev.SRC_YAHOO)],
        present=present,
        expected=len(fields),
        history_years=len(pattern.history),
        target_years=4,  # ~4 quarters of filings is a solid trend
        as_of=latest.period if latest else None,
        notes=notes,
    )


# --------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------
def _delta(cur: float | None, prev: float | None) -> float | None:
    if cur is None or prev is None:
        return None
    return cur - prev


def _arrow(up: bool) -> str:
    return "↑" if up else "↓"


def _coerce(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return num / 100.0 if num > 1.0 else num


def _pct_from_holders(holders: dict[str, Any], *needles: str) -> float | None:
    mh = holders.get("major_holders")
    if not isinstance(mh, dict):
        return None
    for label, value in mh.items():
        if any(n in str(label).lower() for n in needles):
            if isinstance(value, str):
                m = re.search(r"[-+]?\d*\.?\d+", value)
                num = float(m.group()) if m else None
            elif isinstance(value, (int, float)):
                num = float(value)
            else:
                num = None
            if num is not None:
                return num / 100.0 if num > 1.0 else num
    return None
