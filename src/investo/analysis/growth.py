"""Five-year growth outlook — the company's main growth engine, ranked and evidenced.

Combines curated, company-specific knowledge (``data/growth.yaml`` — e.g. Reliance → Jio / Retail /
New Energy, with estimated contribution shares, per-driver risks and a catalyst timeline) with
data-derived signals:

- **sustainable growth** g = ROE × (1 − payout) — the retention-funded internal growth rate,
- **historical** revenue / EPS 3-yr CAGR,
- a best-effort **analyst** forward estimate (Yahoo),
- the curated **industry CAGR**.

These are blended into a low/high 5-year band and a ``growth_signal``. Everything forward-looking is
an *estimate*, so drivers/catalysts carry their own confidence and the section's evidence reflects
the mix of curated vs derived inputs.
"""

from __future__ import annotations

import re
from typing import Any

from ..models import (
    Catalyst,
    Confidence,
    GrowthDriver,
    GrowthOutlook,
    GrowthSignal,
    IndustryIntelligence,
    Provenance,
    Ratios,
)
from . import evidence as ev

_SANE_LOW, _SANE_HIGH = -0.10, 0.50  # clamp blended growth to a plausible band


def growth_outlook(
    symbol: str,
    *,
    ratios: Ratios | None = None,
    info: dict[str, Any] | None = None,
    industry: IndustryIntelligence | None = None,
    sector: str | None = None,
    payout_ratio: float | None = None,
) -> GrowthOutlook:
    """Assemble the 5-year growth outlook for ``symbol``."""
    from ..data import growth_engines
    from ..sources import data
    from .industry import get_industry_intelligence
    from .ratios import compute_ratios

    symbol = symbol.upper()
    if info is None:
        info = data.get_info(symbol)
    if sector is None:
        sector = info.get("sector")
    if ratios is None:
        ratios = compute_ratios(symbol, info=info)
    if industry is None:
        industry = get_industry_intelligence(symbol)
    if payout_ratio is None:
        payout_ratio = _coerce(info.get("payoutRatio"))

    # Data-derived growth signals.
    sustainable = _sustainable_growth(ratios.roe, payout_ratio)
    hist_rev = ratios.revenue_cagr_3y
    hist_eps = ratios.eps_cagr_3y
    est = data.get_growth_estimates(symbol)
    analyst = est.get("earnings_growth") or est.get("revenue_growth")
    industry_cagr_mid = _parse_cagr(industry.industry_cagr)

    estimates = [v for v in (sustainable, hist_rev, analyst, industry_cagr_mid) if v is not None]
    low, high, central = _blend(estimates)
    signal = _signal(central)

    # Curated engine (ticker-specific, then sector), else derived from industry drivers.
    engines = growth_engines()
    curated = engines["by_ticker"].get(symbol) or engines["by_sector"].get(sector or "", None)
    drivers, catalysts, risks, primary, curated_used = _drivers_from_curated(curated)
    if not drivers:
        drivers = _derived_drivers(industry)
        primary = primary or (industry.future_demand or "Sector demand growth")
        risks = risks or list(industry.risks[:4])

    meta = ev.build_meta(
        sources=_sources(curated_used, analyst is not None),
        present=len(estimates),
        expected=4,
        missing_fields=[n for n, v in (("sustainable", sustainable), ("historical", hist_rev),
                                       ("analyst", analyst), ("industry", industry_cagr_mid))
                        if v is None],
        notes=["Forward growth figures are estimates; contribution shares are approximate."],
    )
    # Temper by forecast uncertainty: input coverage alone would overstate certainty about the
    # *future*. Independent estimates that agree earn trust; a wide spread lowers it.
    if meta.confidence is not None:
        agreement = _agreement(low, high)
        tempered = round(meta.confidence.score * agreement, 3)
        meta.confidence = Confidence(
            score=tempered, tier=ev.tier(tempered),
            reason=f"{len(estimates)} growth signal(s), {agreement:.0%} agreement; forward estimate",
        )

    return GrowthOutlook(
        ticker=symbol,
        primary_engine=primary,
        sustainable_growth=_round(sustainable),
        historical_revenue_cagr_3y=_round(hist_rev),
        historical_eps_cagr_3y=_round(hist_eps),
        analyst_growth_est=_round(analyst),
        industry_cagr=industry.industry_cagr,
        blended_5y_low=_round(low),
        blended_5y_high=_round(high),
        drivers=drivers,
        catalysts=catalysts,
        risks=risks,
        growth_signal=signal,
        evidence=meta,
    )


