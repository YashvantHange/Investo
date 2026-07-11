"""Industry intelligence: sub-domains, demand drivers, CAGR and risks for a company.

Combines the curated per-sector notes (``data/industry.yaml``) with the peer-group's more
specific outlook/CAGR (``data/peers.yaml``) when the company belongs to a curated group.
"""

from __future__ import annotations

from ..data import industry_notes
from ..models import IndustryIntelligence
from ..sources import data
from .peers import _group_for


def get_industry_intelligence(symbol: str) -> IndustryIntelligence:
    info = data.get_info(symbol)
    sector = info.get("sector")
    industry = info.get("industry")

    notes = industry_notes().get(sector or "", {})
    outlook = notes.get("outlook")
    cagr = notes.get("industry_cagr")

    # Peer-group specifics override the broad sector note when available.
    found = _group_for(symbol)
    if found:
        _, group = found
        outlook = group.get("outlook", outlook)
        cagr = group.get("industry_cagr", cagr)

    result = IndustryIntelligence(
        ticker=symbol.upper(),
        sector=sector,
        industry=industry,
        sub_domains=list(notes.get("sub_domains", [])),
        demand_drivers=list(notes.get("demand_drivers", [])),
        future_demand=notes.get("future_demand"),
        industry_cagr=cagr,
        risks=list(notes.get("risks", [])),
        source="curated",
    )
    if not notes:
        result.note = (
            f"No curated intelligence for sector '{sector}'. Add it in data/industry.yaml; "
            "the host LLM can also reason about the industry from the profile."
        )
    return result


def industry_outlook(symbol: str) -> tuple[str | None, str | None]:
    """Return (outlook, cagr_hint) used by the composite score."""
    info = data.get_info(symbol)
    sector = info.get("sector")
    notes = industry_notes().get(sector or "", {})
    outlook = notes.get("outlook")
    cagr = notes.get("industry_cagr")
    found = _group_for(symbol)
    if found:
        _, group = found
        outlook = group.get("outlook", outlook)
        cagr = group.get("industry_cagr", cagr)
    return outlook, cagr
