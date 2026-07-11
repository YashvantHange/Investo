"""Investo MCP server.

Exposes the analysis toolkit to an AI client (Claude Code, Claude Desktop, Cursor).
Run with ``python -m investo.server`` (stdio transport) or via the ``investo-mcp`` script.

Every tool is read-only and hits external data APIs, so all are annotated
``readOnlyHint=True, openWorldHint=True``. Tools return typed pydantic models, so FastMCP
emits an output schema and structured content the client can render; failures surface as MCP
``isError`` results via FastMCP's built-in handling.
"""

from __future__ import annotations

import re
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .models import (
    AnalysisReport,
    CompanyProfile,
    DCFResult,
    Financials,
    IndustryIntelligence,
    Management,
    MoatSignals,
    NewsFeed,
    PeerComparison,
    Ratios,
    RiskSignals,
    Score,
    SearchResult,
)
from .resolve import resolve, resolve_ticker

_INSTRUCTIONS = (
    "Investo analyzes companies (India-first: NSE/BSE, plus US/global) from public data. "
    "Call `analyze_company` for a full report (profile, ratios, peers, DCF, moat, risk, news, "
    "SWOT seeds and a 0-100 rating), or the focused tools for one aspect. Pass a company name "
    "or a ticker; names are resolved to NSE (.NS)/BSE (.BO) tickers by default. Use the "
    "returned evidence to write the narrative; do not invent numbers. Research only, not advice."
)

mcp = FastMCP(
    "Investo",
    instructions=_INSTRUCTIONS,
    website_url="https://github.com/YashvantHange/Investo",
)

# All tools are read-only data retrieval against external (open-world) APIs.
_READ = ToolAnnotations(readOnlyHint=True, openWorldHint=True)

_TICKER_RE = re.compile(r"^[A-Za-z0-9&.-]{1,15}(\.[A-Za-z]{1,3})?$")


def _symbol(ticker_or_name: str, market: str = "IN") -> str:
    """Accept a ticker or a company name; return a resolved exchange ticker."""
    s = ticker_or_name.strip()
    if "." in s and _TICKER_RE.match(s):
        return s.upper()
    resolved = resolve_ticker(s, market)
    return resolved or s.upper()


# --------------------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------------------
@mcp.tool(title="Search company", annotations=_READ)
def search_company(query: str, market: str = "IN") -> SearchResult:
    """Resolve a company name to an exchange ticker (NSE/BSE preferred for India).

    Returns the best match plus ranked alternatives.
    """
    return resolve(query, market)


@mcp.tool(title="Company profile", annotations=_READ)
def get_company_profile(ticker: str, market: str = "IN") -> CompanyProfile:
    """Company profile: sector, industry, business summary, market cap, executives."""
    from .sources import data
    return data.get_profile(_symbol(ticker, market))


@mcp.tool(title="Financial statements", annotations=_READ)
def get_financials(ticker: str, period: str = "annual", market: str = "IN") -> Financials:
    """Income statement, balance sheet and cash flow (period = 'annual' or 'quarterly')."""
    from .sources import data
    return data.get_financials(_symbol(ticker, market), period=period)


@mcp.tool(title="Key ratios", annotations=_READ)
def get_key_ratios(ticker: str, market: str = "IN") -> Ratios:
    """Valuation, profitability, leverage, liquidity, growth and cash-flow ratios."""
    from .analysis.ratios import compute_ratios
    return compute_ratios(_symbol(ticker, market))


@mcp.tool(title="Compare peers", annotations=_READ)
def compare_peers(ticker: str, market: str = "IN") -> PeerComparison:
    """Competitor comparison table vs sector peers (revenue, margins, valuation, growth)."""
    from .analysis.peers import compare_peers as _compare
    return _compare(_symbol(ticker, market))


@mcp.tool(title="Industry intelligence", annotations=_READ)
def get_industry_intelligence(ticker: str, market: str = "IN") -> IndustryIntelligence:
    """Sector sub-domains, demand drivers, industry CAGR and risks."""
    from .analysis.industry import get_industry_intelligence as _ii
    return _ii(_symbol(ticker, market))


