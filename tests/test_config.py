"""Config env-parsing tests (no network)."""

from investo.config import load_config


def test_defaults_when_env_absent(monkeypatch):
    for var in ("ALPHAVANTAGE_API_KEY", "FMP_API_KEY", "FINNHUB_API_KEY",
                "INVESTO_DCF_DISCOUNT_RATE_IN", "INVESTO_DEFAULT_MARKET", "INVESTO_SEC_CONTACT"):
        monkeypatch.delenv(var, raising=False)
    cfg = load_config()
    assert cfg.has_alphavantage is False
    assert cfg.dcf_discount_rate_in == 0.12
    assert cfg.default_market == "IN"
    assert "github.com/YashvantHange/Investo" in cfg.sec_contact


def test_keys_and_overrides(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "abc123")
    monkeypatch.setenv("INVESTO_DCF_DISCOUNT_RATE_IN", "0.15")
    monkeypatch.setenv("INVESTO_DEFAULT_MARKET", "us")
    monkeypatch.setenv("INVESTO_SEC_CONTACT", "me@example.com")
    cfg = load_config()
    assert cfg.has_fmp is True
    assert cfg.dcf_discount_rate_in == 0.15
    assert cfg.default_market == "US"
    assert cfg.sec_contact == "me@example.com"
    assert cfg.discount_rate_for_market("US") == cfg.dcf_discount_rate_us


def test_invalid_numeric_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("INVESTO_DCF_YEARS", "not-a-number")
    cfg = load_config()
    assert cfg.dcf_years == 5
