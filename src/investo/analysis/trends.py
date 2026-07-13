"""Fundamentals trend — multi-year revenue / profit / margin / EPS / ROE with a health read.

Turns the reported statements into per-metric series (newest-first) plus an at-a-glance direction
(``up`` / ``flat`` / ``down`` per year) and a qualitative ``health`` grade, so an LLM or reader can
see consistency instantly instead of parsing a table. A single exceptional or weak year is visible
rather than hidden in an average. All values come from statements Investo already fetches.
"""

from __future__ import annotations

from ..models import (
    Financials,
    FundamentalTrend,
    HealthGrade,
    MetricTrend,
    Provenance,
)
from . import evidence as ev
from . import finutils as F

_FLAT_EPS = 0.02  # <2% YoY change reads as "flat"


def fundamental_trend(symbol: str, *, financials: Financials | None = None) -> FundamentalTrend:
    """Build the multi-year fundamentals trend for ``symbol``."""
    from ..sources import data

    symbol = symbol.upper()
    if financials is None:
        financials = data.get_financials(symbol)

    inc = financials.income_statement
    bal = financials.balance_sheet
    periods = [p.period for p in inc]

    revenue = F.series(inc, *F.REVENUE)
    net_income = F.series(inc, *F.NET_INCOME)
    eps = F.series(inc, *F.DILUTED_EPS)
    equity = F.series(bal, *F.EQUITY)
    net_margin = _ratio_series(net_income, revenue)
    roe = _ratio_series(net_income, equity)

    metrics: list[MetricTrend] = []
    for name, values, higher_better in (
        ("Revenue", revenue, True),
        ("Net income", net_income, True),
        ("Net margin", net_margin, True),
        ("EPS", eps, True),
        ("ROE", roe, True),
    ):
        mt = _metric_trend(name, periods, values, higher_better)
        if mt is not None:
            metrics.append(mt)

    health_map: dict[str, str] = {m.name: (m.health or "n/a") for m in metrics}
    overall = _overall_health(metrics)

    meta = ev.build_meta(
        sources=[Provenance(source=ev.SRC_STATEMENTS, detail=_span(periods))],
        present=len(metrics),
        expected=5,
        history_years=len([p for p in periods if p]),
        as_of=periods[0] if periods else None,
    )
    note = None if metrics else "No statement history available to build a trend."
    return FundamentalTrend(
        ticker=symbol, metrics=metrics, financial_health=health_map, overall_health=overall,
        evidence=meta, note=note,
    )


# --------------------------------------------------------------------------------------
# Internals
# --------------------------------------------------------------------------------------
def _metric_trend(
    name: str, periods: list[str], values: list[float | None], higher_better: bool
) -> MetricTrend | None:
    n = min(len(periods), len(values))
    labels = periods[:n]
    vals = values[:n]
    if sum(v is not None for v in vals) < 2:
        return None
    directions = _directions(vals)
    return MetricTrend(
        name=name, periods=labels, values=[_round(v) for v in vals], directions=directions,
        health=_health(vals, directions, higher_better), cagr=_round(F.cagr(vals)),
    )


def _directions(values: list[float | None]) -> list[str]:
    """Per year-over-year step (newest-first): up / flat / down. Length = len(values) - 1."""
    out: list[str] = []
    for i in range(len(values) - 1):
        cur, prev = values[i], values[i + 1]
        if cur is None or prev is None or prev == 0:
            out.append("flat")
            continue
        change = (cur - prev) / abs(prev)
        out.append("up" if change > _FLAT_EPS else "down" if change < -_FLAT_EPS else "flat")
    return out


def _health(values: list[float | None], directions: list[str], higher_better: bool) -> HealthGrade:
    ups = directions.count("up")
    downs = directions.count("down")
    steps = len(directions) or 1
    up_ratio = ups / steps
    if not higher_better:  # invert for lower-is-better metrics
        up_ratio = downs / steps
    newest = next((v for v in values if v is not None), None)
    positive = newest is None or newest > 0
    if up_ratio >= 0.8 and positive:
        return "Excellent"
    if up_ratio >= 0.6 and positive:
        return "Good"
    if up_ratio >= 0.4:
        return "Stable"
    if up_ratio >= 0.2:
        return "Weak"
    return "Poor"


_HEALTH_ORDER: list[HealthGrade] = ["Poor", "Weak", "Stable", "Good", "Excellent"]
_HEALTH_RANK = {grade: i for i, grade in enumerate(_HEALTH_ORDER)}


def _overall_health(metrics: list[MetricTrend]) -> HealthGrade | None:
    grades = [_HEALTH_RANK[m.health] for m in metrics if m.health]
    if not grades:
        return None
    avg = max(0, min(len(_HEALTH_ORDER) - 1, round(sum(grades) / len(grades))))
    return _HEALTH_ORDER[avg]


def _ratio_series(num: list[float | None], den: list[float | None]) -> list[float | None]:
    n = min(len(num), len(den))
    return [F.safe_div(num[i], den[i]) for i in range(n)]


def _span(periods: list[str]) -> str | None:
    clean = [p for p in periods if p]
    if not clean:
        return None
    return f"{clean[-1]}…{clean[0]}" if len(clean) > 1 else clean[0]


def _round(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None
