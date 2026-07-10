"""Scoring-model tests (no network)."""

from investo.analysis import scoring
from investo.models import Ratios


def _good() -> Ratios:
    return Ratios(
        ticker="GOOD", roe=0.30, roce=0.35, roic=0.28, net_margin=0.20, operating_margin=0.25,
        gross_margin=0.50, fcf_margin=0.18, ocf_to_ebitda=1.0, debt_to_equity=0.1,
        interest_coverage=50.0, current_ratio=2.2, pe=15.0, pb=4.0, ev_ebitda=12.0,
        revenue_growth_yoy=0.18, revenue_cagr_3y=0.16, earnings_growth_yoy=0.20, beta=0.8,
    )


def _poor() -> Ratios:
    return Ratios(
        ticker="POOR", roe=0.03, roce=0.04, roic=0.02, net_margin=0.01, operating_margin=0.02,
        gross_margin=0.10, fcf_margin=-0.05, ocf_to_ebitda=0.4, debt_to_equity=3.0,
        interest_coverage=1.0, current_ratio=0.7, pe=80.0, pb=15.0, ev_ebitda=40.0,
        revenue_growth_yoy=-0.10, revenue_cagr_3y=-0.05, earnings_growth_yoy=-0.15, beta=1.8,
    )


def test_good_beats_poor():
    good = scoring.compute_score("GOOD", _good())
    poor = scoring.compute_score("POOR", _poor())
    assert good.total > poor.total
    assert good.total >= 65      # a strong company should score well
    assert poor.total <= 40      # a weak one should score poorly


def test_total_is_bounded_0_100():
    for r in (_good(), _poor(), Ratios(ticker="EMPTY")):
        s = scoring.compute_score("X", r)
        assert 0.0 <= s.total <= 100.0


def test_ten_buckets_without_esg_eleven_with():
    without = scoring.compute_score("X", _good())
    assert len(without.buckets) == 10
    assert without.esg_included is False

    with_esg = scoring.compute_score("X", _good(), esg_total=12.0)
    assert with_esg.esg_included is True
    assert any(b.name == "ESG" for b in with_esg.buckets)


def test_weights_sum_to_100():
    assert abs(sum(scoring.WEIGHTS.values()) - 100.0) < 1e-9


def test_verdict_thresholds():
    assert scoring._verdict(85) == "Excellent"
    assert scoring._verdict(70) == "Strong"
    assert scoring._verdict(55) == "Fair"
    assert scoring._verdict(40) == "Weak"
    assert scoring._verdict(20) == "Poor"


def test_growth_scorer_monotonic():
    low, _, _ = scoring.score_growth(Ratios(ticker="L", revenue_cagr_3y=0.02, revenue_growth_yoy=0.02))
    high, _, _ = scoring.score_growth(Ratios(ticker="H", revenue_cagr_3y=0.20, revenue_growth_yoy=0.20))
    assert high > low


def test_missing_data_is_neutral_not_zero():
    s = scoring.compute_score("X", Ratios(ticker="EMPTY"))
    # With no data every bucket falls back to neutral 0.5 -> ~50.
    assert 45 <= s.total <= 55


def test_financial_sector_excludes_debt_equity():
    r = Ratios(ticker="BANK", debt_to_equity=8.0, interest_coverage=None, current_ratio=None)
    n_fin, rat, _ = scoring.score_debt(r, sector="Financial Services")
    assert "excluded" in rat
