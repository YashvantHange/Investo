"""Investo MCP server.

Exposes the analysis toolkit to an AI client (Claude Code, Claude Desktop, Cursor).
Run with ``python -m investo.server`` (stdio transport) or via the ``investo-mcp`` script.

Almost every tool is read-only and hits external data APIs, so those are annotated
``readOnlyHint=True, openWorldHint=True``. The one exception is ``export_report``, which writes a
file and is annotated ``readOnlyHint=False``; its output path is sandboxed to the export directory.
Tools return typed pydantic models, so FastMCP emits an output schema and structured content the
client can render; failures surface as MCP ``isError`` results via FastMCP's built-in handling.
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
    AiSignals,
    AnalysisReport,
    BuffettChecklist,
    CompanyProfile,
    DCFResult,
    DcfSensitivity,
    ExportedFile,
    ExportResult,
    Financials,
    FundamentalTrend,
    GrowthOutlook,
    IndustryIntelligence,
    InvestmentThesis,
    Management,
    MoatSignals,
    MultiCompare,
    NewsFeed,
    PeerComparison,
    PeerGroupDirectory,
    ProviderStatus,
    Ratios,
    RedFlagReport,
    RelativeComparison,
    RiskSignals,
    Score,
    SearchResult,
    SecFacts,
    ShareholdingPattern,
    TechnicalSnapshot,
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

# Most tools are read-only data retrieval against external (open-world) APIs.
_READ = ToolAnnotations(readOnlyHint=True, openWorldHint=True)
# export_report writes a file — it is the one non-read-only tool.
_WRITE = ToolAnnotations(readOnlyHint=False, openWorldHint=True,
                         destructiveHint=False, idempotentHint=False)

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


def _safe_export_path(path: str | None, ext: str):
    """Resolve an LLM-supplied export path, confined to the export directory.

    ``path`` comes from a tool call, so it is untrusted. Any path that resolves outside the base
    directory — a ``..`` traversal, or an absolute path (on either OS) — is rejected outright
    rather than silently clamped, so the behaviour is identical on Windows and POSIX. A plain
    relative name, optionally with subdirectories, is allowed; the extension is forced to match
    the requested format.
    """
    import tempfile
    from pathlib import Path

    from .config import CONFIG

    base = Path(CONFIG.export_dir or (Path(tempfile.gettempdir()) / "investo-exports")).resolve()
    base.mkdir(parents=True, exist_ok=True)

    name = path or f"investo-export.{ext}"
    candidate = (base / name).resolve()
    if not candidate.is_relative_to(base):
        raise ValueError("Export path must stay inside the export directory.")
    return candidate.with_suffix(f".{ext}")


def _attach_html_report(report: AnalysisReport) -> None:
    """Auto-write an HTML report to the sandbox and record where it went on the report.

    A convenience so a full analysis leaves a shareable document without a second `export_report`
    call. It is best-effort: a filesystem hiccup records a warning rather than failing the
    analysis, so callers that only want the data still get it.
    """
    from datetime import datetime, timezone

    from . import __version__
    from .export import default_filename, file_url, preview_url, save_html

    report.generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    report.investo_version = __version__
    try:
        out = save_html(report, _safe_export_path(default_filename(report, "html"), "html"))
        report.html_report_path = str(out)
        report.html_report_url = file_url(out)          # file:// location
        report.html_report_open_url = preview_url(out)  # http link that opens it on click
        report.html_bytes = out.stat().st_size
    except Exception as exc:  # noqa: BLE001 — the convenience export must never sink the analysis
        _log.warning("automatic HTML export failed: %s", exc)
        report.warnings.append(f"Automatic HTML export failed: {exc}")


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


@mcp.tool(title="Growth engine (5-year)", annotations=_READ)
def growth_outlook(ticker: str, market: Market = "IN") -> GrowthOutlook:
    """The company's main growth engine for the next ~5 years: ranked drivers with estimated
    contribution %, per-driver risks, a catalyst timeline, and a blended growth band (sustainable
    growth, historical CAGR, analyst and industry estimates). Curated where available, else derived.
    """
    from .analysis.growth import growth_outlook as _go
    return _go(_symbol(ticker, market))


@mcp.tool(title="Fundamentals trend", annotations=_READ)
def fundamental_trend(ticker: str, market: Market = "IN") -> FundamentalTrend:
    """Multi-year trend of revenue, profit, margins, EPS and ROE with per-year direction and a
    qualitative health grade per metric — shows consistency at a glance.
    """
    from .analysis.trends import fundamental_trend as _ft
    return _ft(_symbol(ticker, market))


@mcp.tool(title="Shareholding pattern", annotations=_READ)
def shareholding_pattern(ticker: str, market: Market = "IN") -> ShareholdingPattern:
    """Ownership split (promoter / FII / DII / public + promoter pledge) with quarter-over-quarter
    smart observations and an overall ownership signal. Uses NSE/BSE filings for Indian names,
    falling back to Yahoo's coarse insider/institutional snapshot.
    """
    from .analysis.ownership import shareholding_pattern as _sp
    return _sp(_symbol(ticker, market))


@mcp.tool(title="Investment thesis", annotations=_READ)
def investment_thesis(ticker: str, market: Market = "IN") -> InvestmentThesis:
    """Synthesized pros/cons, an overall quality grade, a valuation stance and a one-line verdict
    (e.g. 'High Quality, Fairly Expensive'). Summarizes the full analysis without re-deriving numbers.
    """
    from .analysis.report import analyze
    report = analyze(ticker, market)
    return report.thesis or InvestmentThesis(ticker=_symbol(ticker, market))


@mcp.tool(title="AI signals digest", annotations=_READ)
def ai_signals(ticker: str, market: Market = "IN") -> AiSignals:
    """Compact machine-consumable digest (thesis, quality, confidence, ownership/growth signals,
    risk level, valuation stance, red flags) for other AI agents to consume headlessly.
    """
    from .analysis.report import analyze
    report = analyze(ticker, market)
    return report.ai_signals or AiSignals(ticker=_symbol(ticker, market))


@mcp.tool(title="Red flags", annotations=_READ)
def red_flags(ticker: str, market: Market = "IN") -> RedFlagReport:
    """Automated deterioration warnings (revenue up/profit down, rising debt, negative cash flow,
    margin compression, thin coverage/liquidity, promoter pledge) with an overall risk level.
    """
    from .analysis.redflags import detect_red_flags
    return detect_red_flags(_symbol(ticker, market))


@mcp.tool(title="Buffett checklist", annotations=_READ)
def buffett_checklist(ticker: str, market: Market = "IN") -> BuffettChecklist:
    """Warren Buffett–style quality checklist: a weighted 0-100 fit score with per-criterion
    pass/warn/fail, the reasoning, a derived confidence and a multi-year trend. This is a separate
    lens and does not change the 0-100 investment score.
    """
    from .analysis.buffett import buffett_checklist as _bc
    return _bc(_symbol(ticker, market))


@mcp.tool(title="Relative to industry", annotations=_READ)
def relative_metrics(ticker: str, market: Market = "IN") -> RelativeComparison:
    """Key metrics vs the peer-set median (an industry proxy), with favourable-side percentiles
    so a high percentile always reads as 'better' (ROE, margins, growth, P/E, P/B, D/E).
    """
    from .analysis.peers import compare_peers as _compare
    from .analysis.ratios import compute_ratios
    from .analysis.relative import relative_comparison

    symbol = _symbol(ticker, market)
    return relative_comparison(symbol, _compare(symbol), compute_ratios(symbol))


@mcp.tool(title="Technical snapshot", annotations=_READ)
def technical_snapshot(ticker: str, market: Market = "IN") -> TechnicalSnapshot:
    """Price/momentum context: 50/200-day moving averages and any golden/death cross, RSI(14),
    annualized volatility, 1-year max drawdown, beta vs the market index, and where the price
    sits in its 52-week range. This is *context, not a trading signal* — no buy/sell verdict.
    """
    from .analysis.technical import technical_snapshot as _tech
    return _tech(_symbol(ticker, market), market=market)


@mcp.tool(title="DCF sensitivity", annotations=_READ)
def dcf_sensitivity(ticker: str, market: Market = "IN") -> DcfSensitivity:
    """Intrinsic value per share across a discount-rate x terminal-growth grid, plus the
    break-even growth the market is implying at today's price. Shows how much the DCF rests on
    its two key assumptions rather than presenting a single fragile number.
    """
    from .analysis.sensitivity import dcf_sensitivity as _sens
    return _sens(_symbol(ticker, market), market)


@mcp.tool(title="Compare companies", annotations=_READ)
def compare_companies(
    tickers: Annotated[list[str], Field(min_length=2, max_length=6)],
    market: Market = "IN",
) -> MultiCompare:
    """Head-to-head comparison across 2-6 named tickers (not a curated peer group) — e.g. KPIT
    vs Tata Elxsi vs Tata Technologies. Revenue and market cap are normalized to the first
    ticker's trading currency; shares reported are within this set, not market share.
    """
    from .analysis.multi import compare_companies as _multi
    return _multi([_symbol(t, market) for t in tickers])


@mcp.tool(title="Peer group directory", annotations=_READ)
def peer_group_directory() -> PeerGroupDirectory:
    """List Investo's curated peer groups (label, outlook, industry CAGR, members) so a client
    can see how companies are grouped and why a given company is compared to a given cohort.
    """
    from .analysis.peers import peer_group_directory as _dir
    return _dir()


@mcp.tool(title="Export report", annotations=_WRITE)
def export_report(
    query: str,
    format: Literal["pdf", "html"] = "pdf",
    path: str | None = None,
    market: Market = "IN",
) -> ExportResult:
    """Render a full analysis to an HTML or PDF file and return where it was written.

    PDF uses a headless Chrome/Edge if one is installed, else a Playwright-managed Chromium;
    if neither is available the HTML is written and an error explains how to enable PDF. The
    output path is sandboxed to the export directory (INVESTO_EXPORT_DIR, else a temp dir) —
    a caller cannot write outside it.
    """
    from .analysis.report import analyze
    from .export import PdfExportError, file_url, html_to_pdf, preview_url, save_html

    def _exported(p, fmt: Literal["pdf", "html"]) -> ExportedFile:
        return ExportedFile(path=str(p), file_url=file_url(p), open_url=preview_url(p),
                            format=fmt, bytes=p.stat().st_size)

    out = _safe_export_path(path, format)
    report = analyze(query, market)

    if format == "html":
        f = _exported(save_html(report, out), "html")
        return ExportResult(path=f.path, file_url=f.file_url, open_url=f.open_url, format="html",
                            bytes=f.bytes, engine="renderer", files=[f])

    from .render import render_html
    html = render_html(report)
    sidecar = out.with_suffix(".html")
    sidecar.write_text(html, encoding="utf-8")  # sidecar survives a PDF failure
    try:
        engine, warnings = html_to_pdf(html, out)
    except PdfExportError as exc:
        raise ValueError(f"{exc}") from exc
    # Return the location and an open link for the pdf and its html sidecar (primary first).
    pdf, html_side = _exported(out, "pdf"), _exported(sidecar, "html")
    return ExportResult(path=pdf.path, file_url=pdf.file_url, open_url=pdf.open_url, format="pdf",
                        bytes=pdf.bytes, engine=engine, warnings=warnings, files=[pdf, html_side])


@mcp.tool(title="Full analysis", annotations=_WRITE)
async def analyze_company(query: str, market: Market = "IN", emit_html: bool = True,
                          ctx: Context | None = None) -> AnalysisReport:
    """Full investment analysis for a company name or ticker.

    Bundles profile, ratios, peer comparison, DCF, moat, risk, management, news, the 0-100
    score, plus SWOT seeds and growth-driver hints for the host LLM to turn into a narrative.
    Emits progress notifications while it works (~a few seconds).

    Unless ``emit_html`` is False, it also writes a self-contained HTML research note to the
    export directory and returns its location in ``html_report_path`` (with ``generated_at``,
    ``investo_version`` and ``html_bytes``), so a client can open the rendered report without a
    second ``export_report`` call. Writing the file is why this tool is not marked read-only.
    """
    from .analysis.report import analyze

    _clean(query)  # validate up front so bad input errors fast
    _log.info("analyze_company(%r, market=%s, emit_html=%s)", query, market, emit_html)

    def on_progress(current: int, total: int, message: str) -> None:
        if ctx is not None:
            try:
                anyio.from_thread.run(ctx.report_progress, float(current), float(total), message)
            except Exception:  # progress is best-effort; never fail the analysis over it
                pass

    def _run() -> AnalysisReport:
        report = analyze(query, market, progress=on_progress)
        if emit_html:
            _attach_html_report(report)
        return report

    # The analysis is blocking (network I/O) -> run it off the event loop and bridge progress.
    return await anyio.to_thread.run_sync(_run)


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
    _log.info("Investo MCP server starting (stdio); %d tools", _tool_count())
    mcp.run()


def _tool_count() -> int:
    """Number of registered tools (best-effort; for the startup log only)."""
    try:
        return len(mcp._tool_manager._tools)  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - private API, never fail startup over a log line
        return 0


if __name__ == "__main__":
    main()
