"""Head-to-head comparison across an arbitrary set of tickers.

Unlike ``compare_peers``, which works from a curated group, this compares exactly the tickers the
caller names — answering "compare KPIT with Tata Elxsi and Tata Tech" directly. It reuses
``peers._peer_row`` (same currency normalisation) and the same concurrent fetch.

It deliberately does **not** compute a "market share": revenue share within a set the user invented
is not market share, and calling it that would mislead. The share it does report is named
``revenue_share_of_set`` in prose and is explicitly set-relative.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from ..models import MultiCompare, PeerRow, Provenance
from ..sources import data
from . import evidence as ev
from .peers import _peer_row


def compare_companies(symbols: list[str]) -> MultiCompare:
    """Compare 2-6 tickers side by side (already-resolved exchange tickers)."""
    # De-duplicate, preserving the caller's order.
    seen: set[str] = set()
    ordered: list[str] = []
    for s in symbols:
        u = s.upper()
        if u not in seen:
            seen.add(u)
            ordered.append(u)

    if len(ordered) < 2:
        return MultiCompare(tickers=ordered,
                            note="Need at least two distinct tickers to compare.")

    base_ccy = data.get_info(ordered[0]).get("currency") or \
        data.get_info(ordered[0]).get("financialCurrency")
    with ThreadPoolExecutor(max_workers=8) as pool:
        fetched = list(pool.map(lambda sym: _peer_row(sym, base_ccy), ordered))
    rows: list[PeerRow] = [r for r in fetched if r is not None]

    if not rows:
        return MultiCompare(tickers=ordered, note="None of the tickers resolved to usable data.")

    total_rev = sum(r.revenue_ttm for r in rows if r.revenue_ttm is not None)
    if total_rev > 0:
        for r in rows:
            if r.revenue_ttm is not None:
                r.market_share_proxy = r.revenue_ttm / total_rev  # set-relative; see _summary

    present = sum(1 for r in rows if r.revenue_ttm is not None or r.market_cap is not None)
    return MultiCompare(
        tickers=ordered,
        rows=rows,
        summary=_summary(rows),
        note="Revenue & market cap normalized to the first ticker's trading currency. "
             "Shares are within this set, not market share.",
        evidence=ev.build_meta(
            sources=[Provenance(source=ev.SRC_YAHOO, detail="peer fundamentals")],
            present=present, expected=len(rows),
            notes=[f"Comparing {len(rows)} of {len(ordered)} requested tickers."]),
    )


def _summary(rows: list[PeerRow]) -> list[str]:
    """A few grounded leaders across the set — no subject, so no rank-of-self."""
    out: list[str] = []

    def leader(attr: str, label: str, fmt, reverse: bool = True) -> None:
        vals = [(r, getattr(r, attr)) for r in rows if getattr(r, attr) is not None]
        if not vals:
            return
        best = sorted(vals, key=lambda x: x[1], reverse=reverse)[0][0]
        out.append(f"{label}: {best.name or best.ticker} ({fmt(getattr(best, attr))}).")

    leader("market_cap", "Largest", lambda v: _money(v))
    leader("net_margin", "Highest net margin", lambda v: f"{v:.1%}")
    leader("revenue_growth_yoy", "Fastest growth", lambda v: f"{v:.1%}")
    leader("pe", "Cheapest P/E", lambda v: f"{v:.1f}x", reverse=False)
    leader("roe", "Best ROE", lambda v: f"{v:.1%}")
    return out


def _money(value: float) -> str:
    if abs(value) >= 1e9:
        return f"{value / 1e9:,.1f}B"
    if abs(value) >= 1e7:
        return f"{value / 1e7:,.0f} Cr"
    return f"{value:,.0f}"
