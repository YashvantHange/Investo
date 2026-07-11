"""Small shared helpers for reading financial statements and computing safe ratios."""

from __future__ import annotations

from ..models import FinancialPeriod


def safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None:
        return None
    if denominator == 0:
        return None
    return numerator / denominator


def pick(values: dict[str, float | None], *keys: str) -> float | None:
    """Return the first non-None value among the given line-item keys."""
    for k in keys:
        v = values.get(k)
        if v is not None:
            return v
    return None


def latest(periods: list[FinancialPeriod]) -> dict[str, float | None]:
    """Most-recent period's values (yfinance returns newest first)."""
    return periods[0].values if periods else {}


def series(periods: list[FinancialPeriod], *keys: str) -> list[float | None]:
    """A line item across periods, newest-first."""
    return [pick(p.values, *keys) for p in periods]


def cagr(newest_first: list[float | None]) -> float | None:
    """Compound annual growth rate from a newest-first series of positive values."""
    vals = [v for v in newest_first if v is not None]
    if len(vals) < 2:
        return None
    latest_v, oldest_v = vals[0], vals[-1]
    years = len(vals) - 1
    if oldest_v is None or oldest_v <= 0 or latest_v is None or latest_v <= 0 or years <= 0:
        return None
    return (latest_v / oldest_v) ** (1.0 / years) - 1.0


def yoy(newest_first: list[float | None]) -> float | None:
    """Year-over-year growth between the two most recent periods."""
    vals = newest_first
    if len(vals) < 2:
        return None
    cur, prev = vals[0], vals[1]
    if cur is None or prev is None or prev == 0:
        return None
    return (cur - prev) / abs(prev)


# Common line-item aliases across yfinance schemas -------------------------------------
REVENUE = ("Total Revenue", "Operating Revenue")
NET_INCOME = ("Net Income", "Net Income Common Stockholders", "Net Income Continuous Operations")
GROSS_PROFIT = ("Gross Profit",)
OPERATING_INCOME = ("Operating Income", "Total Operating Income As Reported")
EBIT = ("EBIT", "Operating Income")
EBITDA = ("EBITDA", "Normalized EBITDA")
INTEREST_EXPENSE = ("Interest Expense", "Interest Expense Non Operating")
PRETAX_INCOME = ("Pretax Income",)
TAX_PROVISION = ("Tax Provision",)
TAX_RATE = ("Tax Rate For Calcs",)
DILUTED_EPS = ("Diluted EPS", "Basic EPS")
DILUTED_SHARES = ("Diluted Average Shares", "Basic Average Shares", "Ordinary Shares Number")
RANDD = ("Research And Development",)

TOTAL_ASSETS = ("Total Assets",)
CURRENT_ASSETS = ("Current Assets",)
CURRENT_LIABILITIES = ("Current Liabilities",)
TOTAL_DEBT = ("Total Debt",)
EQUITY = ("Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest")
INVESTED_CAPITAL = ("Invested Capital",)
INVENTORY = ("Inventory",)
CASH = ("Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments")

FREE_CASH_FLOW = ("Free Cash Flow",)
OPERATING_CASH_FLOW = ("Operating Cash Flow", "Cash Flow From Continuing Operating Activities")
CAPEX = ("Capital Expenditure", "Capital Expenditure Reported")
DIVIDENDS_PAID = ("Cash Dividends Paid", "Common Stock Dividend Paid")
REPURCHASE = ("Repurchase Of Capital Stock", "Common Stock Payments")
