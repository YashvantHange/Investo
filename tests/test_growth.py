"""Growth-outlook tests (no network): curated engine, derived fallback, blend, confidence."""

import pytest

from investo.analysis import growth as gmod
from investo.analysis.growth import growth_outlook
from investo.data import growth_engines
from investo.models import IndustryIntelligence, Ratios


@pytest.fixture(autouse=True)
def _no_analyst(monkeypatch):
    # growth_outlook calls Yahoo for analyst estimates; stub it out for deterministic tests.
    from investo.sources import data
    monkeypatch.setattr(data, "get_growth_estimates",
                        lambda s: {"earnings_growth": None, "revenue_growth": None})


def _industry(cagr="~5-7% (est.)"):
    return IndustryIntelligence(ticker="X", sector="Energy", industry_cagr=cagr,
                                demand_drivers=["Demand A", "Demand B", "Demand C"],
                                risks=["Risk A"], future_demand="Steady")


def test_growth_yaml_parses_and_contributions_sum_to_one():
    g = growth_engines()
    assert "RELIANCE.NS" in g["by_ticker"]
    for _, entry in g["by_ticker"].items():
        total = sum(d.get("contribution_pct", 0) for d in entry["drivers"])
        assert abs(total - 1.0) < 0.02


def test_curated_engine_used_for_reliance():
    g = growth_outlook("RELIANCE.NS", ratios=Ratios(ticker="RELIANCE.NS", roe=0.09),
                       info={"payoutRatio": 0.1}, industry=_industry(), sector="Energy")
    assert g.primary_engine and "Jio" in g.primary_engine
    assert g.drivers and g.drivers[0].source == "curated"
    assert g.drivers[0].rank == 1
    assert g.catalysts and g.catalysts[0].year is not None


def test_derived_fallback_for_uncurated_name():
    g = growth_outlook("NOSUCH.NS", ratios=Ratios(ticker="NOSUCH.NS", roe=0.12),
                       info={}, industry=_industry(), sector="Nonexistent Sector")
    assert g.drivers  # falls back to industry demand drivers
    assert all(d.source in ("industry", "derived") for d in g.drivers)


def test_sustainable_growth_math():
    # g = ROE * (1 - payout)
    assert gmod._sustainable_growth(0.20, 0.25) == pytest.approx(0.15)
    assert gmod._sustainable_growth(0.20, None) == pytest.approx(0.20)  # no payout -> full retention
    assert gmod._sustainable_growth(None, 0.3) is None


def test_signal_thresholds():
    assert gmod._signal(0.20) == "strong"
    assert gmod._signal(0.10) == "moderate"
    assert gmod._signal(0.03) == "weak"
    assert gmod._signal(None) is None


def test_parse_cagr_midpoint():
    assert gmod._parse_cagr("~5-7% (est.)") == pytest.approx(0.06)
    assert gmod._parse_cagr("~10-12% FY24-30") == pytest.approx(0.11)
    assert gmod._parse_cagr(None) is None
    assert gmod._parse_cagr("no numbers") is None


def test_confidence_is_tempered_by_agreement():
    # Wide spread between estimates -> lower agreement -> lower confidence.
    tight = gmod._agreement(0.06, 0.07)
    wide = gmod._agreement(-0.10, 0.30)
    assert tight > wide
    assert 0.55 <= wide <= 1.0 and 0.55 <= tight <= 1.0


def test_blended_band_and_evidence_present():
    g = growth_outlook("RELIANCE.NS", ratios=Ratios(ticker="RELIANCE.NS", roe=0.09,
                       revenue_cagr_3y=0.06), info={"payoutRatio": 0.1}, industry=_industry(),
                       sector="Energy")
    assert g.blended_5y_low is not None and g.blended_5y_high is not None
    assert g.blended_5y_low <= g.blended_5y_high
    assert g.evidence is not None and g.evidence.confidence is not None
