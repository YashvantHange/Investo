"""Shareholding-pattern tests: symbol resolver, schema-tolerant parsers, observations,
Yahoo fallback and the disabled path — all with mocked network (no live NSE/BSE calls)."""

import pytest

import investo.sources.india_holdings as ih
from investo.analysis.ownership import _annotate, shareholding_pattern
from investo.models import HolderBreakdown, ShareholdingPattern
from investo.sources.india_holdings import parse_bse, parse_nse
from investo.sources.india_symbols import bse_scrip_code, nse_symbol


def test_scrip_code_resolution():
    assert bse_scrip_code("RELIANCE.NS") == "500325"
    assert bse_scrip_code("500325.BO") == "500325"  # code embedded in the .BO ticker
    assert bse_scrip_code("UNLISTEDNAME.NS") is None
    assert nse_symbol("RELIANCE.NS") == "RELIANCE"


def test_to_pct_coercion():
    assert ih._to_pct(50.3) == 0.503
    assert ih._to_pct("50.3%") == 0.503
    assert ih._to_pct(0.5) == 0.5
    assert ih._to_pct("n/a") is None
    assert ih._to_pct(True) is None  # bool is not a percentage


def test_parse_nse_is_schema_tolerant():
    payload = {"data": [
        {"date": "2026-03-31", "promoterAndPromoterGroup": 50.3, "fiiHolding": 18.9,
         "diiHolding": 12.1, "publicHolding": 18.7, "pledgePct": 0.0},
    ]}
    rows = parse_nse(payload)
    assert len(rows) == 1
    assert rows[0].promoter == pytest.approx(0.503)
    assert rows[0].fii == pytest.approx(0.189)
    assert rows[0].dii == pytest.approx(0.121)
    assert rows[0].provenance and "NSE" in rows[0].provenance.source


def test_parse_bse_table_envelope():
    rows = parse_bse({"Table": [{"QTR_ID": "2026-03", "PromoterHolding": "50.3",
                                 "PublicHolding": "49.7"}]})
    assert rows
    assert rows[0].promoter == pytest.approx(0.503)
    assert rows[0].public == pytest.approx(0.497)


def test_annotate_generates_smart_observations_and_signal():
    hist = [
        HolderBreakdown(period="2026-03-31", promoter=0.503, fii=0.189, dii=0.121,
                        public=0.187, promoter_pledge=0.0),
        HolderBreakdown(period="2025-12-31", promoter=0.501, fii=0.199, dii=0.115,
                        public=0.185, promoter_pledge=0.0),
    ]
    pat = ShareholdingPattern(ticker="X", source="nse", latest=hist[0], history=hist)
    _annotate(pat)
    joined = " ".join(pat.observations)
    assert "FII reducing" in joined and "⚠" in joined
    assert "DII increasing" in joined
    assert "Zero promoter pledge" in joined
    assert pat.ownership_signal is not None
    assert pat.evidence is not None and pat.evidence.confidence is not None


def test_rising_pledge_is_cautionary():
    hist = [
        HolderBreakdown(period="q2", promoter=0.5, promoter_pledge=0.30),
        HolderBreakdown(period="q1", promoter=0.5, promoter_pledge=0.0),
    ]
    pat = ShareholdingPattern(ticker="X", source="nse", latest=hist[0], history=hist)
    _annotate(pat)
    assert pat.ownership_signal in ("cautious", "bearish")


def test_yahoo_fallback_when_india_source_empty(monkeypatch):
    from investo.sources import data
    monkeypatch.setattr(data, "market_of_symbol", lambda s: "IN")
    monkeypatch.setattr(ih, "fetch_shareholding", lambda s: None)
    monkeypatch.setattr(data, "get_info",
                        lambda s: {"heldPercentInsiders": 0.51, "heldPercentInstitutions": 0.29})
    monkeypatch.setattr(data, "get_holders", lambda s: {"institutional_top": [{"Holder": "LIC"}]})

    pat = shareholding_pattern("RELIANCE.NS")
    assert pat.source == "yahoo"
    assert pat.latest is not None and pat.latest.promoter == 0.51
    assert pat.latest.public is not None and abs(pat.latest.public - 0.20) < 1e-9
    assert pat.top_institutions == [{"Holder": "LIC"}]
    assert pat.note is not None  # honest caveat about missing granularity


def test_fetch_shareholding_disabled_returns_none(monkeypatch):
    stub = type("C", (), {"enable_india_holdings": False, "india_holdings_min_interval": 0.0})()
    monkeypatch.setattr(ih, "CONFIG", stub)
    assert ih.fetch_shareholding("RELIANCE.NS") is None
