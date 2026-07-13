"""Red-flag detection — automated warning signs an analyst would circle.

Scans the ratios and the multi-year statement trends for deterioration patterns (revenue rising
while profit falls, leverage climbing, cash flow turning negative, margins compressing, thin
interest cover or liquidity, rising promoter pledge) and rolls them up into an overall
``risk_level``. Each flag carries its own severity, a concrete detail, and provenance.

Everything is derived from data Investo already fetches; a flag only fires when the underlying
figures are present, so a data gap never manufactures a false alarm.
"""

from __future__ import annotations

from typing import Any, Literal

from ..models import (
    Financials,
    Provenance,
    Ratios,
    RedFlag,
    RedFlagReport,
    Severity,
    ShareholdingPattern,
)
from . import evidence as ev
from . import finutils as F

# Order matters: higher-severity levels first for the roll-up.
_SEVERITY_RANK: dict[str, int] = {"none": 0, "low": 1, "moderate": 2, "high": 3, "severe": 4}


def detect_red_flags(
    symbol: str,
    *,
    ratios: Ratios | None = None,
    financials: Financials | None = None,
    info: dict[str, Any] | None = None,
    shareholding: ShareholdingPattern | None = None,
) -> RedFlagReport:
    """Detect deterioration red flags for ``symbol`` (fetching inputs not supplied)."""
    from ..sources import data
    from .ratios import compute_ratios

    symbol = symbol.upper()
    if info is None:
        info = data.get_info(symbol)
    if financials is None:
        financials = data.get_financials(symbol)
    if ratios is None:
        ratios = compute_ratios(symbol, info=info, financials=financials)

    rev = F.series(financials.income_statement, *F.REVENUE)
    ni = F.series(financials.income_statement, *F.NET_INCOME)
    debt = F.series(financials.balance_sheet, *F.TOTAL_DEBT)
    fcf = F.series(financials.cash_flow, *F.FREE_CASH_FLOW)
    margins = _margin_series(rev, ni)

    prov = Provenance(source=ev.SRC_STATEMENTS, detail=_span(financials))
    flags: list[RedFlag] = []

    # Revenue up but profit down (either latest YoY, or over the full window).
    if _rising(rev) and _falling(ni):
        flags.append(RedFlag(
            issue="Revenue rising but profit falling",
            severity="high",
            detail=f"Revenue up but net income down over {len(ni)} periods — margin or cost pressure.",
            provenance=prov,
        ))
    elif ratios.revenue_growth_yoy and ratios.revenue_growth_yoy > 0 and \
            ratios.earnings_growth_yoy is not None and ratios.earnings_growth_yoy < -0.05:
        flags.append(RedFlag(
            issue="Earnings falling despite revenue growth",
            severity="moderate",
            detail=f"Revenue +{ratios.revenue_growth_yoy:.0%} YoY but earnings "
                   f"{ratios.earnings_growth_yoy:.0%} YoY.",
            provenance=Provenance(source=ev.SRC_YAHOO),
        ))

    # Losses.
    if ni and ni[0] is not None and ni[0] < 0:
        flags.append(RedFlag(issue="Net loss in the latest year", severity="severe",
                             detail="Company reported a net loss most recently.", provenance=prov))

    # Rising leverage.
    if _rising(debt, threshold=0.20):
        sev: Severity = "high" if (ratios.debt_to_equity or 0) > 1.5 else "moderate"
        flags.append(RedFlag(issue="Debt rising", severity=sev,
                             detail=f"Total debt up >20% across the window; D/E "
                                    f"{_num(ratios.debt_to_equity)}.", provenance=prov))
    elif ratios.debt_to_equity is not None and ratios.debt_to_equity > 2.0:
        flags.append(RedFlag(issue="High leverage", severity="high",
                             detail=f"D/E {ratios.debt_to_equity:.2f}.",
                             provenance=Provenance(source=ev.SRC_YAHOO)))

    # Cash flow.
    if ratios.fcf is not None and ratios.fcf < 0:
        flags.append(RedFlag(issue="Negative free cash flow", severity="high",
                             detail="Latest free cash flow is negative.", provenance=prov))
    elif _turned_negative(fcf):
        flags.append(RedFlag(issue="Free cash flow turned negative", severity="moderate",
                             detail="FCF slipped below zero within the window.", provenance=prov))

    # Margin compression.
    if _falling(margins, threshold=0.15) and len(margins) >= 3:
        flags.append(RedFlag(issue="Margins compressing", severity="moderate",
                             detail="Net margin has declined materially over the last few years.",
                             provenance=prov))

    # Coverage / liquidity stress.
    if ratios.interest_coverage is not None and ratios.interest_coverage < 2:
        flags.append(RedFlag(issue="Thin interest coverage", severity="high",
                             detail=f"Interest coverage {ratios.interest_coverage:.1f}x (<2x).",
                             provenance=Provenance(source=ev.SRC_YAHOO)))
    if ratios.current_ratio is not None and ratios.current_ratio < 1.0:
        flags.append(RedFlag(issue="Liquidity stress", severity="moderate",
                             detail=f"Current ratio {ratios.current_ratio:.2f} (<1).",
                             provenance=Provenance(source=ev.SRC_YAHOO)))

    # Promoter pledge (from shareholding, when available — M2).
    latest_holding = shareholding.latest if shareholding else None
    pledge = latest_holding.promoter_pledge if latest_holding else None
    if pledge is not None and pledge > 0:
        sev = "high" if pledge > 0.25 else "moderate"
        flags.append(RedFlag(issue="Promoter shares pledged", severity=sev,
                             detail=f"Promoter pledge {pledge:.0%}.",
                             provenance=latest_holding.provenance if latest_holding else None))

    risk_level = _roll_up(flags)
    coverage = _coverage(ratios, financials)
    meta = ev.build_meta(
        sources=[prov, Provenance(source=ev.SRC_YAHOO)],
        present=int(coverage * 8),
        expected=8,
        history_years=len(rev),
        as_of=_span(financials),
    )
    note = "No material red flags detected." if not flags else None
    return RedFlagReport(ticker=symbol, flags=flags, risk_level=risk_level, evidence=meta, note=note)


