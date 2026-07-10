"""Peer-map tests (no network)."""

from investo.analysis.peers import _group_for, get_peers
from investo.data import industry_notes, peer_groups


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
