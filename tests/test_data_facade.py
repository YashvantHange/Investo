"""Provider-facade precedence tests (no network — sources are monkeypatched)."""

from investo.sources import data, keyed, yahoo


def test_keyed_overlay_wins_over_yahoo(monkeypatch):
    data._MERGED_CACHE.clear()
    monkeypatch.setattr(data, "_keys_configured", lambda: True)
    monkeypatch.setattr(yahoo, "get_info", lambda s: {"sector": "Yahoo", "trailingPE": 10, "marketCap": 1})
    monkeypatch.setattr(keyed, "overview_as_info", lambda s: {"sector": "Keyed", "trailingPE": 20})
    info = data.get_info("AAPL")
    assert info["sector"] == "Keyed"    # licensed value takes precedence
    assert info["trailingPE"] == 20
    assert info["marketCap"] == 1       # Yahoo value kept where keyed has none


def test_yahoo_only_without_keys(monkeypatch):
    data._MERGED_CACHE.clear()
    monkeypatch.setattr(data, "_keys_configured", lambda: False)
    monkeypatch.setattr(yahoo, "get_info", lambda s: {"sector": "Yahoo"})
    assert data.get_info("X")["sector"] == "Yahoo"


def test_provider_status_reports_mode(monkeypatch):
    monkeypatch.setattr(data, "_keys_configured", lambda: False)
    status = data.provider_status()
    assert status["fallback"] == "yahoo"
    assert status["primary_when_available"] == "yahoo"
    monkeypatch.setattr(data, "_keys_configured", lambda: True)
    assert "keyed" in data.provider_status()["primary_when_available"]


def test_overview_as_info_skips_suffixed_symbols():
    # NSE/BSE symbols must not be routed to US-centric keyed APIs.
    assert keyed.overview_as_info("RELIANCE.NS") == {}