# --------------------------------------------------------------------------------------
# Internals
# --------------------------------------------------------------------------------------
def _margin_series(rev: list[float | None], ni: list[float | None]) -> list[float | None]:
    n = min(len(rev), len(ni))
    return [F.safe_div(ni[i], rev[i]) for i in range(n)]


def _rising(series: list[float | None], threshold: float = 0.0) -> bool:
    """True if the newest value exceeds the oldest by more than ``threshold`` (fractional)."""
    xs = [v for v in series if v is not None]
    if len(xs) < 2:
        return False
    newest, oldest = xs[0], xs[-1]
    if oldest <= 0:
        return False
    return (newest - oldest) / abs(oldest) > threshold


def _falling(series: list[float | None], threshold: float = 0.0) -> bool:
    xs = [v for v in series if v is not None]
    if len(xs) < 2:
        return False
    newest, oldest = xs[0], xs[-1]
    if oldest <= 0:
        return False
    return (oldest - newest) / abs(oldest) > threshold


def _turned_negative(series: list[float | None]) -> bool:
    xs = [v for v in series if v is not None]
    return bool(xs) and xs[0] is not None and xs[0] < 0


def _roll_up(flags: list[RedFlag]) -> Severity | Literal["none"]:
    if not flags:
        return "none"
    if any(f.severity == "severe" for f in flags):
        return "severe"
    highs = sum(1 for f in flags if f.severity == "high")
    mods = sum(1 for f in flags if f.severity == "moderate")
    if highs >= 2 or (highs >= 1 and mods >= 2):
        return "high"
    if highs >= 1 or mods >= 2:
        return "moderate"
    return "low"


def _coverage(ratios: Ratios, fin: Financials) -> float:
    have = sum(x is not None for x in (
        ratios.debt_to_equity, ratios.interest_coverage, ratios.current_ratio, ratios.fcf,
        ratios.revenue_growth_yoy, ratios.earnings_growth_yoy))
    have += 1 if fin.income_statement else 0
    have += 1 if fin.balance_sheet else 0
    return min(1.0, have / 8)


def _span(fin: Financials) -> str | None:
    periods = [p.period for p in fin.income_statement if p.period]
    if not periods:
        return None
    return f"{periods[-1]}…{periods[0]}" if len(periods) > 1 else periods[0]


def _num(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else "n/a"
