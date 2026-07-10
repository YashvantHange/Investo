"""Competitor analysis: find sector peers and build a side-by-side comparison.

Peers come from the curated map (``data/peers.yaml``); when a ticker isn't in the map and a
Finnhub key is configured, we fall back to Finnhub's peer list. Revenue and market cap are
normalized to the queried company's trading currency so cross-listed peers (e.g. INFY in USD)
compare fairly against INR-reporting peers.
"""

from __future__ import annotations

from typing import Optional

from ..config import CONFIG
from ..data import peer_groups
from ..models import PeerComparison, PeerRow
from ..sources import yahoo

_MAX_PEERS = 6


def _group_for(symbol: str) -> Optional[tuple[str, dict]]:
    sym = symbol.upper()
    for key, group in peer_groups().items():
        members = [m.upper() for m in group.get("members", [])]
        if sym in members:
            return key, group
    return None


def get_peers(symbol: str) -> tuple[list[str], Optional[dict]]:
    """Return (peer_symbols, group_metadata) for a ticker."""
    found = _group_for(symbol)
    if found:
        _, group = found
        peers = [m for m in group.get("members", []) if m.upper() != symbol.upper()]
        return peers, group

    # Fallback: Finnhub peers (optional, needs key).
    if CONFIG.has_finnhub:
        from ..sources import keyed
        peers = keyed.finnhub_peers(symbol)
        if peers:
            return [p for p in peers if p.upper() != symbol.upper()], None
    return [], None


def _bounded(value: Optional[float], lo: float, hi: float) -> Optional[float]:
    if value is None:
        return None
    return value if lo < value <= hi else None


def _peer_row(symbol: str, base_ccy: Optional[str]) -> Optional[PeerRow]:
    info = yahoo.get_info(symbol)
    name = info.get("longName") or info.get("shortName")
    if not name:
        return None

    fin_ccy = info.get("financialCurrency") or info.get("currency")
    price_ccy = info.get("currency") or fin_ccy
    fx_rev = yahoo.fx_rate(fin_ccy, base_ccy) or 1.0
    fx_mcap = yahoo.fx_rate(price_ccy, base_ccy) or 1.0

    def f(key: str) -> Optional[float]:
        v = info.get(key)
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    rev = f("totalRevenue")
    mcap = f("marketCap")
    d2e = f("debtToEquity")
    return PeerRow(
        ticker=symbol.upper(),
        name=name,
        market_cap=mcap * fx_mcap if mcap is not None else None,
        revenue_ttm=rev * fx_rev if rev is not None else None,
        net_margin=f("profitMargins"),
        operating_margin=f("operatingMargins"),
        pe=_bounded(f("trailingPE"), 0, 500),
        pb=_bounded(f("priceToBook"), 0, 100),
        roe=f("returnOnEquity"),
        revenue_growth_yoy=f("revenueGrowth"),
        debt_to_equity=(d2e / 100.0) if d2e is not None else None,
    )


def _summarize(subject: str, rows: list[PeerRow]) -> list[str]:
    out: list[str] = []
    subj = next((r for r in rows if r.ticker == subject.upper()), None)
    if subj is None:
        return out

    def rank_by(attr: str, reverse: bool) -> Optional[int]:
        vals = [(r.ticker, getattr(r, attr)) for r in rows if getattr(r, attr) is not None]
        if not vals or getattr(subj, attr) is None:
            return None
        ordered = sorted(vals, key=lambda x: x[1], reverse=reverse)
        for i, (tk, _) in enumerate(ordered, start=1):
            if tk == subject.upper():
                return i
        return None

    n = len(rows)
    r_size = rank_by("market_cap", True)
    if r_size:
        out.append(f"#{r_size} of {n} by market cap in its peer set.")
    r_margin = rank_by("net_margin", True)
    if r_margin:
        out.append(f"#{r_margin} of {n} by net margin ({_p(subj.net_margin)}).")
    r_growth = rank_by("revenue_growth_yoy", True)
    if r_growth:
        out.append(f"#{r_growth} of {n} by revenue growth ({_p(subj.revenue_growth_yoy)}).")
    r_cheap = rank_by("pe", False)
    if r_cheap and subj.pe is not None:
        out.append(f"#{r_cheap} cheapest of {n} by P/E ({subj.pe:.1f}).")
    if subj.market_share_proxy is not None:
        out.append(f"Peer-set revenue share ~{_p(subj.market_share_proxy)}.")
    return out


def _p(x: Optional[float]) -> str:
    return f"{x:.1%}" if x is not None else "n/a"


def compare_peers(symbol: str, max_peers: int = _MAX_PEERS) -> PeerComparison:
    """Build a peer comparison table for *symbol* (must be a resolved ticker)."""
    info = yahoo.get_info(symbol)
    base_ccy = info.get("currency") or info.get("financialCurrency")
    sector = info.get("sector")

    peers, group = get_peers(symbol)
    if not peers:
        return PeerComparison(
            ticker=symbol.upper(), sector=sector, peers=[],
            note="No curated peer group matched. Add one in data/peers.yaml or set FINNHUB_API_KEY.",
        )

    symbols = [symbol.upper()] + [p.upper() for p in peers[:max_peers]]
    rows: list[PeerRow] = []
    for sym in symbols:
        row = _peer_row(sym, base_ccy)
        if row is not None:
            rows.append(row)

    # Market-share proxy from normalized revenue.
    total_rev = sum(r.revenue_ttm for r in rows if r.revenue_ttm is not None)
    if total_rev > 0:
        for r in rows:
            if r.revenue_ttm is not None:
                r.market_share_proxy = r.revenue_ttm / total_rev

    label = group.get("label") if group else sector
    return PeerComparison(
        ticker=symbol.upper(),
        sector=label,
        peers=rows,
        summary=_summarize(symbol, rows),
        note="Revenue & market cap normalized to the subject's trading currency.",
    )
