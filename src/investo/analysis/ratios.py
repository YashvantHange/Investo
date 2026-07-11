"""Compute a normalized :class:`Ratios` object for a company.

Two sources are combined:
1. Yahoo's precomputed ``info`` ratios (currency-consistent, reliable) -- with unit fixes
   (e.g. ``debtToEquity`` is a *percent*, ``returnOnEquity`` is a *fraction*).
2. Ratios derived from the financial statements (ROCE, ROIC, interest coverage, CAGRs,
   FCF margin, R&D intensity). Statement-derived ratios are currency-agnostic (numerator and
   denominator share a currency), so they are safe even when statements and price differ in
   currency.

Statement-derived values fill gaps and act as fallbacks when Yahoo's precomputed value is
missing.
"""

from __future__ import annotations

from typing import Any

from ..models import Financials, Ratios
from . import finutils as F

# Plausibility bounds: Yahoo occasionally returns currency-mismatched multiples
# (e.g. INFY EV/EBITDA ~ 975 because EV is INR but EBITDA is USD). Values outside these
# bounds are treated as unknown rather than trusted.
_BOUNDS: dict[str, tuple[float, float]] = {
    "pe": (0.0, 500.0),
    "forward_pe": (0.0, 500.0),
    "pb": (0.0, 100.0),
    "ev_ebitda": (0.0, 100.0),
    "price_to_sales": (0.0, 100.0),
    "peg": (-10.0, 20.0),
}


def _from_info(info: dict[str, Any]) -> dict[str, float | None]:
    def g(key: str) -> float | None:
        v = info.get(key)
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    def bounded(name: str, value: float | None) -> float | None:
        if value is None:
            return None
        lo, hi = _BOUNDS[name]
        return value if lo < value <= hi else None

    d2e = g("debtToEquity")
    return {
        "pe": bounded("pe", g("trailingPE")),
        "forward_pe": bounded("forward_pe", g("forwardPE")),
        "pb": bounded("pb", g("priceToBook")),
        "peg": bounded("peg", g("trailingPegRatio") or g("pegRatio")),
        "ev_ebitda": bounded("ev_ebitda", g("enterpriseToEbitda")),
        "price_to_sales": bounded("price_to_sales", g("priceToSalesTrailing12Months")),
        # Yahoo's dividendYield is inconsistent/occasionally garbage; keep only realistic
        # equity yields (<=15%) and drop anomalies.
        "dividend_yield": (lambda y: y if (y is not None and 0 <= y <= 0.15) else None)(g("dividendYield")),
        "roe": g("returnOnEquity"),
        "roa": g("returnOnAssets"),
        "gross_margin": g("grossMargins"),
        "operating_margin": g("operatingMargins"),
        "net_margin": g("profitMargins"),
        # Yahoo reports debtToEquity as a percentage -> convert to a plain ratio.
        "debt_to_equity": (d2e / 100.0) if d2e is not None else None,
        "current_ratio": g("currentRatio"),
        "quick_ratio": g("quickRatio"),
        "revenue_growth_yoy": g("revenueGrowth"),
        "earnings_growth_yoy": g("earningsGrowth"),
        "beta": g("beta"),
        "fcf": g("freeCashflow"),
    }


def _tax_rate(inc_values: dict[str, float | None]) -> float:
    rate = F.pick(inc_values, *F.TAX_RATE)
    if rate is not None and 0 <= rate <= 1:
        return rate
    tax = F.pick(inc_values, *F.TAX_PROVISION)
    pretax = F.pick(inc_values, *F.PRETAX_INCOME)
    r = F.safe_div(tax, pretax)
    if r is not None and 0 <= r <= 1:
        return r
    return 0.25  # sensible default effective tax rate


