"""Investment thesis + AI-ready digest — the capstone synthesis.

Pulls the strands of the analysis together into a decision-useful summary: **pros / cons** drawn
from the score buckets, the Buffett checklist, the relative-to-industry comparison and the red
flags; an overall **quality** grade; a **valuation stance**; and a one-line **verdict**
("High Quality, Fairly Expensive"). :func:`build_ai_signals` distils the same picture into a compact
block other AI agents can consume headlessly.

Nothing here re-derives numbers — it reads the modules' conclusions — so the thesis always agrees
with the sections it summarizes.
"""

from __future__ import annotations

from statistics import mean

from ..models import (
    AiSignals,
    BuffettChecklist,
    Confidence,
    DCFResult,
    GrowthOutlook,
    InvestmentThesis,
    QualityGrade,
    Ratios,
    RedFlagReport,
    RelativeComparison,
    Score,
    ShareholdingPattern,
    ValuationStance,
)
from . import evidence as ev

_MAX_ITEMS = 6


def build_thesis(
    symbol: str,
    *,
    score: Score | None = None,
    ratios: Ratios | None = None,
    buffett: BuffettChecklist | None = None,
    red_flags: RedFlagReport | None = None,
    relative: RelativeComparison | None = None,
    dcf: DCFResult | None = None,
    shareholding: ShareholdingPattern | None = None,
    growth: GrowthOutlook | None = None,
) -> InvestmentThesis:
    """Synthesize the investment thesis from the already-computed module outputs."""
    symbol = symbol.upper()
    pros: list[str] = []
    cons: list[str] = []

    # 1) Score buckets — strengths vs weaknesses.
    if score:
        for b in score.buckets:
            if b.normalized >= 0.60:
                pros.append(f"{b.name}: {b.rationale}")
            elif b.normalized <= 0.35:
                cons.append(f"{b.name}: {b.rationale}")

    # 2) Buffett criteria — passes are pros, fails are cons.
    if buffett:
        for c in buffett.criteria:
            if c.status == "pass":
                pros.append(f"Buffett ✓ {c.name} ({_short(c.reason)})")
            elif c.status == "fail":
                cons.append(f"Buffett ✗ {c.name} ({_short(c.reason)})")

    # 3) Relative to industry — clear out/under-performance.
    if relative:
        for m in relative.metrics:
            if m.percentile is not None and m.percentile >= 0.75 and m.better:
                pros.append(f"{m.name} in the top quartile vs peers")
            elif m.percentile is not None and m.percentile <= 0.25 and m.better is False:
                cons.append(f"{m.name} in the bottom quartile vs peers")

    # 4) Red flags feed straight into cons.
    if red_flags:
        for f in red_flags.flags:
            if f.severity in ("high", "severe"):
                cons.append(f"⚠ {f.issue}")

    pros = _dedupe(pros)[:_MAX_ITEMS]
    cons = _dedupe(cons)[:_MAX_ITEMS]

    quality = _quality(score, buffett)
    stance = _valuation_stance(ratios, relative)
    verdict = _verdict(quality, stance)
    summary = _summary(symbol, quality, stance, red_flags, growth, shareholding)
    conf = _confidence(score, buffett, red_flags, relative)

    return InvestmentThesis(
        ticker=symbol,
        pros=pros,
        cons=cons,
        quality=quality,
        valuation_stance=stance,
        verdict=verdict,
        summary=summary,
        confidence=conf,
        evidence=ev.build_meta(
            sources=[ev.Provenance(source=ev.SRC_STATEMENTS), ev.Provenance(source=ev.SRC_YAHOO)],
            present=sum(x is not None for x in (score, buffett, red_flags, relative)),
            expected=4,
            notes=["Thesis summarizes the module conclusions; it does not re-derive numbers."],
        ),
    )


