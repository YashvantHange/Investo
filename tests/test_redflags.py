"""Red-flag detection tests (no network)."""

from investo.analysis.redflags import detect_red_flags
from investo.models import FinancialPeriod, Financials, Ratios


def _fin(inc_rows, bal_rows=None, cf_rows=None) -> Financials:
    inc = [FinancialPeriod(period=p, values={"Total Revenue": rev, "Net Income": ni})
           for p, rev, ni in inc_rows]
    bal = [FinancialPeriod(period=p, values={"Total Debt": d}) for p, d in (bal_rows or [])]
    cf = [FinancialPeriod(period=p, values={"Free Cash Flow": f}) for p, f in (cf_rows or [])]
    return Financials(ticker="X", income_statement=inc, balance_sheet=bal, cash_flow=cf)


def test_deteriorating_company_flags_high_risk():
    fin = _fin(
        inc_rows=[("2025", 1200, 40), ("2024", 1100, 70), ("2023", 1000, 90), ("2022", 900, 100)],
        bal_rows=[("2025", 800), ("2024", 600), ("2023", 500), ("2022", 450)],
        cf_rows=[("2025", -50), ("2024", 20), ("2023", 60), ("2022", 80)])
    r = Ratios(ticker="X", debt_to_equity=1.8, interest_coverage=1.5, current_ratio=0.9, fcf=-50,
               revenue_growth_yoy=0.09, earnings_growth_yoy=-0.43)
    rep = detect_red_flags("X", ratios=r, financials=fin, info={})
    issues = {f.issue for f in rep.flags}
    assert "Revenue rising but profit falling" in issues
    assert "Debt rising" in issues
    assert "Negative free cash flow" in issues
    assert rep.risk_level in ("high", "severe")


def test_healthy_company_has_no_flags():
    fin = _fin(inc_rows=[("2025", 1400, 220), ("2024", 1200, 180), ("2023", 1000, 150)])
    r = Ratios(ticker="Y", debt_to_equity=0.2, interest_coverage=15, current_ratio=2.2, fcf=300,
               revenue_growth_yoy=0.17, earnings_growth_yoy=0.22)
    rep = detect_red_flags("Y", ratios=r, financials=fin, info={})
    assert rep.flags == []
    assert rep.risk_level == "none"
    assert rep.note is not None


def test_net_loss_is_severe():
    fin = _fin(inc_rows=[("2025", 1000, -50), ("2024", 1000, 20)])
    r = Ratios(ticker="Z", debt_to_equity=0.5)
    rep = detect_red_flags("Z", ratios=r, financials=fin, info={})
    assert any(f.severity == "severe" for f in rep.flags)
    assert rep.risk_level == "severe"


def test_missing_data_does_not_manufacture_flags():
    rep = detect_red_flags("EMPTY", ratios=Ratios(ticker="EMPTY"),
                           financials=Financials(ticker="EMPTY"), info={})
    assert rep.flags == []
    assert rep.risk_level == "none"
