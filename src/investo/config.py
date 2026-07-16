"""Runtime configuration for Investo.

Reads optional environment variables (see .env.example). Everything has a sensible
default so the server works out of the box with zero configuration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    """Effective configuration derived from the environment."""

    # Optional API keys (empty string => disabled)
    alphavantage_key: str = ""
    fmp_key: str = ""
    finnhub_key: str = ""

    # DCF defaults
    dcf_discount_rate_in: float = 0.12
    dcf_discount_rate_us: float = 0.09
    dcf_terminal_growth: float = 0.04
    dcf_years: int = 5

    default_market: str = "IN"

    # SEC EDGAR requires a descriptive User-Agent with contact info.
    sec_contact: str = "https://github.com/YashvantHange/Investo"

    # Rate limiting (seconds between calls / daily caps per provider).
    yahoo_min_interval: float = 0.0   # polite gap for Yahoo calls (0 = off by default)
    av_min_interval: float = 12.0     # Alpha Vantage free tier ~5/min
    av_daily_cap: int = 25            # Alpha Vantage free tier 25/day
    fmp_min_interval: float = 0.3
    finnhub_min_interval: float = 1.0

    # India shareholding source (NSE/BSE filings). On by default; can be disabled to force the
    # Yahoo fallback (e.g. offline / tests / when the exchange endpoints are unreliable).
    enable_india_holdings: bool = True
    india_holdings_min_interval: float = 1.0  # polite gap between NSE/BSE calls

    # PDF export. `chrome_path` overrides browser discovery; `export_dir` sandboxes the
    # MCP export tool's output (empty => a temp dir).
    chrome_path: str = ""
    pdf_timeout: float = 60.0
    export_dir: str = ""

    # Logging
    log_level: str = "WARNING"

    @property
    def has_alphavantage(self) -> bool:
        return bool(self.alphavantage_key)

    @property
    def has_fmp(self) -> bool:
        return bool(self.fmp_key)

    @property
    def has_finnhub(self) -> bool:
        return bool(self.finnhub_key)

    def discount_rate_for_market(self, market: str) -> float:
        return self.dcf_discount_rate_us if (market or "").upper() == "US" else self.dcf_discount_rate_in


def load_config() -> Config:
    """Build a Config from current environment variables."""
    return Config(
        alphavantage_key=os.getenv("ALPHAVANTAGE_API_KEY", "").strip(),
        fmp_key=os.getenv("FMP_API_KEY", "").strip(),
        finnhub_key=os.getenv("FINNHUB_API_KEY", "").strip(),
        dcf_discount_rate_in=_get_float("INVESTO_DCF_DISCOUNT_RATE_IN", 0.12),
        dcf_discount_rate_us=_get_float("INVESTO_DCF_DISCOUNT_RATE_US", 0.09),
        dcf_terminal_growth=_get_float("INVESTO_DCF_TERMINAL_GROWTH", 0.04),
        dcf_years=_get_int("INVESTO_DCF_YEARS", 5),
        default_market=os.getenv("INVESTO_DEFAULT_MARKET", "IN").strip().upper() or "IN",
        sec_contact=os.getenv("INVESTO_SEC_CONTACT", "").strip()
        or "https://github.com/YashvantHange/Investo",
        yahoo_min_interval=_get_float("INVESTO_RATE_MIN_INTERVAL", 0.0),
        av_daily_cap=_get_int("INVESTO_AV_DAILY_CAP", 25),
        enable_india_holdings=_get_bool("INVESTO_ENABLE_INDIA_HOLDINGS", True),
        india_holdings_min_interval=_get_float("INVESTO_INDIA_HOLDINGS_MIN_INTERVAL", 1.0),
        chrome_path=os.getenv("INVESTO_CHROME", "").strip(),
        pdf_timeout=_get_float("INVESTO_PDF_TIMEOUT", 60.0),
        export_dir=os.getenv("INVESTO_EXPORT_DIR", "").strip(),
        log_level=(os.getenv("INVESTO_LOG_LEVEL", "WARNING").strip().upper() or "WARNING"),
    )


# A module-level singleton is convenient; call load_config() again to refresh.
CONFIG = load_config()
