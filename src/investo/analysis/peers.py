"""Competitor analysis: find sector peers and build a side-by-side comparison.

Peers are resolved by a ladder, best evidence first (see :func:`resolve_peer_group`): an exact
curated match, then a keyword match on the company's Yahoo industry/sector, then Finnhub if a key
is configured. The resulting :class:`PeerBasis` travels with the comparison so that everything
derived from it can be priced honestly — a guessed peer set must not be presented with the same
confidence as a deliberate one.

Revenue and market cap are normalized to the queried company's trading currency so cross-listed
peers (e.g. INFY in USD) compare fairly against INR-reporting peers.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from ..config import CONFIG
from ..data import peer_groups
from ..models import PeerBasis, PeerComparison, PeerRow
from ..sources import data

_MAX_PEERS = 6


@dataclass(frozen=True)
class PeerResolution:
    """How a peer set was found, and what it is."""

    basis: PeerBasis
    key: str | None
    group: dict | None
    peers: list[str]

    @property
    def label(self) -> str | None:
        return self.group.get("label") if self.group else None


def _group_for(symbol: str) -> tuple[str, dict] | None:
    """Exact membership match. First-match-wins over peers.yaml order (deliberate — see the note
    at the top of that file; some tickers are double-booked)."""
    sym = symbol.upper()
    for key, group in peer_groups().items():
        members = [m.upper() for m in group.get("members", [])]
        if sym in members:
            return key, group
    return None


def _group_by_keywords(info: dict) -> tuple[str, dict] | None:
    """Match a group's ``keywords`` against Yahoo's industry, then its sector.

    Only reached for tickers in no curated group. Longest keyword wins so the most specific
    match beats a generic one, with an alphabetical tie-break so the result never depends on
    dict ordering — an unstable peer group would be worse than none.
    """
    for field in ("industry", "sector"):
        haystack = str(info.get(field) or "").lower()
        if not haystack:
            continue
        hits = [
            (len(kw), key, group)
            for key, group in peer_groups().items()
            for kw in group.get("keywords", [])
            if kw and kw.lower() in haystack
        ]
        if hits:
            _, key, group = max(hits, key=lambda h: (h[0], _inverse(h[1])))
            return key, group
    return None


def _inverse(key: str) -> tuple[int, ...]:
    """Sort helper: makes `max` pick the alphabetically-first key on a length tie."""
    return tuple(-ord(c) for c in key)


def resolve_peer_group(symbol: str, info: dict | None = None) -> PeerResolution:
    """Resolve ``symbol``'s peer set, best evidence first.

    1. curated       — an exact membership match in data/peers.yaml
    2. sector-fallback — a keyword match on Yahoo's industry/sector (an educated guess)
    3. keyed         — Finnhub's peer list, when a key is configured
    4. none          — no peers; callers must not pretend otherwise
    """
    sym = symbol.upper()

    found = _group_for(sym)
    if found:
        key, group = found
        peers = [m for m in group.get("members", []) if m.upper() != sym]
        return PeerResolution("curated", key, group, peers)

    info = data.get_info(symbol) if info is None else info
    found = _group_by_keywords(info or {})
    if found:
        key, group = found
        peers = [m for m in group.get("members", []) if m.upper() != sym]
        if peers:
            return PeerResolution("sector-fallback", key, group, peers)

    if CONFIG.has_finnhub:
        from ..sources import keyed
        fh = [p for p in keyed.finnhub_peers(symbol) if p.upper() != sym]
        if fh:
            return PeerResolution("keyed", None, None, fh)

    return PeerResolution("none", None, None, [])


def get_peers(symbol: str) -> tuple[list[str], dict | None]:
    """Return (peer_symbols, group_metadata) for a ticker.

    Kept for callers that don't care *how* the peers were found; prefer
    :func:`resolve_peer_group`, which also tells you how much to trust them.
    """
    res = resolve_peer_group(symbol)
    return res.peers, res.group


def peer_group_directory():
    """List the curated peer groups so a client can see how companies are grouped and why."""
    from ..models import PeerGroupDirectory, PeerGroupInfo

    groups = [
        PeerGroupInfo(
            key=key,
            label=g.get("label", key),
            outlook=g.get("outlook"),
            industry_cagr=g.get("industry_cagr"),
            updated_at=g.get("updated_at"),
            member_count=len(g.get("members", [])),
            members=list(g.get("members", [])),
        )
        for key, g in peer_groups().items()
    ]
    return PeerGroupDirectory(groups=groups, count=len(groups))


def _bounded(value: float | None, lo: float, hi: float) -> float | None:
    if value is None:
        return None
    return value if lo < value <= hi else None


def _peer_row(symbol: str, base_ccy: str | None) -> PeerRow | None:
    info = data.get_info(symbol)
    name = info.get("longName") or info.get("shortName")
    if not name:
        return None

    fin_ccy = info.get("financialCurrency") or info.get("currency")
    price_ccy = info.get("currency") or fin_ccy
    fx_rev = data.fx_rate(fin_ccy, base_ccy) or 1.0
    fx_mcap = data.fx_rate(price_ccy, base_ccy) or 1.0

    def f(key: str) -> float | None:
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
        roa=f("returnOnAssets"),
        # Bounded because Yahoo mixes currencies on cross-listed names: an INR enterprise value
        # over USD EBITDA yields nonsense like 975x (see ratios.py).
        ev_ebitda=_bounded(f("enterpriseToEbitda"), 0, 100),
        price_to_sales=_bounded(f("priceToSalesTrailing12Months"), 0, 100),
        revenue_growth_yoy=f("revenueGrowth"),
        debt_to_equity=(d2e / 100.0) if d2e is not None else None,
    )


def _summarize(subject: str, rows: list[PeerRow]) -> list[str]:
    out: list[str] = []
    subj = next((r for r in rows if r.ticker == subject.upper()), None)
    if subj is None:
        return out

    def rank_by(attr: str, reverse: bool) -> int | None:
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


def _p(x: float | None) -> str:
    return f"{x:.1%}" if x is not None else "n/a"


_NO_PEERS_NOTE = {
    "none": "No peer group matched — not by membership in data/peers.yaml, not by industry "
            "keyword. Add the ticker to a group there, or set FINNHUB_API_KEY.",
    "keyed": "Finnhub returned no usable peers for this ticker.",
}


def compare_peers(symbol: str, max_peers: int = _MAX_PEERS) -> PeerComparison:
    """Build a peer comparison table for *symbol* (must be a resolved ticker)."""
    info = data.get_info(symbol)
    base_ccy = info.get("currency") or info.get("financialCurrency")
    sector = info.get("sector")

    res = resolve_peer_group(symbol, info)
    peers = res.peers
    group = res.group
    if not peers:
        return PeerComparison(
            ticker=symbol.upper(), sector=sector, peers=[], basis=res.basis,
            note=_NO_PEERS_NOTE.get(res.basis, _NO_PEERS_NOTE["none"]),
        )

    symbols = [symbol.upper()] + [p.upper() for p in peers[:max_peers]]
    # Fetch peer rows concurrently — each is an independent, blocking network call.
    with ThreadPoolExecutor(max_workers=8) as pool:
        fetched = list(pool.map(lambda sym: _peer_row(sym, base_ccy), symbols))
    rows: list[PeerRow] = [row for row in fetched if row is not None]

    # Market-share proxy from normalized revenue.
    total_rev = sum(r.revenue_ttm for r in rows if r.revenue_ttm is not None)
    if total_rev > 0:
        for r in rows:
            if r.revenue_ttm is not None:
                r.market_share_proxy = r.revenue_ttm / total_rev

    label = group.get("label") if group else sector
    note = "Revenue & market cap normalized to the subject's trading currency."
    if res.basis == "sector-fallback":
        note = (f"{symbol.upper()} is not in a curated peer group; matched to '{label}' by its "
                f"industry. Treat the comparison as indicative. ") + note
    return PeerComparison(
        ticker=symbol.upper(),
        sector=label,
        peers=rows,
        summary=_summarize(symbol, rows),
        basis=res.basis,
        peer_group_key=res.key,
        peer_group_label=label,
        note=note,
    )
