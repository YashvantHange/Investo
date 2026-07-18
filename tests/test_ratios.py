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
# Net cash: cash - total debt, plus its size relative to market cap (FX-normalized so the
# statement-currency cash and trading-currency market cap are comparable).
# --------------------------------------------------------------------------------------
def _bal(cash: float, debt: float) -> Financials:
    return Financials(
        ticker="X.NS", currency="INR",
        income_statement=[FinancialPeriod(period="2024", values={"Total Revenue": 1000, "Net Income": 150})],
        balance_sheet=[FinancialPeriod(period="2024", values={
            "Cash And Cash Equivalents": cash, "Total Debt": debt, "Stockholders Equity": 900})],
        cash_flow=[],
    )


def test_net_cash_from_statements_and_market_cap():
    info = {"marketCap": 3000, "financialCurrency": "INR", "currency": "INR"}
    r = compute_ratios("X.NS", info=info, financials=_bal(cash=500, debt=200))
    assert abs(r.net_cash - 300) < 1e-6                      # 500 - 200
    assert abs(r.net_cash_to_market_cap - 0.10) < 1e-6       # 300 / 3000, FX = 1


def test_net_debt_when_debt_exceeds_cash_is_signed():
    info = {"marketCap": 1000, "financialCurrency": "INR", "currency": "INR"}
    r = compute_ratios("X.NS", info=info, financials=_bal(cash=200, debt=800))
    assert abs(r.net_cash - (-600)) < 1e-6
    assert abs(r.net_cash_to_market_cap - (-0.60)) < 1e-6


def test_net_cash_to_market_cap_is_fx_consistent(monkeypatch):
    # Statements in USD, trades in INR (the Infosys case): net cash must be converted with the
    # same FX the DCF uses before dividing by the INR market cap.
    monkeypatch.setattr("investo.sources.data.fx_rate", lambda frm, to: 80.0)
    fin = _bal(cash=1100, debt=100)             # net cash = 1000 USD
    info = {"marketCap": 800_000, "financialCurrency": "USD", "currency": "INR"}
    r = compute_ratios("INFY.NS", info=info, financials=fin)
    assert abs(r.net_cash - 1000) < 1e-6                     # statement currency (USD)
    assert abs(r.net_cash_to_market_cap - 0.10) < 1e-6       # 1000 * 80 / 800_000


def test_net_cash_ratio_none_without_market_cap():
    r = compute_ratios("X.NS", info={"financialCurrency": "INR", "currency": "INR"},
                       financials=_bal(cash=500, debt=200))
    assert r.net_cash == 300
    assert r.net_cash_to_market_cap is None
