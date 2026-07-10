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
    )


# A module-level singleton is convenient; call load_config() again to refresh.
CONFIG = load_config()
