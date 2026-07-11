"""Investo MCP server.

Exposes the analysis toolkit to an AI client (Claude Code, Claude Desktop, Cursor).
Run with ``python -m investo.server`` (stdio transport) or via the ``investo-mcp`` script.

Every tool is read-only and hits external data APIs, so all are annotated
``readOnlyHint=True, openWorldHint=True``. Tools return typed pydantic models, so FastMCP
emits an output schema and structured content the client can render; failures surface as MCP
``isError`` results via FastMCP's built-in handling.
"""

from __future__ import annotations

import logging
import re
from typing import Annotated, Literal

import anyio
from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

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
    ProviderStatus,
    Ratios,
    RiskSignals,
    Score,
    SearchResult,
    SecFacts,
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

_log = logging.getLogger("investo.server")

# All tools are read-only data retrieval against external (open-world) APIs.
_READ = ToolAnnotations(readOnlyHint=True, openWorldHint=True)

# Validated enums / bounds -> surfaced in each tool's JSON input schema.
Market = Literal["IN", "US"]
Period = Literal["annual", "quarterly"]

_TICKER_RE = re.compile(r"^[A-Za-z0-9&.-]{1,15}(\.[A-Za-z]{1,3})?$")
_MAX_QUERY_LEN = 80


def _clean(text: str) -> str:
    """Validate and normalize a user-supplied company name / ticker."""
    s = (text or "").strip()
    if not s:
        raise ValueError("Empty company name or ticker.")
    if len(s) > _MAX_QUERY_LEN:
        raise ValueError(f"Query too long (max {_MAX_QUERY_LEN} characters).")
    return s


def _symbol(ticker_or_name: str, market: Market = "IN") -> str:
    """Accept a ticker or a company name; return a resolved exchange ticker."""
    s = _clean(ticker_or_name)
    if "." in s and _TICKER_RE.match(s):
        return s.upper()
    resolved = resolve_ticker(s, market)
    return resolved or s.upper()


# --------------------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------------------
@mcp.tool(title="Search company", annotations=_READ)
def search_company(query: str, market: Market = "IN") -> SearchResult:
    """Resolve a company name to an exchange ticker (NSE/BSE preferred for India).

    Returns the best match plus ranked alternatives.
    """
    return resolve(query, market)


@mcp.tool(title="Company profile", annotations=_READ)
def get_company_profile(ticker: str, market: Market = "IN") -> CompanyProfile:
    """Company profile: sector, industry, business summary, market cap, executives."""
    from .sources import data
    return data.get_profile(_symbol(ticker, market))


@mcp.tool(title="Financial statements", annotations=_READ)
def get_financials(ticker: str, period: Period = "annual", market: Market = "IN") -> Financials:
    """Income statement, balance sheet and cash flow (period = 'annual' or 'quarterly')."""
    from .sources import data
    return data.get_financials(_symbol(ticker, market), period=period)


@mcp.tool(title="Key ratios", annotations=_READ)
def get_key_ratios(ticker: str, market: Market = "IN") -> Ratios:
    """Valuation, profitability, leverage, liquidity, growth and cash-flow ratios."""
    from .analysis.ratios import compute_ratios
    return compute_ratios(_symbol(ticker, market))


@mcp.tool(title="Compare peers", annotations=_READ)
def compare_peers(ticker: str, market: Market = "IN") -> PeerComparison:
    """Competitor comparison table vs sector peers (revenue, margins, valuation, growth)."""
    from .analysis.peers import compare_peers as _compare
    return _compare(_symbol(ticker, market))


@mcp.tool(title="Industry intelligence", annotations=_READ)
def get_industry_intelligence(ticker: str, market: Market = "IN") -> IndustryIntelligence:
    """Sector sub-domains, demand drivers, industry CAGR and risks."""
    from .analysis.industry import get_industry_intelligence as _ii
    return _ii(_symbol(ticker, market))


@mcp.tool(title="Company news", annotations=_READ)
def get_news(ticker: str, limit: Annotated[int, Field(ge=1, le=50)] = 15, market: Market = "IN") -> NewsFeed:
    """Recent company news, categorized (earnings, M&A, management, legal, product/AI)."""
    from .sources import data
    from .sources.news import get_news as _news
    symbol = _symbol(ticker, market)
    name = data.get_profile(symbol).name
    return _news(symbol, name, limit=limit)


@mcp.tool(title="Management & ownership", annotations=_READ)
def get_management(ticker: str, market: Market = "IN") -> Management:
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
    market: Market = "IN",
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
def moat_assessment(ticker: str, market: Market = "IN") -> MoatSignals:
    """Economic-moat signals (brand/cost/scale/IP) with a 0-10 heuristic score."""
    from .analysis.moat import moat_assessment as _moat
    return _moat(_symbol(ticker, market))


@mcp.tool(title="Risk assessment", annotations=_READ)
def risk_assessment(ticker: str, market: Market = "IN") -> RiskSignals:
    """Risk signals (leverage, currency, concentration, regulation) with a 0-5 safety score."""
    from .analysis.risk import risk_assessment as _risk
    return _risk(_symbol(ticker, market))


@mcp.tool(title="Investment score (0-100)", annotations=_READ)
def score_company(ticker: str, market: Market = "IN") -> Score:
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
async def analyze_company(query: str, market: Market = "IN", ctx: Context | None = None) -> AnalysisReport:
    """Full investment analysis for a company name or ticker.

    Bundles profile, ratios, peer comparison, DCF, moat, risk, management, news, the 0-100
    score, plus SWOT seeds and growth-driver hints for the host LLM to turn into a narrative.
    Emits progress notifications while it works (~a few seconds).
    """
    from .analysis.report import analyze

    _clean(query)  # validate up front so bad input errors fast
    _log.info("analyze_company(%r, market=%s)", query, market)

    def on_progress(current: int, total: int, message: str) -> None:
        if ctx is not None:
            try:
                anyio.from_thread.run(ctx.report_progress, float(current), float(total), message)
            except Exception:  # progress is best-effort; never fail the analysis over it
                pass

    # The analysis is blocking (network I/O) -> run it off the event loop and bridge progress.
    return await anyio.to_thread.run_sync(lambda: analyze(query, market, progress=on_progress))


@mcp.tool(title="SEC EDGAR facts", annotations=_READ)
def get_sec_facts(ticker_or_cik: str) -> SecFacts:
    """SEC EDGAR company facts (US-listed companies / Indian ADRs only). Optional cross-check."""
    from .sources.sec_edgar import get_sec_facts as _facts
    return _facts(_clean(ticker_or_cik))


@mcp.tool(title="Data provider status", annotations=_READ)
def provider_status() -> ProviderStatus:
    """Which data providers are active (licensed vs Yahoo fallback) and the disclosure note."""
    from .sources import data
    return ProviderStatus(**data.provider_status())


def main() -> None:
    """Console-script entry point: run the MCP server over stdio."""
    from .logging_config import configure_logging
    configure_logging()
    _log.info("Investo MCP server starting (stdio); %d tools", 15)
    mcp.run()


if __name__ == "__main__":
    main()