def build_ai_signals(
    symbol: str,
    *,
    thesis: InvestmentThesis | None = None,
    red_flags: RedFlagReport | None = None,
    shareholding: ShareholdingPattern | None = None,
    growth: GrowthOutlook | None = None,
) -> AiSignals:
    """Compact machine-consumable digest of the whole analysis."""
    return AiSignals(
        ticker=symbol.upper(),
        investment_thesis=thesis.verdict if thesis else None,
        overall_quality=thesis.quality if thesis else None,
        confidence=thesis.confidence.score if (thesis and thesis.confidence) else None,
        ownership_signal=shareholding.ownership_signal if shareholding else None,
        growth_signal=growth.growth_signal if growth else None,
        risk_level=red_flags.risk_level if red_flags else None,
        valuation_stance=thesis.valuation_stance if thesis else None,
        red_flags=[f.issue for f in (red_flags.flags if red_flags else [])][:5],
    )


# --------------------------------------------------------------------------------------
# Internals
# --------------------------------------------------------------------------------------
def _quality(score: Score | None, buffett: BuffettChecklist | None) -> QualityGrade | None:
    total = score.total if score else None
    if total is None:
        total = buffett.weighted_score if (buffett and buffett.weighted_score is not None) else None
    if total is None:
        return None
    if total >= 80:
        return "Excellent"
    if total >= 65:
        return "Good"
    if total >= 50:
        return "Fair"
    if total >= 35:
        return "Weak"
    return "Poor"


def _valuation_stance(
    ratios: Ratios | None, relative: RelativeComparison | None
) -> ValuationStance | None:
    if ratios is None:
        return None
    votes: list[int] = []  # -1 cheap, 0 fair, +1 expensive
    if ratios.pe is not None:
        votes.append(-1 if ratios.pe < 12 else 1 if ratios.pe > 28 else 0)
    if ratios.pb is not None:
        votes.append(-1 if ratios.pb < 1.5 else 1 if ratios.pb > 6 else 0)
    if ratios.peg is not None and ratios.peg > 0:
        votes.append(-1 if ratios.peg < 1 else 1 if ratios.peg > 2 else 0)
    # Relative valuation: cheaper/dearer than the peer median.
    if relative:
        for m in relative.metrics:
            if m.name in ("P/E", "P/B") and m.company is not None and m.industry is not None:
                votes.append(1 if m.company > m.industry else -1 if m.company < m.industry else 0)
    if not votes:
        return None
    avg = mean(votes)
    if avg <= -0.34:
        return "cheap"
    if avg >= 0.34:
        return "expensive"
    return "fair"


def _verdict(quality: QualityGrade | None, stance: ValuationStance | None) -> str | None:
    if quality is None and stance is None:
        return None
    q = quality or "Unrated"
    s = {"cheap": "Attractively Valued", "fair": "Fairly Valued",
         "expensive": "Richly Valued"}.get(stance or "", "Valuation Unclear")
    return f"{q} Quality, {s}"


def _summary(
    symbol: str,
    quality: QualityGrade | None,
    stance: ValuationStance | None,
    red_flags: RedFlagReport | None,
    growth: GrowthOutlook | None,
    shareholding: ShareholdingPattern | None,
) -> str:
    bits = [f"{symbol} screens as {quality.lower() if quality else 'unrated'} quality"]
    if stance:
        bits.append(f"and {stance}ly valued" if stance != "fair" else "and fairly valued")
    if growth and growth.growth_signal:
        bits.append(f"with {growth.growth_signal} forward growth")
    if shareholding and shareholding.ownership_signal:
        bits.append(f"and {shareholding.ownership_signal} ownership trend")
    tail = ""
    if red_flags and red_flags.risk_level not in ("none", None):
        tail = f" Watch {red_flags.risk_level} risk flags."
    return " ".join(bits).replace(" and and ", " and ") + "." + tail


def _confidence(
    score: Score | None,
    buffett: BuffettChecklist | None,
    red_flags: RedFlagReport | None,
    relative: RelativeComparison | None,
) -> Confidence:
    confs: list[float] = []
    for module in (buffett, red_flags, relative):
        meta = getattr(module, "evidence", None)
        if meta and meta.confidence:
            confs.append(meta.confidence.score)
    if score is not None:
        confs.append(0.75)  # the composite score is deterministic from reliable ratios
    avg = round(mean(confs), 3) if confs else 0.5
    return Confidence(score=avg, tier=ev.tier(avg), reason=f"blended from {len(confs)} module(s)")


def _short(text: str | None, limit: int = 60) -> str:
    if not text:
        return ""
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        key = it.lower()
        if key not in seen:
            seen.add(key)
            out.append(it)
    return out
