"""Warren Buffett–style quality checklist.

Evaluates the business against Buffett's durable-quality principles — high and *consistent*
returns on capital, low debt, strong owner earnings, a moat, honest owner-friendly management, and
a margin of safety — using figures Investo has already computed (no extra network calls beyond the
statements needed for the historical trend).

Each criterion reports its **value vs threshold**, a **pass / warn / fail / unknown** status, the
**reason** (the *why*), a derived **confidence**, its **provenance**, and — crucially — the
**multi-year trend** so a single exceptional year can't flatter the verdict. The criteria are
weighted (Margin of Safety heaviest at 20) into a **0-100 weighted score**; a criterion whose data
is unavailable is marked ``unknown`` and its weight is renormalized out rather than counted as a
failure. This is a **separate lens** — it does not touch the 0-100 investment score in ``scoring``.
"""

from __future__ import annotations

from typing import Any

from ..models import (
    BuffettChecklist,
    BuffettCriterion,
    CriterionStatus,
    DCFResult,
    Financials,
    Management,
    MoatSignals,
    Provenance,
    Ratios,
    TrendPoint,
)
from . import evidence as ev
from . import finutils as F

_FINANCIAL_SECTORS = {"Financial Services", "Financials", "Banks", "Insurance"}

# Credit awarded to the weighted score per status.
_CREDIT: dict[CriterionStatus, float] = {"pass": 1.0, "warn": 0.5, "fail": 0.0, "unknown": 0.0}


def buffett_checklist(
    symbol: str,
    *,
    ratios: Ratios | None = None,
    dcf: DCFResult | None = None,
    moat: MoatSignals | None = None,
    management: Management | None = None,
    financials: Financials | None = None,
    info: dict[str, Any] | None = None,
    sector: str | None = None,
) -> BuffettChecklist:
    """Build the weighted Buffett checklist for ``symbol`` (fetching any inputs not supplied)."""
    from ..sources import data
    from .dcf import compute_dcf
    from .management import get_management
    from .moat import moat_assessment
    from .ratios import compute_ratios

    symbol = symbol.upper()
    if info is None:
        info = data.get_info(symbol)
    if sector is None:
        sector = info.get("sector")
    if financials is None:
        financials = data.get_financials(symbol)
    if ratios is None:
        ratios = compute_ratios(symbol, info=info, financials=financials)
    if dcf is None:
        dcf = compute_dcf(symbol, info=info, financials=financials, ratios=ratios)
    if moat is None:
        moat = moat_assessment(symbol, ratios=ratios)
    if management is None:
        management = get_management(symbol, info=info, financials=financials, ratios=ratios)

    is_financial = sector in _FINANCIAL_SECTORS
    roe_trend = _roe_series(financials)
    margin_trend = _net_margin_series(financials)

    criteria: list[BuffettCriterion] = [
        _roe(ratios, roe_trend),
        _roic(ratios),
        _debt(ratios, is_financial),
        _fcf(ratios),
        _margin_of_safety(dcf),
        _management(management),
        _moat(moat),
    ]

    weighted_score, applicable = _score(criteria)
    passed = sum(1 for c in criteria if c.status == "pass")
    verdict = _verdict(weighted_score) if weighted_score is not None else "Insufficient data"

    meta = ev.build_meta(
        sources=[
            Provenance(source=ev.SRC_STATEMENTS, detail=_period_span(financials)),
            Provenance(source=ev.SRC_YAHOO),
        ],
        present=applicable,
        expected=len(criteria),
        missing_fields=[c.name for c in criteria if c.status == "unknown"],
        history_years=max(len(roe_trend), len(margin_trend)),
        as_of=_latest_period(financials),
        notes=["Buffett lens is separate from the 0-100 investment score."],
    )

    return BuffettChecklist(
        ticker=symbol,
        criteria=criteria,
        weighted_score=weighted_score,
        passed_count=passed,
        applicable_count=applicable,
        verdict=verdict,
        evidence=meta,
        note=None if applicable else "Not enough data to evaluate the Buffett checklist.",
    )


# --------------------------------------------------------------------------------------
# Individual criteria
# --------------------------------------------------------------------------------------
def _roe(r: Ratios, trend: list[TrendPoint]) -> BuffettCriterion:
    status = _band(r.roe, good=0.15, ok=0.10)
    verdict = _trend_verdict([p.value for p in trend], good=0.15, ok=0.10)
    reason = _reason("ROE", r.roe, "15%", status, pct=True, trend_verdict=verdict)
    return _make(
        "Consistent high ROE", 15.0, r.roe, "ROE > 15%", status, reason,
        sources=[ev.SRC_STATEMENTS, ev.SRC_YAHOO], trend=trend, trend_verdict=verdict,
    )