# --------------------------------------------------------------------------------------
# Drivers / catalysts
# --------------------------------------------------------------------------------------
def _drivers_from_curated(
    curated: dict[str, Any] | None,
) -> tuple[list[GrowthDriver], list[Catalyst], list[str], str | None, bool]:
    if not curated:
        return [], [], [], None, False
    drivers: list[GrowthDriver] = []
    conf = ev.confidence(sources=[ev.SRC_CURATED], reason="curated company/sector estimate")
    for i, d in enumerate(curated.get("drivers", []), start=1):
        drivers.append(GrowthDriver(
            rank=i, name=d.get("name", f"Driver {i}"), detail=d.get("detail"),
            contribution_pct=_coerce(d.get("contribution_pct")), confidence=conf,
            risks=list(d.get("risks", [])), source="curated",
        ))
    catalysts = [
        Catalyst(year=_int(c.get("year")), event=c.get("event", ""),
                 confidence=ev.confidence(sources=[ev.SRC_CURATED]))
        for c in curated.get("catalysts", []) if c.get("event")
    ]
    return drivers, catalysts, list(curated.get("risks", [])), curated.get("primary_engine"), True


def _derived_drivers(industry: IndustryIntelligence) -> list[GrowthDriver]:
    """Fall back to equal-weighted drivers from the industry demand drivers."""
    demand = industry.demand_drivers[:4]
    if not demand:
        return []
    share = round(1.0 / len(demand), 2)
    conf = ev.confidence(sources=[ev.SRC_HEURISTIC], reason="derived from industry demand drivers")
    return [
        GrowthDriver(rank=i, name=name, contribution_pct=share, confidence=conf, source="industry")
        for i, name in enumerate(demand, start=1)
    ]


# --------------------------------------------------------------------------------------
# Numeric helpers
# --------------------------------------------------------------------------------------
def _sustainable_growth(roe: float | None, payout: float | None) -> float | None:
    if roe is None:
        return None
    retention = 1.0 - payout if payout is not None else 1.0
    retention = max(0.0, min(1.0, retention))
    return roe * retention


def _blend(estimates: list[float]) -> tuple[float | None, float | None, float | None]:
    if not estimates:
        return None, None, None
    clamped = [max(_SANE_LOW, min(_SANE_HIGH, e)) for e in estimates]
    low, high = min(clamped), max(clamped)
    central = sorted(clamped)[len(clamped) // 2]  # median
    return low, high, central


def _agreement(low: float | None, high: float | None) -> float:
    """1.0 when independent estimates cluster tightly, down to 0.55 when they diverge widely."""
    if low is None or high is None:
        return 0.7  # single estimate — moderate forecast confidence
    spread = high - low
    return max(0.55, min(1.0, 1.0 - spread / 0.20))


def _signal(central: float | None) -> GrowthSignal | None:
    if central is None:
        return None
    if central >= 0.15:
        return "strong"
    if central >= 0.07:
        return "moderate"
    return "weak"


def _parse_cagr(text: str | None) -> float | None:
    """Extract a midpoint fraction from a curated CAGR string like '~5-7% (est.)'."""
    if not text:
        return None
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", text)]
    if not nums:
        return None
    # Use the first one or two numbers (a range) as the estimate.
    vals = nums[:2]
    return (sum(vals) / len(vals)) / 100.0


def _sources(curated_used: bool, has_analyst: bool) -> list[Provenance]:
    srcs = [Provenance(source=ev.SRC_STATEMENTS, detail="historical CAGR"),
            Provenance(source=ev.SRC_CURATED, detail="industry CAGR")]
    if curated_used:
        srcs.append(Provenance(source=ev.SRC_CURATED, detail="growth engine"))
    if has_analyst:
        srcs.append(Provenance(source=ev.SRC_ANALYST))
    return srcs


def _coerce(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _round(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None
