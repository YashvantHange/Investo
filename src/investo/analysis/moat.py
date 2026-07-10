"""Economic-moat assessment: which durable competitive advantages the numbers suggest.

Produces a signal pack (candidate moat sources + observations) and a 0-10 heuristic score
reusing :func:`scoring.score_moat`, so the standalone tool and the composite rating agree.
The host LLM refines the qualitative call (brand, switching costs, network effects).
"""

from __future__ import annotations

from typing import Optional

from ..models import MoatSignals, Ratios
from ..sources import yahoo
from .scoring import score_moat


def moat_assessment(
    symbol: str,
    ratios: Optional[Ratios] = None,
    market_share_proxy: Optional[float] = None,
) -> MoatSignals:
    from .ratios import compute_ratios

    if ratios is None:
        ratios = compute_ratios(symbol)

    normalized, rationale, drivers = score_moat(ratios, market_share_proxy)
    score10 = round((normalized if normalized is not None else 0.5) * 10.0, 1)

    sources: list[str] = []
    signals: list[str] = []

    if ratios.gross_margin and ratios.gross_margin > 0.4:
        sources.append("cost advantage / brand (high gross margin)")
        signals.append(f"Gross margin {ratios.gross_margin:.0%} suggests pricing power.")
    if ratios.roic and ratios.roic > 0.15:
        sources.append("durable returns (high ROIC)")
        signals.append(f"ROIC {ratios.roic:.0%} well above cost of capital -> economic moat likely.")
    if ratios.net_margin and ratios.net_margin > 0.20:
        signals.append(f"Net margin {ratios.net_margin:.0%} indicates strong profitability.")
    if market_share_proxy and market_share_proxy > 0.25:
        sources.append("scale / market leadership")
        signals.append(f"Leads peer set with ~{market_share_proxy:.0%} revenue share.")
    if ratios.rd_intensity and ratios.rd_intensity > 0.04:
        sources.append("intangibles / R&D & patents")
        signals.append(f"R&D intensity {ratios.rd_intensity:.1%} supports an innovation edge.")

    if not signals:
        signals.append("No strong quantitative moat signal; assess brand/switching-costs qualitatively.")

    return MoatSignals(
        ticker=symbol.upper(),
        gross_margin=ratios.gross_margin,
        roic=ratios.roic,
        market_share_proxy=market_share_proxy,
        rd_intensity=ratios.rd_intensity,
        moat_score=score10,
        sources=sources,
        signals=signals,
        note=f"Heuristic moat score {score10}/10 ({rationale}). Refine with brand/switching-cost judgment.",
    )
