"""Industry-framing tests (no network).

Yahoo calls KPIT "Technology / Information Technology Services", which is true but useless: it
frames an automotive ER&D firm as an IT outsourcer and points the whole analysis at the wrong
demand drivers, the wrong CAGR and the wrong risks.
"""

import pytest

from investo.analysis.industry import get_industry_intelligence, industry_outlook
from investo.sources import data


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    monkeypatch.setattr(data, "get_info", lambda symbol: {})


def _info(monkeypatch, **fields):
    monkeypatch.setattr(data, "get_info", lambda symbol: dict(fields))


def test_curated_group_reframes_yahoos_generic_classification(monkeypatch):
    _info(monkeypatch, sector="Technology", industry="Information Technology Services")
    intel = get_industry_intelligence("KPITTECH.NS")

    assert intel.peer_group == "Automotive ER&D"
    assert intel.basis == "curated"
    joined = " ".join(intel.sub_domains).lower()
    assert "software-defined" in joined
    assert "outsourcing" not in joined  # the generic Technology framing must not win


def test_yahoos_raw_industry_string_is_preserved_not_overwritten(monkeypatch):
    # It's a fact about how the exchange classifies the company. Hiding the disagreement
    # would be worse than showing it.
    _info(monkeypatch, sector="Technology", industry="Information Technology Services")
    intel = get_industry_intelligence("KPITTECH.NS")
    assert intel.industry == "Information Technology Services"
    assert intel.sector == "Technology"


def test_group_drives_drivers_risks_and_cagr(monkeypatch):
    _info(monkeypatch, sector="Technology", industry="Information Technology Services")
    intel = get_industry_intelligence("KPITTECH.NS")
    assert any("software-defined" in d.lower() for d in intel.demand_drivers)
    assert any("oem" in r.lower() for r in intel.risks)
    assert "SDV" in (intel.industry_cagr or "")
    assert intel.as_of  # curated framing is dated so a reader can judge staleness


def test_company_without_a_group_keeps_the_sector_framing(monkeypatch):
    # TCS really is an IT services company; the sector note is right for it.
    _info(monkeypatch, sector="Technology", industry="Information Technology Services")
    intel = get_industry_intelligence("TCS.NS")
    assert intel.peer_group == "IT Services"
    assert any("IT services" in d for d in intel.sub_domains)


def test_sector_fallback_says_it_is_a_guess(monkeypatch):
    _info(monkeypatch, sector="Consumer Cyclical", industry="Auto Parts")
    intel = get_industry_intelligence("SOMENEWCO.NS")
    assert intel.basis == "sector-fallback"
    assert intel.peer_group == "Auto Components"
    assert intel.note and "Indicative only" in intel.note


def test_unknown_sector_and_no_group_admits_it(monkeypatch):
    _info(monkeypatch, sector="Llama Farming", industry="Llama Farming")
    intel = get_industry_intelligence("LLAMA.NS")
    assert intel.basis == "none"
    assert intel.source == "unknown"
    assert intel.note and "No curated intelligence" in intel.note


def test_industry_outlook_prefers_the_group_over_the_sector(monkeypatch):
    _info(monkeypatch, sector="Technology", industry="Information Technology Services")
    outlook, cagr = industry_outlook("KPITTECH.NS")
    assert outlook == "high"
    assert "SDV" in (cagr or "")  # the auto_erd CAGR, not the generic Technology one