def _roic(r: Ratios) -> BuffettCriterion:
    status = _band(r.roic, good=0.12, ok=0.08)
    reason = _reason("ROIC", r.roic, "12%", status, pct=True)
    return _make("High ROIC", 15.0, r.roic, "ROIC > 12%", status, reason,
                 sources=[ev.SRC_STATEMENTS])


def _debt(r: Ratios, is_financial: bool) -> BuffettCriterion:
    if is_financial:
        return _make(
            "Low debt", 15.0, r.debt_to_equity, "D/E < 0.5 & interest cover > 8x", "unknown",
            "Leverage is structurally high for financials — not comparable on this rule.",
            sources=[ev.SRC_YAHOO],
        )
    de, cov = r.debt_to_equity, r.interest_coverage
    if de is None and cov is None:
        status: CriterionStatus = "unknown"
    elif (de is not None and de < 0.5) and (cov is not None and cov > 8):
        status = "pass"
    elif (de is None or de < 1.0) and (cov is None or cov > 4):
        status = "warn"
    else:
        status = "fail"
    reason = (
        f"D/E {_num(de)} and interest coverage {_num(cov)}x vs target D/E < 0.5 & cover > 8x → "
        f"{status.upper()}"
    )
    return _make("Low debt", 15.0, de, "D/E < 0.5 & interest cover > 8x", status, reason,
                 sources=[ev.SRC_YAHOO, ev.SRC_STATEMENTS])


def _fcf(r: Ratios) -> BuffettCriterion:
    fm, ocf = r.fcf_margin, r.ocf_to_ebitda
    if fm is None:
        status: CriterionStatus = "unknown"
    elif fm > 0.05 and (ocf is None or ocf > 0.8):
        status = "pass"
    elif fm > 0:
        status = "warn"
    else:
        status = "fail"
    reason = (
        f"FCF margin {_pct(fm)} (OCF/EBITDA {_num(ocf)}) vs target > 5% & cash-backed earnings → "
        f"{status.upper()}"
    )
    return _make("Strong owner earnings (FCF)", 15.0, fm, "FCF margin > 5%", status, reason,
                 sources=[ev.SRC_STATEMENTS])


def _margin_of_safety(dcf: DCFResult) -> BuffettCriterion:
    mos = dcf.margin_of_safety
    # A plain FCF-DCF is unreliable for capex-heavy businesses (dcf.note flags this) — in that
    # case report UNKNOWN rather than unfairly failing the company.
    if dcf.note or mos is None:
        status: CriterionStatus = "unknown"
        reason = (
            "DCF is low-confidence for this business (capital-intensive); margin of safety not "
            "reliable — cross-check with P/E, P/B, EV/EBITDA."
            if dcf.note else "No DCF margin of safety available."
        )
    else:
        status = "pass" if mos > 0.15 else "warn" if mos > 0 else "fail"
        reason = _reason("Margin of safety", mos, "15%", status, pct=True)
    return _make("Margin of safety", 20.0, mos, "Intrinsic value > price (MoS > 15%)", status,
                 reason, sources=[ev.SRC_HEURISTIC])


def _management(m: Management) -> BuffettCriterion:
    promoter = m.promoter_holding
    buyback = bool(m.buyback_signal)
    payout = m.dividend_payout_ratio
    if promoter is None and not buyback and payout is None:
        status: CriterionStatus = "unknown"
    elif (promoter is not None and promoter >= 0.40) or buyback:
        status = "pass"
    elif (promoter is not None and promoter >= 0.15) or (payout is not None and payout > 0):
        status = "warn"
    else:
        status = "fail"
    bits = []
    if promoter is not None:
        bits.append(f"promoter/insider holding {_pct(promoter)}")
    if buyback:
        bits.append("buyback detected")
    if payout is not None:
        bits.append(f"payout {_pct(payout)}")
    reason = (", ".join(bits) or "no ownership signal") + f" → {status.upper()}"
    return _make("Owner-friendly management", 10.0, promoter,
                 "Skin in the game / capital discipline", status, reason,
                 sources=[ev.SRC_YAHOO])


def _moat(moat: MoatSignals) -> BuffettCriterion:
    score = moat.moat_score
    status = _band(score, good=6.0, ok=4.0)
    reason = _reason("Moat score", score, "6/10", status, pct=False)
    return _make("Durable moat", 10.0, score, "Heuristic moat >= 6/10", status, reason,
                 sources=[ev.SRC_HEURISTIC])


