"""Buffett checklist tests (no network): weighting, unknown handling, trend."""

from investo.analysis.buffett import buffett_checklist
from investo.models import (
    DCFResult,
    FinancialPeriod,
    Financials,
    Management,
    MoatSignals,
    Ratios,
)


def _financials(rows) -> Financials:
    inc = [FinancialPeriod(period=p, values={"Net Income": ni, "Total Revenue": rev}) for p, ni, rev, eq in rows]
    bal = [FinancialPeriod(period=p, values={"Stockholders Equity": eq}) for p, ni, rev, eq in rows]
    return Financials(ticker="X", income_statement=inc, balance_sheet=bal)


_ROWS = [
    ("2025-03-31", 300, 1000, 1000),
    ("2024-03-31", 260, 900, 950),
    ("2023-03-31", 230, 820, 900),
    ("2022-03-31", 200, 750, 880),
]


def _run(**over):
    r = Ratios(ticker="X", roe=over.get("roe", 0.28), roic=over.get("roic", 0.20),
               debt_to_equity=over.get("de", 0.2), interest_coverage=over.get("cov", 20.0),
               fcf_margin=over.get("fcfm", 0.15), ocf_to_ebitda=over.get("ocf", 1.0))
    dcf = DCFResult(ticker="X", margin_of_safety=over.get("mos"), note=over.get("dcf_note"))
    moat = MoatSignals(ticker="X", moat_score=over.get("moat", 7.0))
    mgmt = Management(ticker="X", promoter_holding=over.get("prom", 0.55))
    return buffett_checklist("X", ratios=r, dcf=dcf, moat=moat, management=mgmt,
                             financials=_financials(_ROWS), info={}, sector="Technology")


def test_high_quality_scores_well():
    b = _run(mos=0.3)
    assert b.weighted_score is not None and b.weighted_score >= 80
    assert b.verdict == "Strong Buffett fit"
    assert b.applicable_count == 7  # MoS present -> all applicable


def test_low_confidence_dcf_marks_mos_unknown_not_fail():
    b = _run(dcf_note="Low confidence: capex-heavy", mos=-5.0)
    mos = next(c for c in b.criteria if c.name == "Margin of safety")
    assert mos.status == "unknown"
    # Unknown is excluded from the weighted score rather than counted as a fail.
    assert b.applicable_count == 6
    assert "Margin of safety" in (b.evidence.missing_fields if b.evidence else [])


def test_weighted_score_renormalizes_when_unknown():
    # Everything passes except MoS is unknown -> score should be 100, not penalized.
    b = _run(dcf_note="unreliable")
    assert b.weighted_score == 100.0


def test_roe_trend_is_populated_and_verdict_present():
    b = _run(mos=0.2)
    roe = next(c for c in b.criteria if c.name == "Consistent high ROE")
    assert len(roe.trend) == len(_ROWS)
    assert roe.trend_verdict is not None


def test_financial_sector_marks_debt_unknown():
    r = Ratios(ticker="BANK", roe=0.18, roic=0.12, debt_to_equity=8.0)
    b = buffett_checklist("BANK", ratios=r, dcf=DCFResult(ticker="BANK", margin_of_safety=0.2),
                          moat=MoatSignals(ticker="BANK", moat_score=6.0),
                          management=Management(ticker="BANK", promoter_holding=0.0),
                          financials=_financials(_ROWS), info={}, sector="Banks")
    debt = next(c for c in b.criteria if c.name == "Low debt")
    assert debt.status == "unknown"


def test_every_criterion_has_reason_and_confidence():
    b = _run(mos=0.2)
    for c in b.criteria:
        assert c.reason
        assert c.confidence is not None
        assert c.provenance is not None
