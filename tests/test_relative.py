"""Relative-to-industry tests (no network)."""

from investo.analysis.relative import _METRIC_SPECS, relative_comparison
from investo.models import PeerComparison, PeerRow, Ratios


def _peers(basis="curated", label="Test Group") -> PeerComparison:
    return PeerComparison(ticker="SUB.NS", basis=basis, peer_group_label=label, peers=[
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


# --------------------------------------------------------------------------------------
# The reported bug. KPIT matched no peer group, so this module computed nothing — and then
# reported 0.37 confidence claiming "cross-source agreement" over zero rows.
# --------------------------------------------------------------------------------------
def test_no_peer_group_reports_zero_confidence_not_thirty_seven():
    rc = relative_comparison("KPITTECH.NS", PeerComparison(ticker="KPITTECH.NS", peers=[], basis="none"))
    assert rc.metrics == []
    assert rc.evidence.data_coverage == 0.0
    assert rc.evidence.confidence.score < 0.10  # was 0.37
    assert "cross-source agreement" not in (rc.evidence.confidence.reason or "")
    assert "no peer group matched" in rc.evidence.confidence.reason


def test_no_peers_does_not_claim_a_one_name_peer_set():
    rc = relative_comparison("KPITTECH.NS", PeerComparison(ticker="KPITTECH.NS", peers=[], basis="none"))
    assert rc.peer_count == 0  # not 1: the company alone is not a peer set
    joined = " ".join(rc.evidence.notes)
    assert "peer set" not in joined  # no rank-within-set claim when there is no set
    assert "1-peer" not in joined


# --------------------------------------------------------------------------------------
# Basis drives confidence: a guessed peer set must never read like a deliberate one.
# --------------------------------------------------------------------------------------
def test_sector_fallback_scores_strictly_below_curated_on_identical_data():
    curated = relative_comparison("SUB.NS", _peers(basis="curated"))
    guessed = relative_comparison("SUB.NS", _peers(basis="sector-fallback"))
    assert guessed.evidence.confidence.score < curated.evidence.confidence.score
    assert guessed.basis == "sector-fallback"


def test_curated_never_reaches_the_high_tier():
    # A rank among a handful of hand-picked names is not a market percentile, however
    # complete the underlying data.
    rc = relative_comparison("SUB.NS", _peers())
    assert rc.evidence.confidence.score < 0.80
    assert rc.evidence.confidence.tier != "High"


def test_thin_peer_set_scores_below_a_full_one():
    thin = _peers()
    thin.peers = thin.peers[:3]  # subject + 2 peers, the bare minimum for a median
    a = relative_comparison("SUB.NS", thin)
    b = relative_comparison("SUB.NS", _peers())
    assert a.evidence.confidence.score < b.evidence.confidence.score


def test_peer_group_label_travels_to_the_comparison():
    rc = relative_comparison("SUB.NS", _peers(label="Automotive ER&D"))
    assert rc.peer_group_label == "Automotive ER&D"
    assert "Automotive ER&D" in " ".join(rc.evidence.notes)


# --------------------------------------------------------------------------------------
# Coverage counts what the peer set can rank on, not every metric we know how to compute.
# --------------------------------------------------------------------------------------
def test_metrics_peers_never_report_do_not_dent_coverage():
    # None of these peers report EV/EBITDA, P/S or ROA. That is a gap in the market data, not
    # a gap in the company — so coverage must stay at 1.0 rather than falling to 7/10.
    rc = relative_comparison("SUB.NS", _peers())
    assert rc.evidence.data_coverage == 1.0
    assert len(rc.metrics) == 7
    assert "EV/EBITDA" not in rc.evidence.missing_fields
    assert "No peer data reported for" in " ".join(rc.evidence.notes)


def test_company_missing_a_metric_peers_have_does_dent_coverage():
    peers = _peers()
    peers.peers[0].pe = None  # the subject alone lacks P/E; peers have it
    rc = relative_comparison("SUB.NS", peers)
    assert "P/E" in rc.evidence.missing_fields
    assert rc.evidence.data_coverage < 1.0


def test_new_metrics_compute_when_peers_report_them():
    peers = _peers()
    for row, ev_, ps, roa in ((peers.peers[0], 30.0, 5.5, 0.18),
                              (peers.peers[1], 12.0, 1.5, 0.06),
                              (peers.peers[2], 14.0, 1.8, 0.07),
                              (peers.peers[3], 16.0, 2.0, 0.08)):
        row.ev_ebitda, row.price_to_sales, row.roa = ev_, ps, roa
    rc = relative_comparison("SUB.NS", peers)
    assert {"EV/EBITDA", "P/S", "ROA"} <= {m.name for m in rc.metrics}
    assert len(rc.metrics) == 10
    # Expensive on EV/EBITDA -> unfavourable, since lower is better.
    assert next(m for m in rc.metrics if m.name == "EV/EBITDA").better is False
    # High ROA -> favourable.
    assert next(m for m in rc.metrics if m.name == "ROA").better is True


def test_units_are_declared_so_renderers_need_not_guess_from_the_name():
    by_name = {name: unit for name, _, _, unit in _METRIC_SPECS}
    assert by_name["EV/EBITDA"] == "ratio"  # would render as 3000% if guessed by name
    assert by_name["P/S"] == "ratio"
    assert by_name["ROE"] == "percent"
    rc = relative_comparison("SUB.NS", _peers())
    assert next(m for m in rc.metrics if m.name == "P/E").unit == "ratio"
    assert next(m for m in rc.metrics if m.name == "ROE").unit == "percent"