# --------------------------------------------------------------------------------------
# Trend series (from reported statements)
# --------------------------------------------------------------------------------------
def _roe_series(fin: Financials) -> list[TrendPoint]:
    inc, bal = fin.income_statement, fin.balance_sheet
    ni = F.series(inc, *F.NET_INCOME)
    eq = F.series(bal, *F.EQUITY)
    n = min(len(inc), len(ni), len(eq))
    out: list[TrendPoint] = []
    for i in range(n):
        val = F.safe_div(ni[i], eq[i])
        out.append(TrendPoint(period=inc[i].period, value=round(val, 4) if val is not None else None))
    return [p for p in out if p.value is not None]


def _net_margin_series(fin: Financials) -> list[TrendPoint]:
    inc = fin.income_statement
    ni = F.series(inc, *F.NET_INCOME)
    rev = F.series(inc, *F.REVENUE)
    out: list[TrendPoint] = []
    for i in range(len(inc)):
        val = F.safe_div(ni[i], rev[i])
        out.append(TrendPoint(period=inc[i].period, value=round(val, 4) if val is not None else None))
    return [p for p in out if p.value is not None]


def _trend_verdict(vals: list[float | None], good: float, ok: float) -> str | None:
    xs = [v for v in vals if v is not None]
    if len(xs) < 2:
        return None
    newest, oldest = xs[0], xs[-1]
    rising = newest > oldest * 1.02
    falling = newest < oldest * 0.98
    if all(v >= good for v in xs):
        return "Consistently excellent"
    if all(v >= ok for v in xs):
        return "Consistently solid" if not rising else "Improving"
    if falling:
        return "Declining"
    if rising:
        return "Improving from a low base"
    return "Volatile"


# --------------------------------------------------------------------------------------
# Assembly helpers
# --------------------------------------------------------------------------------------
def _make(
    name: str,
    weight: float,
    value: float | None,
    threshold: str,
    status: CriterionStatus,
    reason: str,
    *,
    sources: list[str],
    trend: list[TrendPoint] | None = None,
    trend_verdict: str | None = None,
) -> BuffettCriterion:
    history_years = len([p for p in (trend or []) if p.value is not None]) or None
    conf = ev.confidence(
        sources=sources,
        coverage=None if value is not None else 0.0,
        history_years=history_years,
    ) if status != "unknown" else ev.confidence(sources=sources, coverage=0.0)
    return BuffettCriterion(
        name=name, weight=weight, value=_round(value), threshold=threshold, status=status,
        reason=reason, confidence=conf, provenance=Provenance(source=sources[0]),
        trend=trend or [], trend_verdict=trend_verdict,
    )


def _score(criteria: list[BuffettCriterion]) -> tuple[float | None, int]:
    applicable = [c for c in criteria if c.status != "unknown"]
    if not applicable:
        return None, 0
    earned = sum(c.weight * _CREDIT[c.status] for c in applicable)
    possible = sum(c.weight for c in applicable)
    return round(100.0 * earned / possible, 1), len(applicable)


def _verdict(score: float) -> str:
    if score >= 80:
        return "Strong Buffett fit"
    if score >= 60:
        return "Good Buffett fit"
    if score >= 40:
        return "Partial Buffett fit"
    return "Weak Buffett fit"


def _band(value: float | None, good: float, ok: float) -> CriterionStatus:
    if value is None:
        return "unknown"
    if value >= good:
        return "pass"
    if value >= ok:
        return "warn"
    return "fail"


def _reason(
    label: str,
    value: float | None,
    threshold: str,
    status: CriterionStatus,
    *,
    pct: bool,
    trend_verdict: str | None = None,
) -> str:
    shown = _pct(value) if pct else _num(value)
    base = f"{label} {shown} vs {threshold} threshold → {status.upper()}"
    if trend_verdict:
        base += f" ({trend_verdict.lower()} over history)"
    return base


def _round(value: float | None) -> float | None:
    return round(value, 6) if value is not None else None


def _pct(value: float | None) -> str:
    return f"{value:.1%}" if value is not None else "n/a"


def _num(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else "n/a"


def _period_span(fin: Financials) -> str | None:
    periods = [p.period for p in fin.income_statement if p.period]
    if not periods:
        return None
    return f"{periods[-1]}…{periods[0]}" if len(periods) > 1 else periods[0]


def _latest_period(fin: Financials) -> str | None:
    return fin.income_statement[0].period if fin.income_statement else None
