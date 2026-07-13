"""NSE/BSE symbol helpers for the shareholding source.

BSE's shareholding API is keyed by a numeric **scrip code** (e.g. Reliance = 500325), while Investo
usually resolves names to NSE ``.NS`` tickers. This module bridges the two:

- ``nse_symbol`` strips the exchange suffix to the bare NSE symbol NSE's API expects.
- ``bse_scrip_code`` returns the BSE scrip code — taken directly from a ``<code>.BO`` ticker when we
  already have one, otherwise from a small curated map of large-caps. Unknown names return ``None``
  and the caller falls back to NSE-by-symbol or Yahoo.

The curated map intentionally covers only frequently-analysed names; it is easy to extend and never
required for correctness (it only enables the BSE path).
"""

from __future__ import annotations

import re

# Bare NSE symbol -> BSE scrip code. Extend as needed; this is a convenience, not a dependency.
NSE_TO_BSE: dict[str, str] = {
    "RELIANCE": "500325",
    "TCS": "532540",
    "INFY": "500209",
    "HDFCBANK": "500180",
    "ICICIBANK": "532174",
    "HINDUNILVR": "500696",
    "ITC": "500875",
    "SBIN": "500112",
    "BHARTIARTL": "532454",
    "KOTAKBANK": "500247",
    "LT": "500510",
    "AXISBANK": "532215",
    "BAJFINANCE": "500034",
    "ASIANPAINT": "500820",
    "MARUTI": "532500",
    "SUNPHARMA": "524715",
    "TITAN": "500114",
    "WIPRO": "507685",
    "ULTRACEMCO": "532538",
    "NESTLEIND": "500790",
    "ONGC": "500312",
    "IOC": "530965",
    "BPCL": "500547",
    "GAIL": "532155",
    "HINDPETRO": "500104",
    "TATAMOTORS": "500570",
    "TATASTEEL": "500470",
    "HCLTECH": "532281",
    "TECHM": "532755",
    "LTIM": "540005",
}

_NUMERIC = re.compile(r"^(\d{4,6})\.BO$", re.IGNORECASE)


def nse_symbol(symbol: str) -> str:
    """Bare NSE symbol (drop ``.NS``/``.BO`` and upper-case)."""
    return (symbol or "").upper().split(".")[0]


def bse_scrip_code(symbol: str) -> str | None:
    """BSE scrip code for a symbol, or ``None`` if unknown.

    Prefers the code embedded in a ``<code>.BO`` ticker, then the curated map.
    """
    s = (symbol or "").upper()
    m = _NUMERIC.match(s)
    if m:
        return m.group(1)
    return NSE_TO_BSE.get(nse_symbol(s))
