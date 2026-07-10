"""Ticker-resolution ranking tests (no network)."""

from investo.models import TickerCandidate
from investo.resolve import _relevance_tier, rank_candidates


def test_relevance_beats_unrelated_name():
    # "Infosys" must not resolve to "HCL Infosystems"; the exact-name ADR should win.
    cands = [
        TickerCandidate(symbol="HCL-INSYS.NS", name="HCL INFOSYSTEMS LTD", market="IN",
                        quote_type="EQUITY", score=20002),
        TickerCandidate(symbol="INFY", name="Infosys Limited", market="US",
                        quote_type="EQUITY", score=20035),
    ]
    ranked = rank_candidates(cands, "IN", "Infosys")
    assert ranked[0].symbol == "INFY"


def test_nse_preferred_among_equally_relevant():
    cands = [
        TickerCandidate(symbol="HDB", name="HDFC Bank Limited", market="US",
                        quote_type="EQUITY", score=20019),
        TickerCandidate(symbol="HDFCBANK.NS", name="HDFC BANK LTD", market="IN",
                        quote_type="EQUITY", score=20003),
        TickerCandidate(symbol="HDFCBANK.BO", name="HDFC BANK LTD.", market="IN",
                        quote_type="EQUITY", score=20001),
    ]
    ranked = rank_candidates(cands, "IN", "HDFC Bank")
    assert ranked[0].symbol == "HDFCBANK.NS"


def test_relevance_tiers():
    exact = TickerCandidate(symbol="INFY", name="Infosys Limited")
    partial = TickerCandidate(symbol="INFYX", name="Infosys Digital Services Ltd")
    unrelated = TickerCandidate(symbol="HCL-INSYS.NS", name="HCL Infosystems Ltd")
    assert _relevance_tier("Infosys", exact) == 0
    assert _relevance_tier("Infosys", partial) <= 1
    assert _relevance_tier("Infosys", unrelated) == 3


def test_equities_preferred_over_non_equity():
    cands = [
        TickerCandidate(symbol="ZTAM.SI", name="Tata Motors FUT", market="OTHER",
                        quote_type="FUTURE", score=20000),
        TickerCandidate(symbol="TMCV.NS", name="TATA MOTORS LIMITED", market="IN",
                        quote_type="EQUITY", score=20003),
    ]
    ranked = rank_candidates(cands, "IN", "Tata Motors")
    assert ranked[0].symbol == "TMCV.NS"
