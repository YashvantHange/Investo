"""Relative-to-industry comparison.

Absolute ratios only say so much — "ROE 24%" means more when the peer median is 17%. This module
reuses the peer set already assembled by :mod:`peers` and, for each metric, reports the company's
value against the **peer-set median** (an industry proxy) plus a **favourable-side percentile** so
that a high percentile always means "good" regardless of whether higher or lower is better.

Honesty notes, which the confidence reflects rather than merely mentions:

- The peer set is small and curated, so a percentile is a rank *within that set*, not a true
  market-wide percentile. This module therefore cannot reach the High confidence tier.
- A guessed peer set (``sector-fallback``) is priced below a deliberate one (``curated``), and a
  two-name set below a six-name one, via ``reliability_factor``.
- With no peers there are no metrics, and the confidence is **zero** — not a plausible-looking
  number derived from nothing.
"""

from __future__ import annotations

from statistics import median

from ..models import MetricUnit, PeerBasis, PeerComparison, Ratios, RelativeComparison, RelativeMetric
from . import evidence as ev

# (display name, PeerRow attribute, higher-is-better, unit)
_METRIC_SPECS: list[tuple[str, str, bool, MetricUnit]] = [
    ("ROE", "roe", True, "percent"),
    ("ROA", "roa", True, "percent"),
    ("Net margin", "net_margin", True, "percent"),
    ("Operating margin", "operating_margin", True, "percent"),
    ("Revenue growth", "revenue_growth_yoy", True, "percent"),
    ("P/E", "pe", False, "ratio"),
    ("P/B", "pb", False, "ratio"),
    ("P/S", "price_to_sales", False, "ratio"),
    ("EV/EBITDA", "ev_ebitda", False, "ratio"),
    ("Debt/Equity", "debt_to_equity", False, "ratio"),
]

# A metric needs at least this many peer values before its median means anything.
_MIN_PEERS_FOR_MEDIAN = 2

# How much to trust a peer set given how it was found. Curated caps below the High tier (0.80)
# on purpose: a rank among five hand-picked names is not a market percentile, however complete
# the data behind it.
_BASIS_RELIABILITY: dict[PeerBasis, float] = {
    "curated": 0.90,
    "keyed": 0.80,
    "sector-fallback": 0.65,
    "none": 0.0,
}

# A small peer set is a weak proxy for an industry, independent of how it was found.
_PEER_FACTOR_FLOOR = 0.6
_PEER_FACTOR_SPAN = 0.4
_PEER_TARGET = 4

_BAND_TOP = 0.75
_BAND_ABOVE = 0.5
_BAND_BELOW = 0.25


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
    applicable: list[str] = []   # metrics the peer set can actually rank on
    missing: list[str] = []      # applicable, but we lack the company's own value
    unavailable: list[str] = []  # the peer set has no data for these at all

    for name, attr, higher_better, unit in _METRIC_SPECS:
        peer_vals = [v for v in (getattr(p, attr, None) for p in others) if v is not None]
        if len(peer_vals) < _MIN_PEERS_FOR_MEDIAN:
            unavailable.append(name)
            continue

        applicable.append(name)
        company = _subject_value(subject, ratios, attr)
        if company is None:
            missing.append(name)
            continue

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
            unit=unit,
            provenance=ev.Provenance(source=ev.SRC_YAHOO, detail="peer-set median"),
        ))
        summary.append(_phrase(name, company, ind, pct, unit))

    label = peers.peer_group_label or peers.sector
    meta = _evidence(peers.basis, label, len(others), metrics, applicable, missing, unavailable)
    return RelativeComparison(
        ticker=symbol,
        metrics=metrics,
        peer_count=len(others) + 1 if others else 0,
        summary=summary,
        basis=peers.basis,
        peer_group_label=label,
        evidence=meta,
        note=None if metrics else _no_metrics_note(peers.basis),
    )


# --------------------------------------------------------------------------------------
# Evidence
# --------------------------------------------------------------------------------------
def _evidence(
    basis: PeerBasis,
    label: str | None,
    n_peers: int,
    metrics: list[RelativeMetric],
    applicable: list[str],
    missing: list[str],
    unavailable: list[str],
) -> ev.EvidenceMeta:
    """Price this comparison honestly.

    Coverage is computed against the metrics the peer set can actually rank on, not against every
    metric we know how to compute. Otherwise adding a metric that Indian peers rarely report would
    silently mark every Indian company down — a confidence drop with no change in what we know.
    """
    # `or len(_METRIC_SPECS)` is load-bearing: build_meta treats expected=0 as "not applicable"
    # and would hand back full confidence for a module that computed nothing at all.
    expected = len(applicable) or len(_METRIC_SPECS)

    notes: list[str] = []
    if metrics:
        notes.append(f"Percentiles are a rank within a {n_peers}-peer {basis} set"
                     f"{f' ({label})' if label else ''}, not the whole market.")
    # With no peers at all, every metric is trivially "unavailable" — the reason already says why,
    # and listing all ten would bury it.
    if unavailable and n_peers:
        notes.append("No peer data reported for: " + ", ".join(unavailable) + ".")

    return ev.build_meta(
        sources=[
            ev.Provenance(source=ev.SRC_YAHOO, detail="peer fundamentals"),
            ev.Provenance(source=ev.SRC_CURATED, detail="peer list"),
        ],
        present=len(metrics),
        expected=expected,
        missing_fields=missing,
        reliability_factor=_reliability(basis, n_peers),
        notes=notes,
        reason=None if metrics else _no_metrics_note(basis),
    )


def _reliability(basis: PeerBasis, n_peers: int) -> float:
    """Discount for *how* the peer set was obtained and how thin it is."""
    if not n_peers:
        return 0.0
    peer_factor = _PEER_FACTOR_FLOOR + _PEER_FACTOR_SPAN * min(1.0, n_peers / _PEER_TARGET)
    return _BASIS_RELIABILITY.get(basis, 0.0) * peer_factor


def _no_metrics_note(basis: PeerBasis) -> str:
    if basis == "none":
        return "No peer metrics computed: no peer group matched this ticker."
    return ("No peer metrics computed: the peer set reported too few comparable figures "
            f"(basis: {basis}).")


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


def _phrase(name: str, company: float, industry: float, pct: float, unit: MetricUnit) -> str:
    return f"{name} {_fmt(company, unit)} vs industry {_fmt(industry, unit)} ({_band(pct)})"


def _band(pct: float) -> str:
    """Qualitative percentile band (higher pct = better; robust for small peer sets)."""
    if pct >= _BAND_TOP:
        return "top quartile"
    if pct >= _BAND_ABOVE:
        return "above median"
    if pct >= _BAND_BELOW:
        return "below median"
    return "bottom quartile"


def _fmt(value: float, unit: MetricUnit) -> str:
    return f"{value:.1f}x" if unit == "ratio" else f"{value:.1%}"
