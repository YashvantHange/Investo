"""Peer-map and peer-resolution tests (no network)."""

import pytest

from investo.analysis.peers import _group_for, get_peers, resolve_peer_group
from investo.data import industry_notes, peer_groups
from investo.sources import data


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Resolution falls back to Yahoo's industry/sector when a ticker is in no curated group.
    Default that to empty so no test reaches the network unless it opts in via `_info`."""
    monkeypatch.setattr(data, "get_info", lambda symbol: {})


def _info(monkeypatch, **fields):
    monkeypatch.setattr(data, "get_info", lambda symbol: dict(fields))


def test_infosys_in_it_services_group():
    found = _group_for("INFY.NS")
    assert found is not None
    key, group = found
    assert key == "it_services"
    assert group["label"] == "IT Services"


def test_get_peers_excludes_self_includes_rivals():
    peers, group = get_peers("INFY.NS")
    upper = [p.upper() for p in peers]
    assert "INFY.NS" not in upper
    assert "TCS.NS" in upper
    assert group is not None


def test_unknown_symbol_returns_no_curated_peers():
    peers, group = get_peers("NONEXISTENT.NS")
    assert peers == []
    assert group is None


def test_curated_data_loads():
    assert peer_groups()  # peers.yaml parsed
    assert "Technology" in industry_notes()  # industry.yaml parsed
    # Every group has the required fields.
    for key, g in peer_groups().items():
        assert g.get("members"), f"{key} has no members"
        assert g.get("outlook") in {"high", "medium", "low"}, f"{key} outlook invalid"


# --------------------------------------------------------------------------------------
# The reported bug: KPIT and its ER&D cohort were in no group at all.
# --------------------------------------------------------------------------------------
def test_kpit_resolves_to_automotive_erd_not_it_services():
    res = resolve_peer_group("KPITTECH.NS")
    assert res.basis == "curated"
    assert res.key == "auto_erd"
    assert res.label == "Automotive ER&D"
    upper = [p.upper() for p in res.peers]
    assert "KPITTECH.NS" not in upper  # self excluded
    assert {"TATAELXSI.NS", "TATATECH.NS", "LTTS.NS", "CYIENT.NS"} == set(upper)


def test_erd_cohort_all_resolve_to_each_other():
    # The market treats these as one cohort; so must we.
    for sym in ("TATAELXSI.NS", "TATATECH.NS", "LTTS.NS", "CYIENT.NS"):
        assert resolve_peer_group(sym).key == "auto_erd"


# --------------------------------------------------------------------------------------
# The resolution ladder
# --------------------------------------------------------------------------------------
def test_keyword_fallback_finds_a_group_for_an_unlisted_ticker(monkeypatch):
    _info(monkeypatch, industry="Auto Parts", sector="Consumer Cyclical")
    res = resolve_peer_group("SOMENEWCO.NS")
    assert res.basis == "sector-fallback"
    assert res.key == "auto_components"
    assert res.peers  # a usable set, flagged as a guess


def test_keyword_fallback_prefers_industry_over_sector(monkeypatch):
    # Sector alone is too coarse to frame a company; the finer industry label wins.
    _info(monkeypatch, industry="Auto Parts", sector="Technology")
    assert resolve_peer_group("SOMENEWCO.NS").key == "auto_components"


def test_no_keyword_match_reports_none_not_a_guess(monkeypatch):
    _info(monkeypatch, industry="Llama Farming", sector="Agriculture")
    res = resolve_peer_group("LLAMA.NS")
    assert res.basis == "none"
    assert res.peers == []
    assert res.group is None


def test_curated_membership_beats_keyword_match(monkeypatch):
    # KPIT's Yahoo industry is generic IT; membership must win so it is never re-framed
    # as an IT services company by the fallback.
    _info(monkeypatch, industry="Information Technology Services", sector="Technology")
    assert resolve_peer_group("KPITTECH.NS").key == "auto_erd"


def test_keyword_resolution_is_deterministic(monkeypatch):
    _info(monkeypatch, industry="Auto Parts", sector="Consumer Cyclical")
    keys = {resolve_peer_group("SOMENEWCO.NS").key for _ in range(5)}
    assert len(keys) == 1  # an unstable peer group would be worse than none


# --------------------------------------------------------------------------------------
# peers.yaml invariants
# --------------------------------------------------------------------------------------
def test_first_match_wins_order_is_pinned():
    # Several tickers sit in more than one group on purpose; peers.yaml order decides which
    # wins. New groups must be appended, never inserted, or these silently re-frame.
    assert _group_for("RELIANCE.NS")[0] == "oil_gas_energy"  # not telecom
    assert _group_for("EICHERMOT.NS")[0] == "auto_oem"       # not two_wheelers


def test_every_group_carries_provenance():
    for key, g in peer_groups().items():
        assert g.get("version"), f"{key} has no version"
        assert g.get("updated_at"), f"{key} has no updated_at"
        assert g.get("source"), f"{key} has no source"


def test_keywords_are_lowercase_for_case_insensitive_matching():
    for key, g in peer_groups().items():
        for kw in g.get("keywords", []):
            assert kw == kw.lower(), f"{key} keyword {kw!r} is not lowercase"


def test_auto_erd_reframes_the_narrative():
    g = peer_groups()["auto_erd"]
    joined = " ".join(g["sub_domains"]).lower()
    assert "software-defined" in joined
    assert "adas" in joined
    assert "outsourcing" not in joined  # this is not an IT services group
