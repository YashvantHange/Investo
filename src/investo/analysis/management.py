"""Management & ownership analysis: executives, holdings, and capital allocation.

Holdings (promoter/insider/institutional) are best-effort. yfinance's holder data is far more
complete for US listings than for NSE/BSE, so promoter holding is frequently unavailable for
Indian names -- callers should treat ``None`` as "not disclosed here" (see BSE/NSE shareholding
filings for the authoritative figure).
"""

from __future__ import annotations

import re
from typing import Any

from ..models import Financials, Management, Ratios
from ..sources import data
from . import finutils as F


def _pct_from_holders(holders: dict[str, Any], *needles: str) -> float | None:
    mh = holders.get("major_holders")
    if not isinstance(mh, dict):
        return None
    for label, value in mh.items():
        low = str(label).lower()
        if any(n in low for n in needles):
            v = value
            if isinstance(v, str):
                m = re.search(r"[-+]?\d*\.?\d+", v)
                v = float(m.group()) / 100.0 if m else None
            if isinstance(v, (int, float)):
                return v if v <= 1.0 else v / 100.0
    return None


def get_management(
    symbol: str,
    info: dict[str, Any] | None = None,
    financials: Financials | None = None,
    ratios: Ratios | None = None,
) -> Management:
    from .ratios import compute_ratios

    if info is None:
        info = data.get_info(symbol)
    if financials is None:
        financials = data.get_financials(symbol)
    if ratios is None:
        ratios = compute_ratios(symbol, info=info, financials=financials)

    holders = data.get_holders(symbol)
    execs = []
    for o in info.get("companyOfficers", []) or []:
        if isinstance(o, dict) and o.get("name"):
            execs.append({"name": o.get("name"), "title": o.get("title"), "age": o.get("age")})

    insider = _pct_from_holders(holders, "insider")
    institutional = _pct_from_holders(holders, "institution")

    # Capital allocation signals
    payout = info.get("payoutRatio")
    try:
        payout = float(payout) if payout is not None else None
    except (TypeError, ValueError):
        payout = None

    repurchase = F.pick(F.latest(financials.cash_flow), *F.REPURCHASE)
    buyback = bool(repurchase and repurchase < 0)

    notes: list[str] = []
    if ratios.roic is not None:
        notes.append(f"ROIC {ratios.roic:.1%} indicates {'strong' if ratios.roic > 0.15 else 'moderate' if ratios.roic > 0.08 else 'weak'} capital efficiency.")
    if payout is not None:
        notes.append(f"Dividend payout ratio ~{payout:.0%}.")
    if buyback:
        notes.append("Recent share buyback detected in cash-flow statement.")

    m = Management(
        ticker=symbol.upper(),
        key_executives=execs,
        promoter_holding=insider,  # best-effort proxy on NSE/BSE; often None
        insider_holding=insider,
        institutional_holding=institutional,
        roic=ratios.roic,
        dividend_payout_ratio=payout,
        buyback_signal=buyback,
        capital_allocation_notes=notes,
    )
    if insider is None:
        m.note = "Promoter/insider holding not available from Yahoo for this listing (common for NSE/BSE)."
    return m
