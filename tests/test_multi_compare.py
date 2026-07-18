"""Multi-company compare tests (no network — stubbed _peer_row)."""

from investo.analysis import multi
from investo.models import PeerRow


def _wire(monkeypatch, rows: dict[str, PeerRow | None]):
    monkeypatch.setattr(multi.data, "get_info", lambda s: {"currency": "INR"})
    monkeypatch.setattr(multi, "_peer_row", lambda sym, ccy: rows.get(sym.upper()))


def _row(ticker, name, mcap=None, nm=None, growth=None, pe=None, roe=None, rev=None):
    return PeerRow(ticker=ticker, name=name, market_cap=mcap, net_margin=nm,
                   revenue_growth_yoy=growth, pe=pe, roe=roe, revenue_ttm=rev)


def test_compares_the_named_tickers(monkeypatch):
    _wire(monkeypatch, {
        "KPITTECH.NS": _row("KPITTECH.NS", "KPIT", mcap=3.4e11, nm=0.10, growth=0.12, pe=23.7,
                            roe=0.197, rev=6e10),
        "TATAELXSI.NS": _row("TATAELXSI.NS", "Tata Elxsi", mcap=3.6e11, nm=0.166, growth=0.02,
                             pe=33.5, roe=0.21, rev=4e10),
    })
    mc = multi.compare_companies(["KPITTECH.NS", "TATAELXSI.NS"])
    assert [r.ticker for r in mc.rows] == ["KPITTECH.NS", "TATAELXSI.NS"]
    assert mc.evidence is not None


def test_duplicates_are_collapsed_preserving_order(monkeypatch):
    _wire(monkeypatch, {"A.NS": _row("A.NS", "A", rev=10), "B.NS": _row("B.NS", "B", rev=10)})
    mc = multi.compare_companies(["A.NS", "B.NS", "a.ns", "A.NS"])
    assert mc.tickers == ["A.NS", "B.NS"]


def test_unresolvable_rows_are_dropped(monkeypatch):
    _wire(monkeypatch, {"A.NS": _row("A.NS", "A", rev=10), "GHOST.NS": None})
    mc = multi.compare_companies(["A.NS", "GHOST.NS"])
    assert [r.ticker for r in mc.rows] == ["A.NS"]


def test_fewer_than_two_distinct_tickers_is_a_note(monkeypatch):
    _wire(monkeypatch, {"A.NS": _row("A.NS", "A")})
    mc = multi.compare_companies(["A.NS", "a.ns"])
    assert mc.rows == []
    assert "at least two" in mc.note


def test_set_relative_share_sums_to_one(monkeypatch):
    _wire(monkeypatch, {
        "A.NS": _row("A.NS", "A", rev=60.0),
        "B.NS": _row("B.NS", "B", rev=40.0),
    })
    mc = multi.compare_companies(["A.NS", "B.NS"])
    total = sum(r.market_share_proxy for r in mc.rows if r.market_share_proxy is not None)
    assert abs(total - 1.0) < 1e-9
    # And the note is explicit that this is within-set, not market share.
    assert "not market share" in mc.note


def test_summary_names_grounded_leaders(monkeypatch):
    _wire(monkeypatch, {
        "A.NS": _row("A.NS", "A", mcap=100, nm=0.2, growth=0.3, pe=10, roe=0.25, rev=50),
        "B.NS": _row("B.NS", "B", mcap=200, nm=0.1, growth=0.1, pe=20, roe=0.15, rev=50),
    })
    mc = multi.compare_companies(["A.NS", "B.NS"])
    joined = " ".join(mc.summary)
    assert "Largest: B" in joined            # bigger market cap
    assert "Highest net margin: A" in joined
    assert "Cheapest P/E: A" in joined