def _from_statements(fin: Financials) -> dict[str, float | None]:
    inc = F.latest(fin.income_statement)
    bal = F.latest(fin.balance_sheet)
    cf = F.latest(fin.cash_flow)
    out: dict[str, float | None] = {}

    revenue = F.pick(inc, *F.REVENUE)
    ebit = F.pick(inc, *F.EBIT)
    ebitda = F.pick(inc, *F.EBITDA)
    net_income = F.pick(inc, *F.NET_INCOME)
    gross = F.pick(inc, *F.GROSS_PROFIT)
    op_income = F.pick(inc, *F.OPERATING_INCOME)
    interest = F.pick(inc, *F.INTEREST_EXPENSE)
    randd = F.pick(inc, *F.RANDD)

    total_assets = F.pick(bal, *F.TOTAL_ASSETS)
    cur_assets = F.pick(bal, *F.CURRENT_ASSETS)
    cur_liab = F.pick(bal, *F.CURRENT_LIABILITIES)
    invested_capital = F.pick(bal, *F.INVESTED_CAPITAL)
    equity = F.pick(bal, *F.EQUITY)
    inventory = F.pick(bal, *F.INVENTORY)

    # Margins (fallbacks; Yahoo values preferred upstream)
    out["gross_margin"] = F.safe_div(gross, revenue)
    out["operating_margin"] = F.safe_div(op_income, revenue)
    out["net_margin"] = F.safe_div(net_income, revenue)

    # Returns & liquidity fallbacks (currency-agnostic)
    out["roe"] = F.safe_div(net_income, equity)
    out["roa"] = F.safe_div(net_income, total_assets)
    out["current_ratio"] = F.safe_div(cur_assets, cur_liab)
    if cur_assets is not None and inventory is not None and cur_liab:
        out["quick_ratio"] = (cur_assets - inventory) / cur_liab
    else:
        out["quick_ratio"] = None
    out["debt_to_equity"] = F.safe_div(F.pick(bal, *F.TOTAL_DEBT), equity)

    # ROCE = EBIT / (Total Assets - Current Liabilities)
    capital_employed = None
    if total_assets is not None and cur_liab is not None:
        capital_employed = total_assets - cur_liab
    out["roce"] = F.safe_div(ebit, capital_employed)

    # ROIC = EBIT * (1 - tax) / Invested Capital
    if ebit is not None and invested_capital:
        out["roic"] = (ebit * (1 - _tax_rate(inc))) / invested_capital
    else:
        out["roic"] = None

    # Interest coverage = EBIT / Interest Expense (capped to avoid absurd values)
    cov = F.safe_div(ebit, abs(interest) if interest is not None else None)
    out["interest_coverage"] = min(cov, 999.0) if cov is not None else None

    # R&D intensity
    out["rd_intensity"] = F.safe_div(randd, revenue)

    # Growth (currency-agnostic)
    rev_series = F.series(fin.income_statement, *F.REVENUE)
    eps_series = F.series(fin.income_statement, *F.DILUTED_EPS)
    ni_series = F.series(fin.income_statement, *F.NET_INCOME)
    out["revenue_growth_yoy"] = F.yoy(rev_series)
    out["revenue_cagr_3y"] = F.cagr(rev_series)
    out["earnings_growth_yoy"] = F.yoy(ni_series)
    out["eps_cagr_3y"] = F.cagr(eps_series) or F.cagr(ni_series)

    # Cash flow
    fcf = F.pick(cf, *F.FREE_CASH_FLOW)
    if fcf is None:
        ocf = F.pick(cf, *F.OPERATING_CASH_FLOW)
        capex = F.pick(cf, *F.CAPEX)
        if ocf is not None and capex is not None:
            fcf = ocf + capex  # capex is reported negative
    out["fcf"] = fcf
    out["fcf_margin"] = F.safe_div(fcf, revenue)
    ocf = F.pick(cf, *F.OPERATING_CASH_FLOW)
    out["ocf_to_ebitda"] = F.safe_div(ocf, ebitda)

    return out


def compute_ratios(
    symbol: str,
    info: dict[str, Any] | None = None,
    financials: Financials | None = None,
) -> Ratios:
    """Build a Ratios object, preferring Yahoo's precomputed values and filling gaps."""
    from ..sources import data

    if info is None:
        info = data.get_info(symbol)
    if financials is None:
        financials = data.get_financials(symbol)

    merged: dict[str, Any] = {}
    stmt = _from_statements(financials)
    inf = _from_info(info)
    # Start with statement-derived, then let non-None Yahoo values take precedence.
    for key, val in stmt.items():
        merged[key] = val
    for key, val in inf.items():
        if val is not None:
            merged[key] = val
        else:
            merged.setdefault(key, None)

    merged["ticker"] = symbol.upper()
    merged["currency"] = info.get("financialCurrency") or info.get("currency")
    return Ratios(**merged)
