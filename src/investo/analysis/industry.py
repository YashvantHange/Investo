"""Industry intelligence: sub-domains, demand drivers, CAGR and risks for a company.

Yahoo's ``sector`` is broad — KPIT, Infosys and a data-centre REIT are all "Technology" — so the
per-sector notes in ``data/industry.yaml`` are only a starting point. When a company resolves to a
curated peer group, that group's framing wins: an automotive ER&D firm is described by SDV and
ADAS programmes, not by "IT services & outsourcing", because the group is the more specific and
more considered judgement.

Yahoo's raw ``industry`` string is preserved verbatim alongside — it is a fact about how the
exchange classifies the company, and overwriting it would hide the disagreement rather than show
it.
"""

from __future__ import annotations

from ..data import industry_notes
from ..models import IndustryIntelligence
from ..sources import data
from .peers import resolve_peer_group


def get_industry_intelligence(symbol: str) -> IndustryIntelligence:
    info = data.get_info(symbol)
    sector = info.get("sector")
    industry = info.get("industry")

    notes = industry_notes().get(sector or "", {})
    res = resolve_peer_group(symbol, info)
    group = res.group or {}

    # The peer group is the more specific judgement, so it wins field by field; the sector note
    # fills whatever the group doesn't speak to.
    def pick(key: str, default):
        value = group.get(key)
        return value if value else notes.get(key, default)

    result = IndustryIntelligence(
        ticker=symbol.upper(),
        sector=sector,
        industry=industry,
        peer_group=res.label,
        basis=res.basis,
        sub_domains=list(pick("sub_domains", [])),
        demand_drivers=list(pick("demand_drivers", [])),
        future_demand=pick("future_demand", None),
        industry_cagr=pick("industry_cagr", None),
        as_of=group.get("updated_at"),
        risks=list(pick("risks", [])),
        source="curated" if (res.basis == "curated" or notes) else "unknown",
    )
    if res.basis == "sector-fallback":
        result.note = (
            f"{symbol.upper()} is not in a curated peer group; framed as '{res.label}' by matching "
            f"its Yahoo industry ('{industry}'). Indicative only."
        )
    elif not notes and not group:
        result.note = (
            f"No curated intelligence for sector '{sector}'. Add it in data/industry.yaml or add "
            "the ticker to a peer group in data/peers.yaml; the host LLM can also reason about "
            "the industry from the profile."
        )
    return result


def industry_outlook(symbol: str) -> tuple[str | None, str | None]:
    """Return (outlook, cagr_hint) used by the composite score."""
    info = data.get_info(symbol)
    sector = info.get("sector")
    notes = industry_notes().get(sector or "", {})
    outlook = notes.get("outlook")
    cagr = notes.get("industry_cagr")
    group = resolve_peer_group(symbol, info).group
    if group:
        outlook = group.get("outlook", outlook)
        cagr = group.get("industry_cagr", cagr)
    return outlook, cagr
