"""Relative-to-industry comparison.

Absolute ratios only say so much — "ROE 24%" means more when the peer median is 17%. This module
reuses the peer set already assembled by :mod:`peers` and, for each metric, reports the company's
value against the **peer-set median** (an industry proxy) plus a **favourable-side percentile** so
that a high percentile always means "good" regardless of whether higher or lower is better.

Honesty note: the peer set is small and curated, so the percentile is a rank *within that set*, not
a true market-wide percentile. That limitation is reflected in the section's confidence/notes.
"""

from __future__ import annotations

from statistics import median

from ..models import PeerComparison, Ratios, RelativeComparison, RelativeMetric
from . import evidence as ev

# (display name, PeerRow attribute, higher-is-better)
_METRIC_SPECS: list[tuple[str, str, bool]] = [
    ("ROE", "roe", True),
    ("Net margin", "net_margin", True),
    ("Operating margin", "operating_margin", True),
    ("Revenue growth", "revenue_growth_yoy", True),
    ("P/E", "pe", False),
    ("P/B", "pb", False),
    ("Debt/Equity", "debt_to_equity", False),
]


def relative_comparison(
    symbol: str,
    peers: PeerComparison,
    ratios: Ratios | None = None,
) -> RelativeComparison:
    """Compare ``symbol`` against its peer set, metric by metric."""
    symbol = symbol.upper()
    subject = next((p for p in peers.peers if p.ticker == symbol), None)
    others = [p for p in peers.peers if p.ticker != symbol]

    metrics: list[RelativeMetric] = []
    summary: list[str] = []
    computed = 0

    for name, attr, higher_better in _METRIC_SPECS:
        company = _subject_value(subject, ratios, attr)
        peer_vals = [v for v in (getattr(p, attr, None) for p in others) if v is not None]
        if company is None or len(peer_vals) < 2:
            continue  # need the company's value and a couple of peers to be meaningful

        ind = float(median(peer_vals))
        pct = _favourable_percentile(company, peer_vals, higher_better)
        better = (company >= ind) if higher_better else (company <= ind)
        metrics.append(RelativeMetric(
            name=name,
            company=round(company, 6),
            industry=round(ind, 6),
            percentile=round(pct, 3),
            better=better,
            delta=round(company - ind, 6),
            higher_is_better=higher_better,
            provenance=ev.Provenance(source=ev.SRC_YAHOO, detail="peer-set median"),
        ))
        computed += 1
        summary.append(_phrase(name, company, ind, pct, higher_better))

    total = len(_METRIC_SPECS)
    meta = ev.build_meta(
        sources=[
            ev.Provenance(source=ev.SRC_YAHOO, detail="peer fundamentals"),
            ev.Provenance(source=ev.SRC_CURATED, detail="peer list"),
        ],
        present=computed,
        expected=total,
        missing_fields=[n for n, a, _ in _METRIC_SPECS
                        if not any(m.name == n for m in metrics)],
        notes=[f"Percentiles are within a {len(others) + 1}-name peer set, not the whole market."],
    )
    note = None if metrics else "Not enough peer data for a relative comparison."
    return RelativeComparison(
        ticker=symbol,
        metrics=metrics,
        peer_count=len(others) + 1,
        summary=summary,
        evidence=meta,
        note=note,
    )


# --------------------------------------------------------------------------------------
# Internals
# --------------------------------------------------------------------------------------
def _subject_value(subject, ratios: Ratios | None, attr: str) -> float | None:
    """Prefer the subject's peer-set value (same normalization); fall back to raw ratios."""
    if subject is not None:
        val = getattr(subject, attr, None)
        if val is not None:
            return float(val)
    if ratios is not None:
        val = getattr(ratios, attr, None)
        if val is not None:
            return float(val)
    return None


def _favourable_percentile(company: float, peer_vals: list[float], higher_better: bool) -> float:
    """Fraction of peers the company is *at least as good as* (0..1). High = good, always."""
    if higher_better:
        wins = sum(1 for v in peer_vals if company >= v)
    else:
        wins = sum(1 for v in peer_vals if company <= v)
    return wins / len(peer_vals)


def _phrase(name: str, company: float, industry: float, pct: float, higher_better: bool) -> str:
    fmt = _fmt(name)
    return f"{name} {fmt(company)} vs industry {fmt(industry)} ({_band(pct)})"


def _band(pct: float) -> str:
    """Qualitative percentile band (higher pct = better; robust for small peer sets)."""
    if pct >= 0.75:
        return "top quartile"
    if pct >= 0.5:
        return "above median"
    if pct >= 0.25:
        return "below median"
    return "bottom quartile"


def _fmt(name: str):
    if name in {"P/E", "P/B", "Debt/Equity"}:
        return lambda x: f"{x:.1f}"
    return lambda x: f"{x:.1%}"
