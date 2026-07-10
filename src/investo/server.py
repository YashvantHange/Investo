"""Investo MCP server.

Exposes the analysis toolkit to an AI client (Claude Code, Claude Desktop, Cursor).
Run with ``python -m investo.server`` (stdio transport) or via the ``investo-mcp`` script.
"""

from __future__ import annotations

import functools
import re
from typing import Any, Callable, Optional

from mcp.server.fastmcp import FastMCP

from .resolve import resolve, resolve_ticker

_INSTRUCTIONS = (
    "Investo analyzes companies (India-first: NSE/BSE, plus US/global) from public data. "
    "Call `analyze_company` for a full report (profile, ratios, peers, DCF, moat, risk, news, "
    "SWOT seeds and a 0-100 rating), or the focused tools for one aspect. Pass a company name "
    "or a ticker; names are resolved to NSE (.NS)/BSE (.BO) tickers by default. Use the "
    "returned evidence to write the narrative; do not invent numbers. Research only, not advice."
)

mcp = FastMCP("Investo", instructions=_INSTRUCTIONS)

_TICKER_RE = re.compile(r"^[A-Za-z0-9&.-]{1,15}(\.[A-Za-z]{1,3})?$")


def safe_tool(fn: Callable) -> Callable:
    """Wrap a tool so failures return an ``{"error": ...}`` dict instead of crashing."""
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - surface any failure cleanly to the client
            return {"error": f"{type(exc).__name__}: {exc}"}
    return wrapper


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
@mcp.tool()
@safe_tool
def search_company(query: str, market: str = "IN") -> dict:
    """Resolve a company name to an exchange ticker (NSE/BSE preferred for India).

    Returns the best match plus ranked alternatives.
    """
    return resolve(query, market).model_dump()


@mcp.tool()
@safe_tool
def get_company_profile(ticker: str, market: str = "IN") -> dict:
    """Company profile: sector, industry, business summary, market cap, executives."""
    from .sources import yahoo
    return yahoo.get_profile(_symbol(ticker, market)).model_dump()


@mcp.tool()
@safe_tool
def get_financials(ticker: str, period: str = "annual", market: str = "IN") -> dict:
    """Income statement, balance sheet and cash flow (period = 'annual' or 'quarterly')."""
    from .sources import yahoo
    return yahoo.get_financials(_symbol(ticker, market), period=period).model_dump()


@mcp.tool()
@safe_tool
def get_key_ratios(ticker: str, market: str = "IN") -> dict:
    """Valuation, profitability, leverage, liquidity, growth and cash-flow ratios."""
    from .analysis.ratios import compute_ratios
    return compute_ratios(_symbol(ticker, market)).model_dump()


@mcp.tool()
@safe_tool
def compare_peers(ticker: str, market: str = "IN") -> dict:
    """Competitor comparison table vs sector peers (revenue, margins, valuation, growth)."""
    from .analysis.peers import compare_peers as _compare
    return _compare(_symbol(ticker, market)).model_dump()


@mcp.tool()
@safe_tool
def get_industry_intelligence(ticker: str, market: str = "IN") -> dict:
    """Sector sub-domains, demand drivers, industry CAGR and risks."""
    from .analysis.industry import get_industry_intelligence as _ii
    return _ii(_symbol(ticker, market)).model_dump()


@mcp.tool()
@safe_tool
def get_news(ticker: str, limit: int = 15, market: str = "IN") -> dict:
    """Recent company news, categorized (earnings, M&A, management, legal, product/AI)."""
    from .sources import yahoo
    from .sources.news import get_news as _news
    symbol = _symbol(ticker, market)
    name = yahoo.get_profile(symbol).name
    return _news(symbol, name, limit=limit).model_dump()


@mcp.tool()
@safe_tool
def get_management(ticker: str, market: str = "IN") -> dict:
    """Executives, promoter/insider/institutional holding and capital-allocation signals."""
    from .analysis.management import get_management as _mgmt
    return _mgmt(_symbol(ticker, market)).model_dump()


@mcp.tool()
@safe_tool
def dcf_valuation(
    ticker: str,
    discount_rate: Optional[float] = None,
    terminal_growth: Optional[float] = None,
    years: Optional[int] = None,
    growth_rate: Optional[float] = None,
    market: str = "IN",
) -> dict:
    """Two-stage DCF: intrinsic value/share, margin of safety and expected return.

    Optional overrides: discount_rate (e.g. 0.12), terminal_growth (e.g. 0.04), years,
    growth_rate. Handles cases where statements and the stock trade in different currencies.
    """
    from .analysis.dcf import compute_dcf
    return compute_dcf(
        _symbol(ticker, market),
        discount_rate=discount_rate, terminal_growth=terminal_growth,
        years=years, growth_rate=growth_rate,
    ).model_dump()


@mcp.tool()
@safe_tool
def moat_assessment(ticker: str, market: str = "IN") -> dict:
    """Economic-moat signals (brand/cost/scale/IP) with a 0-10 heuristic score."""
    from .analysis.moat import moat_assessment as _moat
    return _moat(_symbol(ticker, market)).model_dump()


@mcp.tool()
@safe_tool
def risk_assessment(ticker: str, market: str = "IN") -> dict:
    """Risk signals (leverage, currency, concentration, regulation) with a 0-5 safety score."""
    from .analysis.risk import risk_assessment as _risk
    return _risk(_symbol(ticker, market)).model_dump()


@mcp.tool()
@safe_tool
def score_company(ticker: str, market: str = "IN") -> dict:
    """The 0-100 investment rating with its eleven weighted buckets and rationale."""
    from .analysis.dcf import compute_dcf
    from .analysis.industry import industry_outlook
    from .analysis.peers import compare_peers as _compare
    from .analysis.ratios import compute_ratios
    from .analysis.scoring import compute_score
    from .sources import yahoo

    symbol = _symbol(ticker, market)
    info = yahoo.get_info(symbol)
    ratios = compute_ratios(symbol, info=info)
    dcf = compute_dcf(symbol, info=info, ratios=ratios)
    outlook, cagr = industry_outlook(symbol)
    peers = _compare(symbol)
    share = next((p.market_share_proxy for p in peers.peers if p.ticker == symbol), None)
    return compute_score(
        symbol, ratios, dcf=dcf, sector=info.get("sector"),
        market_share_proxy=share, industry_outlook=outlook, industry_cagr_hint=cagr,
        esg_total=yahoo.get_esg_score(symbol),
    ).model_dump()


@mcp.tool()
@safe_tool
def analyze_company(query: str, market: str = "IN") -> dict:
    """Full investment analysis for a company name or ticker.

    Bundles profile, ratios, peer comparison, DCF, moat, risk, management, news, the 0-100
    score, plus SWOT seeds and growth-driver hints for the host LLM to turn into a narrative.
    """
    from .analysis.report import analyze
    return analyze(query, market).model_dump()


@mcp.tool()
@safe_tool
def get_sec_facts(ticker_or_cik: str) -> dict:
    """SEC EDGAR company facts (US-listed companies / Indian ADRs only). Optional cross-check."""
    from .sources.sec_edgar import get_sec_facts as _facts
    return _facts(ticker_or_cik)


def main() -> None:
    """Console-script entry point: run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
