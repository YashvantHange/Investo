"""Fundamentals-trend tests (no network): directions, health grades, overall."""

from investo.analysis import trends as tmod
from investo.analysis.trends import fundamental_trend
from investo.models import FinancialPeriod, Financials


def _fin(rows):
    """rows: (period, revenue, net_income, eps, equity), newest-first."""
    inc = [FinancialPeriod(period=p, values={"Total Revenue": rev, "Net Income": ni,
                                             "Diluted EPS": eps}) for p, rev, ni, eps, eq in rows]
    bal = [FinancialPeriod(period=p, values={"Stockholders Equity": eq}) for p, rev, ni, eps, eq in rows]
    return Financials(ticker="X", income_statement=inc, balance_sheet=bal)


def test_steadily_growing_company_is_excellent():
    fin = _fin([("2025", 1400, 300, 6.0, 1000), ("2024", 1250, 260, 5.2, 950),
                ("2023", 1100, 220, 4.4, 900), ("2022", 950, 180, 3.6, 860)])
    ft = fundamental_trend("X", financials=fin)
    rev = next(m for m in ft.metrics if m.name == "Revenue")
    assert rev.directions == ["up", "up", "up"]
    assert rev.health == "Excellent"
    assert ft.overall_health in ("Excellent", "Good")


def test_directions_detect_flat_and_down():
    # revenue: 1000 -> 1005 (flat) -> 900 (down, newest-first order)
    fin = _fin([("2025", 900, 50, 1.0, 500), ("2024", 1005, 60, 1.2, 500),
                ("2023", 1000, 70, 1.4, 500)])
    rev = next(m for m in fundamental_trend("X", financials=fin).metrics if m.name == "Revenue")
    assert rev.directions[0] == "down"   # 900 vs 1005
    assert rev.directions[1] == "flat"   # 1005 vs 1000


def test_metric_needs_two_points():
    fin = _fin([("2025", 1000, 100, 2.0, 500)])
    ft = fundamental_trend("X", financials=fin)
    # single period -> not enough for any trend
    assert all(len(m.values) >= 2 for m in ft.metrics) or ft.metrics == []


def test_direction_helper():
    assert tmod._directions([110.0, 100.0]) == ["up"]
    assert tmod._directions([100.0, 110.0]) == ["down"]
    assert tmod._directions([100.5, 100.0]) == ["flat"]
    assert tmod._directions([None, 100.0]) == ["flat"]


def test_overall_health_none_when_no_metrics():
    ft = fundamental_trend("X", financials=Financials(ticker="X"))
    assert ft.overall_health is None
    assert ft.note is not None


def test_health_grade_reflects_direction_ratio():
    # mostly-down series -> weak/poor health
    fin = _fin([("2025", 700, 40, 0.8, 500), ("2024", 850, 60, 1.1, 520),
                ("2023", 1000, 90, 1.6, 560), ("2022", 1100, 110, 2.0, 600)])
    rev = next(m for m in fundamental_trend("X", financials=fin).metrics if m.name == "Revenue")
    assert rev.directions.count("down") >= 2
    assert rev.health in ("Weak", "Poor")