@mcp.tool(title="Company news", annotations=_READ)
def get_news(ticker: str, limit: int = 15, market: str = "IN") -> NewsFeed:
    """Recent company news, categorized (earnings, M&A, management, legal, product/AI)."""
    from .sources import data
    from .sources.news import get_news as _news
    symbol = _symbol(ticker, market)
    name = data.get_profile(symbol).name
    return _news(symbol, name, limit=limit)


@mcp.tool(title="Management & ownership", annotations=_READ)
def get_management(ticker: str, market: str = "IN") -> Management:
    """Executives, promoter/insider/institutional holding and capital-allocation signals."""
    from .analysis.management import get_management as _mgmt
    return _mgmt(_symbol(ticker, market))


@mcp.tool(title="DCF valuation", annotations=_READ)
def dcf_valuation(
    ticker: str,
    discount_rate: float | None = None,
    terminal_growth: float | None = None,
    years: int | None = None,
    growth_rate: float | None = None,
    market: str = "IN",
) -> DCFResult:
    """Two-stage DCF: intrinsic value/share, margin of safety and expected return.

    Optional overrides: discount_rate (e.g. 0.12), terminal_growth (e.g. 0.04), years,
    growth_rate. Handles cases where statements and the stock trade in different currencies.
    """
    from .analysis.dcf import compute_dcf
    return compute_dcf(
        _symbol(ticker, market),
        discount_rate=discount_rate, terminal_growth=terminal_growth,
        years=years, growth_rate=growth_rate,
    )


@mcp.tool(title="Economic moat", annotations=_READ)
def moat_assessment(ticker: str, market: str = "IN") -> MoatSignals:
    """Economic-moat signals (brand/cost/scale/IP) with a 0-10 heuristic score."""
    from .analysis.moat import moat_assessment as _moat
    return _moat(_symbol(ticker, market))


@mcp.tool(title="Risk assessment", annotations=_READ)
def risk_assessment(ticker: str, market: str = "IN") -> RiskSignals:
    """Risk signals (leverage, currency, concentration, regulation) with a 0-5 safety score."""
    from .analysis.risk import risk_assessment as _risk
    return _risk(_symbol(ticker, market))


@mcp.tool(title="Investment score (0-100)", annotations=_READ)
def score_company(ticker: str, market: str = "IN") -> Score:
    """The 0-100 investment rating with its eleven weighted buckets and rationale."""
    from .analysis.dcf import compute_dcf
    from .analysis.industry import industry_outlook
    from .analysis.peers import compare_peers as _compare
    from .analysis.ratios import compute_ratios
    from .analysis.scoring import compute_score
    from .sources import data

    symbol = _symbol(ticker, market)
    info = data.get_info(symbol)
    ratios = compute_ratios(symbol, info=info)
    dcf = compute_dcf(symbol, info=info, ratios=ratios)
    outlook, cagr = industry_outlook(symbol)
    peers = _compare(symbol)
    share = next((p.market_share_proxy for p in peers.peers if p.ticker == symbol), None)
    return compute_score(
        symbol, ratios, dcf=dcf, sector=info.get("sector"),
        market_share_proxy=share, industry_outlook=outlook, industry_cagr_hint=cagr,
        esg_total=data.get_esg_score(symbol),
    )


@mcp.tool(title="Full analysis", annotations=_READ)
def analyze_company(query: str, market: str = "IN") -> AnalysisReport:
    """Full investment analysis for a company name or ticker.

    Bundles profile, ratios, peer comparison, DCF, moat, risk, management, news, the 0-100
    score, plus SWOT seeds and growth-driver hints for the host LLM to turn into a narrative.
    """
    from .analysis.report import analyze
    return analyze(query, market)


@mcp.tool(title="SEC EDGAR facts", annotations=_READ)
def get_sec_facts(ticker_or_cik: str) -> dict:
    """SEC EDGAR company facts (US-listed companies / Indian ADRs only). Optional cross-check."""
    from .sources.sec_edgar import get_sec_facts as _facts
    return _facts(ticker_or_cik)


@mcp.tool(title="Data provider status", annotations=_READ)
def provider_status() -> dict[str, Any]:
    """Which data providers are active (licensed vs Yahoo fallback) and the disclosure note."""
    from .sources import data
    return data.provider_status()


def main() -> None:
    """Console-script entry point: run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
