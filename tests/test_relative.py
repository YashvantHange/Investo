"""Relative-to-industry tests (no network)."""

from investo.analysis.relative import relative_comparison
from investo.models import PeerComparison, PeerRow, Ratios


def _peers() -> PeerComparison:
    return PeerComparison(ticker="SUB.NS", peers=[
        PeerRow(ticker="SUB.NS", roe=0.30, net_margin=0.20, pe=25.0, pb=5.0, debt_to_equity=0.2,
                revenue_growth_yoy=0.20, operating_margin=0.25),
        PeerRow(ticker="A.NS", roe=0.10, net_margin=0.08, pe=10.0, pb=1.0, debt_to_equity=0.6,
                revenue_growth_yoy=0.05, operating_margin=0.10),
        PeerRow(ticker="B.NS", roe=0.12, net_margin=0.09, pe=12.0, pb=1.2, debt_to_equity=0.5,
                revenue_growth_yoy=0.06, operating_margin=0.11),
        PeerRow(ticker="C.NS", roe=0.15, net_margin=0.10, pe=14.0, pb=1.4, debt_to_equity=0.4,
                revenue_growth_yoy=0.07, operating_margin=0.12),
    ])


def test_high_roe_is_top_quartile():
    rc = relative_comparison("SUB.NS", _peers())
    roe = next(m for m in rc.metrics if m.name == "ROE")
    assert roe.better is True
    assert roe.percentile == 1.0  # beats every peer
    assert roe.industry is not None and roe.company > roe.industry


def test_expensive_pe_is_unfavourable():
    rc = relative_comparison("SUB.NS", _peers())
    pe = next(m for m in rc.metrics if m.name == "P/E")
    # Lower P/E is better; the subject is the most expensive -> bottom, not "better".
    assert pe.better is False
    assert pe.percentile == 0.0


def test_low_debt_is_favourable_even_though_lower_is_better():
    rc = relative_comparison("SUB.NS", _peers())
    de = next(m for m in rc.metrics if m.name == "Debt/Equity")
    assert de.better is True  # lowest leverage in the set
    assert de.percentile == 1.0


def test_percentiles_bounded_and_peercount():
    rc = relative_comparison("SUB.NS", _peers())
    assert rc.peer_count == 4
    assert all(0.0 <= m.percentile <= 1.0 for m in rc.metrics)
    assert rc.evidence is not None and rc.evidence.confidence is not None


def test_falls_back_to_ratios_when_subject_not_in_peers():
    peers = _peers()
    peers.peers = peers.peers[1:]  # drop the subject row
    rc = relative_comparison("SUB.NS", peers, Ratios(ticker="SUB.NS", roe=0.30))
    roe = next((m for m in rc.metrics if m.name == "ROE"), None)
    assert roe is not None and roe.company == 0.30


def test_insufficient_peers_returns_note():
    rc = relative_comparison("SUB.NS", PeerComparison(ticker="SUB.NS", peers=[]))
    assert rc.metrics == []
    assert rc.note is not None
