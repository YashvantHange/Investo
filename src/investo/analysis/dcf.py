"""Two-stage discounted-cash-flow valuation.

Projects free cash flow for ``years`` at an estimated growth rate, adds a Gordon terminal
value, discounts to present, subtracts net debt to get equity value, and converts to an
intrinsic value per share -- handling the case where the statements' currency differs from
the trading currency (e.g. Infosys reports in USD but trades in INR on the NSE).

This is an approximation for research, not a precise fair-value oracle. Assumptions are
returned alongside the result so they can be inspected and overridden.
"""

from __future__ import annotations

from statistics import median
from typing import Any

from ..config import CONFIG
from ..models import DCFResult, Financials, Ratios
from . import finutils as F

_GROWTH_CAP = 0.15  # cap the explicit-period growth for conservatism


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _base_fcf(fin: Financials, ratios: Ratios) -> float | None:
    """A smoothed base free cash flow (average of available positive FCF years)."""
    fcf_series: list[float] = []
    for p in fin.cash_flow:
        v = F.pick(p.values, *F.FREE_CASH_FLOW)
        if v is None:
            ocf = F.pick(p.values, *F.OPERATING_CASH_FLOW)
            capex = F.pick(p.values, *F.CAPEX)
            if ocf is not None and capex is not None:
                v = ocf + capex
        if v is not None:
            fcf_series.append(v)
    positive = [v for v in fcf_series if v > 0]
    if positive:
        # Average of up to the 3 most recent positive years (newest-first).
        window = positive[:3]
        return sum(window) / len(window)
    if ratios.fcf is not None and ratios.fcf > 0:
        return ratios.fcf
    return None


def _estimate_growth(ratios: Ratios, terminal_growth: float) -> float:
    candidates = [ratios.revenue_cagr_3y, ratios.revenue_growth_yoy, ratios.earnings_growth_yoy]
    vals = [c for c in candidates if c is not None and -0.5 < c < 1.0]
    g = median(vals) if vals else 0.08
    return _clamp(g, terminal_growth + 0.01, _GROWTH_CAP)


def _net_debt(fin: Financials, info: dict[str, Any]) -> float:
    bal = F.latest(fin.balance_sheet)
    total_debt = F.pick(bal, *F.TOTAL_DEBT)
    cash = F.pick(bal, *F.CASH)
    if total_debt is None:
        total_debt = _f(info.get("totalDebt"))
    if cash is None:
        cash = _f(info.get("totalCash"))
    total_debt = total_debt or 0.0
    cash = cash or 0.0
    return total_debt - cash


def _f(v: Any) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def compute_dcf(
    symbol: str,
    info: dict[str, Any] | None = None,
    financials: Financials | None = None,
    ratios: Ratios | None = None,
    *,
    discount_rate: float | None = None,
    terminal_growth: float | None = None,
    years: int | None = None,
    growth_rate: float | None = None,
) -> DCFResult:
    from ..sources import data
    from .ratios import compute_ratios

    if info is None:
        info = data.get_info(symbol)
    if financials is None:
        financials = data.get_financials(symbol)
    if ratios is None:
        ratios = compute_ratios(symbol, info=info, financials=financials)

    market = data.market_of_symbol(symbol, info.get("exchange"))
    stmt_ccy = info.get("financialCurrency") or info.get("currency")
    price_ccy = info.get("currency") or stmt_ccy

    r = discount_rate if discount_rate is not None else CONFIG.discount_rate_for_market(market)
    tg = terminal_growth if terminal_growth is not None else CONFIG.dcf_terminal_growth
    n = years if years is not None else CONFIG.dcf_years

    result = DCFResult(
        ticker=symbol.upper(),
        currency=price_ccy,
        discount_rate=r,
        terminal_growth=tg,
        years=n,
    )

    base_fcf = _base_fcf(financials, ratios)
    if base_fcf is None:
        result.note = "DCF not available: no positive free cash flow found."
        return result
    if r <= tg:
        result.note = "DCF not available: discount rate must exceed terminal growth."
        return result

    g = growth_rate if growth_rate is not None else _estimate_growth(ratios, tg)
    result.base_fcf = base_fcf
    result.growth_rate = g

    # Two-stage DCF (values in statement currency).
    pv_fcf = 0.0
    fcf_t = base_fcf
    for t in range(1, n + 1):
        fcf_t = fcf_t * (1 + g)
        pv_fcf += fcf_t / ((1 + r) ** t)
    terminal_value = fcf_t * (1 + tg) / (r - tg)
    pv_terminal = terminal_value / ((1 + r) ** n)
    enterprise_value = pv_fcf + pv_terminal

    net_debt = _net_debt(financials, info)
    equity_value_stmt = enterprise_value - net_debt

    result.enterprise_value = enterprise_value
    result.equity_value = equity_value_stmt

    # Convert equity value to trading currency for a per-share figure.
    fx = data.fx_rate(stmt_ccy, price_ccy)
    shares = _f(info.get("sharesOutstanding"))
    price = _f(info.get("currentPrice") or info.get("regularMarketPrice"))
    result.current_price = price

    assumptions = [
        f"base FCF (smoothed) = {base_fcf:,.0f} {stmt_ccy}",
        f"explicit growth = {g:.1%} for {n}y, then {tg:.1%} terminal",
        f"discount rate = {r:.1%}",
        f"net debt = {net_debt:,.0f} {stmt_ccy}",
    ]
    if fx not in (None, 1.0):
        assumptions.append(f"FX {stmt_ccy}->{price_ccy} = {fx:.2f}")

    if fx is not None and shares and equity_value_stmt is not None:
        intrinsic_ps = (equity_value_stmt * fx) / shares
        result.intrinsic_value_per_share = intrinsic_ps
        if price:
            result.margin_of_safety = (intrinsic_ps - price) / intrinsic_ps if intrinsic_ps else None
            result.expected_return = (intrinsic_ps - price) / price
            if result.margin_of_safety is not None and result.margin_of_safety < -1.0:
                result.note = (
                    "Low confidence: a plain FCF-DCF materially understates capital-intensive "
                    "or heavy-reinvestment businesses; cross-check with P/E, P/B and EV/EBITDA."
                )
    else:
        result.note = "Per-share intrinsic value unavailable (missing shares or FX rate)."

    result.assumptions = assumptions
    return result
