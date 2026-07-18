"""Ratio computation from statement fixtures (no network)."""

from investo.analysis.ratios import compute_ratios
from investo.models import FinancialPeriod, Financials


def _financials() -> Financials:
    return Financials(
        ticker="X.NS", currency="INR", period_type="annual",
        income_statement=[
            FinancialPeriod(period="2024", values={"Total Revenue": 1000, "Gross Profit": 400,
                                                    "Operating Income": 220, "EBIT": 220, "EBITDA": 260,
                                                    "Net Income": 150, "Interest Expense": 10,
                                                    "Pretax Income": 200, "Tax Provision": 50}),
            FinancialPeriod(period="2023", values={"Total Revenue": 900, "Net Income": 130}),
            FinancialPeriod(period="2022", values={"Total Revenue": 800, "Net Income": 110}),
        ],
        balance_sheet=[
            FinancialPeriod(period="2024", values={"Total Assets": 2000, "Current Assets": 600,
                                                   "Current Liabilities": 300, "Total Debt": 200,
                                                   "Invested Capital": 800, "Stockholders Equity": 900,
                                                   "Inventory": 100}),
        ],
        cash_flow=[FinancialPeriod(period="2024", values={"Free Cash Flow": 120})],
    )


def test_margins_and_returns_from_statements():
    r = compute_ratios("X.NS", info={}, financials=_financials())
    assert abs(r.gross_margin - 0.40) < 1e-6      # 400 / 1000
    assert abs(r.operating_margin - 0.22) < 1e-6  # 220 / 1000
    assert abs(r.net_margin - 0.15) < 1e-6        # 150 / 1000
    assert abs(r.roe - (150 / 900)) < 1e-6        # NI / equity
    # ROCE = EBIT / (assets - current liabilities) = 220 / (2000-300)
    assert abs(r.roce - (220 / 1700)) < 1e-6


def test_growth_and_liquidity():
    r = compute_ratios("X.NS", info={}, financials=_financials())
    assert abs(r.revenue_growth_yoy - (1000 - 900) / 900) < 1e-6
    assert abs(r.revenue_cagr_3y - ((1000 / 800) ** 0.5 - 1)) < 1e-6
    assert abs(r.current_ratio - 2.0) < 1e-6           # 600 / 300
    assert abs(r.debt_to_equity - (200 / 900)) < 1e-6  # from statements when Yahoo missing


def test_interest_coverage_and_fcf_margin():
    r = compute_ratios("X.NS", info={}, financials=_financials())
    assert abs(r.interest_coverage - (220 / 10)) < 1e-6
    assert abs(r.fcf_margin - (120 / 1000)) < 1e-6


def test_yahoo_info_overrides_statement_values():
    # Yahoo's precomputed ratios (currency-consistent) win over statement-derived ones.
    info = {"trailingPE": 18.5, "priceToBook": 3.2, "debtToEquity": 25.0}  # D/E is a percent
    r = compute_ratios("X.NS", info=info, financials=_financials())
    assert r.pe == 18.5
    assert r.pb == 3.2
    assert abs(r.debt_to_equity - 0.25) < 1e-6  # 25.0% -> 0.25 ratio


def test_implausible_multiples_dropped():
    r = compute_ratios("X.NS", info={"enterpriseToEbitda": 975.0, "trailingPE": 12.0}, financials=_financials())
    assert r.ev_ebitda is None   # 975 is out of bounds -> treated as unknown
    assert r.pe == 12.0


# --------------------------------------------------------------------------------------
# Dividend yield: yfinance reports these fields on different scales, and dividendYield in
# particular flipped to a *percent* (1.61 == 1.61%) — the old <=0.15 fraction filter nulled
# every real yield. Field shapes below are the actual values fetched for these names.
# --------------------------------------------------------------------------------------
def test_dividend_yield_prefers_the_unambiguous_fraction_field():
    # trailingAnnualDividendYield is a decimal fraction (HDFC Bank ~1.6%).
    r = compute_ratios("HDFCBANK.NS", info={
        "dividendYield": 1.61, "trailingAnnualDividendYield": 0.016083,
        "dividendRate": 13.0, "currentPrice": 819.6}, financials=_financials())
    assert r.dividend_yield is not None
    assert abs(r.dividend_yield - 0.0161) < 1e-4  # ~1.6%, NOT nulled


def test_percent_scale_dividend_yield_is_normalized_not_dropped():
    # Only dividendYield present, on the percent scale. Must become a 5.7% fraction, not None.
    r = compute_ratios("ITC.NS", info={"dividendYield": 5.73}, financials=_financials())
    assert r.dividend_yield is not None
    assert abs(r.dividend_yield - 0.0573) < 1e-4


def test_low_yield_is_kept_not_dropped():
    # AAPL ~0.3% — the old filter kept only <0.15% and this survived by luck; confirm it holds.
    r = compute_ratios("AAPL", info={
        "dividendYield": 0.32, "trailingAnnualDividendYield": 0.0031}, financials=_financials())
    assert r.dividend_yield is not None
    assert abs(r.dividend_yield - 0.0031) < 1e-4


def test_dividend_rate_over_price_is_the_fallback():
    r = compute_ratios("X.NS", info={"dividendRate": 22.0, "currentPrice": 427.65},
                       financials=_financials())
    assert r.dividend_yield is not None
    assert abs(r.dividend_yield - 0.0514) < 1e-3  # 22/427.65


def test_no_dividend_is_none():
    r = compute_ratios("NODIV.NS", info={"trailingPE": 30.0}, financials=_financials())
    assert r.dividend_yield is None


def test_garbage_dividend_yield_is_rejected():
    # A 300% "yield" is an anomaly, not a real payout.
    r = compute_ratios("X.NS", info={"trailingAnnualDividendYield": 3.0}, financials=_financials())
    assert r.dividend_yield is None
