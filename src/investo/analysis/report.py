"""The master orchestrator behind ``analyze_company``.

Resolves a query to a ticker, gathers every module's output, computes the composite score,
and derives grounded *signals*, *SWOT seeds* and *growth-driver hints* that the host LLM turns
into the final narrative (what the company does, competitor comparison, SWOT,
advantages/disadvantages, growth drivers, risks, and the rating).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from ..models import AnalysisReport, Signal, SwotSeed
from ..resolve import resolve
from ..sources import data
from ..sources.news import get_news
from . import evidence as ev
from .buffett import buffett_checklist
from .dcf import compute_dcf
from .growth import growth_outlook
from .industry import get_industry_intelligence, industry_outlook
from .management import get_management
from .moat import moat_assessment
from .ownership import shareholding_pattern
from .peers import compare_peers
from .ratios import compute_ratios
from .redflags import detect_red_flags
from .relative import relative_comparison
from .risk import risk_assessment
from .scoring import compute_score
from .thesis import build_ai_signals, build_thesis
from .trends import fundamental_trend

_log = logging.getLogger("investo.analysis.report")

_LLM_GUIDANCE = (
    "You are Investo. Produce a PROFESSIONAL, ANALYST-GRADE report in clean, well-formatted "
    "Markdown using ONLY the structured evidence here — never invent numbers. Use headed "
    "sections, tables, and ✓/⚠/✗ markers; keep it scannable. Order:\n"
    "1. HEADER: name, ticker, price, market cap, 52w range.\n"
    "2. INVESTMENT THESIS (lead with `thesis`): the one-line `verdict`, `summary`, then a "
    "Pros vs Cons table from `thesis.pros`/`thesis.cons`. Show `thesis.quality` and "
    "`thesis.valuation_stance`.\n"
    "3. RATING: `score.total`/100 (`score.verdict`) with the bucket table.\n"
    "4. RELATIVE TO INDUSTRY (`relative`): a table of company vs industry(median) + the "
    "percentile band for each metric.\n"
    "5. WARREN BUFFETT CHECKLIST (`buffett`): the weighted `weighted_score`/100 and `verdict`, "
    "then a table of each criterion — status (✓ pass / ⚠ warn / ✗ fail / — unknown), the "
    "`reason`, the `confidence.tier`, and the `trend_verdict` where present.\n"
    "6. SHAREHOLDING (`shareholding`): the latest promoter/FII/DII/public split and pledge, the "
    "quarter-over-quarter `observations`, and the `ownership_signal`; note the source (exchange "
    "filing vs Yahoo snapshot).\n"
    "7. GROWTH ENGINE — NEXT 5 YEARS (`growth_outlook`): the `primary_engine`, a ranked table of "
    "`drivers` (name, ~contribution %, confidence, key risks), the `catalysts` timeline "
    "(year → event), the blended 5y band and `growth_signal`.\n"
    "8. FUNDAMENTALS TREND (`fundamental_trend`): a compact table per metric with the ⬆/➡/⬇ "
    "`directions` and `health` grade, and the `overall_health`.\n"
    "9. RED FLAGS (`red_flags`): the `risk_level` and each flag with its severity; say so "
    "explicitly if none.\n"
    "10. WHAT IT DOES, competitor comparison (`peers`), SWOT (`swot_seeds`), key risks (`risk`), "
    "and the DCF (respect any low-confidence note).\n"
    "11. ANALYSIS QUALITY FOOTER (`evidence`): overall confidence (score + tier), data coverage, "
    "source count, latest data date (`as_of`), and any `missing_fields`.\n"
    "Surface confidence and provenance wherever the evidence provides them so the reader can "
    "judge reliability. Close with one line: research/education only, not investment advice."
)


def _subject_share(peers, symbol: str) -> float | None:
    for row in peers.peers:
        if row.ticker == symbol.upper():
            return row.market_share_proxy
    return None


def _build_signals(score) -> list[Signal]:
    signals: list[Signal] = []
    for b in score.buckets:
        if b.normalized >= 0.66:
            signals.append(Signal(polarity="positive", category=b.name, text=f"{b.name}: {b.rationale}"))
        elif b.normalized <= 0.34:
            signals.append(Signal(polarity="negative", category=b.name, text=f"{b.name}: {b.rationale}"))
    return signals


def _build_swot(signals, industry, risk) -> list[SwotSeed]:
    swot: list[SwotSeed] = []
    for s in signals:
        if s.polarity == "positive":
            swot.append(SwotSeed(bucket="strength", text=s.text))
        elif s.polarity == "negative":
            swot.append(SwotSeed(bucket="weakness", text=s.text))
    for d in industry.demand_drivers[:4]:
        swot.append(SwotSeed(bucket="opportunity", text=d))
    for r in industry.risks[:3]:
        swot.append(SwotSeed(bucket="threat", text=r))
    for rf in risk.regulatory_flags[:2]:
        swot.append(SwotSeed(bucket="threat", text=rf))
    return swot


def _build_growth_hints(ratios, industry, news) -> list[str]:
    hints: list[str] = []
    categories = {item.category for item in news.items}
    if "product-ai" in categories:
        hints.append("Recent product / AI initiatives in the news flow.")
    if "m&a" in categories:
        hints.append("Inorganic growth signalled by recent M&A news.")
    if ratios.revenue_cagr_3y is not None:
        hints.append(f"Revenue 3y CAGR of {ratios.revenue_cagr_3y:.1%}.")
    if ratios.rd_intensity:
        hints.append(f"R&D investment at {ratios.rd_intensity:.1%} of revenue.")
    hints.extend(industry.demand_drivers[:4])
    return hints


def _growth_hints_from_outlook(growth, ratios, industry, news) -> list[str]:
    """Prefer the ranked growth-engine drivers; fall back to the legacy hint builder."""
    hints: list[str] = []
    if growth is not None and growth.primary_engine:
        hints.append(f"Primary engine: {growth.primary_engine}")
    if growth is not None and growth.drivers:
        for d in growth.drivers[:4]:
            share = f" (~{d.contribution_pct:.0%})" if d.contribution_pct is not None else ""
            hints.append(f"{d.name}{share}")
    # Always include the news/CAGR-derived hints so nothing is lost.
    for h in _build_growth_hints(ratios, industry, news):
        if h not in hints:
            hints.append(h)
    return hints


ProgressFn = Callable[[int, int, str], None]


def _noop_progress(current: int, total: int, message: str) -> None:
    pass


def analyze(query: str, market: str = "IN", progress: ProgressFn | None = None) -> AnalysisReport:
    report_progress = progress or _noop_progress
    started = time.monotonic()
    report_progress(0, 5, "Resolving company")

    search = resolve(query, market)
    report = AnalysisReport(query=query, resolved=search.resolved)
    if search.note:
        report.warnings.append(search.note)
    if search.resolved is None:
        report.warnings.append("Could not resolve the company to a ticker.")
        report.llm_guidance = "Ask the user for a ticker (e.g. INFY.NS) or a clearer company name."
        _log.info("analyze(%r): unresolved", query)
        return report

    symbol = search.resolved.symbol
    _log.info("analyze(%r) -> %s", query, symbol)
    info = data.get_info(symbol)      # one network call, then cached for the rest
    profile = data.get_profile(symbol)  # reuses cached info
    report_progress(1, 5, f"Fetching financials, peers & news for {symbol}")

    # Run the independent, network-bound fetches concurrently (peers is itself parallel).
    with ThreadPoolExecutor(max_workers=5) as pool:
        f_financials = pool.submit(data.get_financials, symbol)
        f_peers = pool.submit(compare_peers, symbol)
        f_news = pool.submit(get_news, symbol, profile.name)
        f_esg = pool.submit(data.get_esg_score, symbol)
        f_shareholding = pool.submit(shareholding_pattern, symbol, info=info)
        financials = f_financials.result()
        peers = f_peers.result()
        news = f_news.result()
        esg = f_esg.result()
        shareholding = f_shareholding.result()

    report_progress(2, 5, "Computing ratios, DCF, moat & risk")
    ratios = compute_ratios(symbol, info=info, financials=financials)
    dcf = compute_dcf(symbol, info=info, financials=financials, ratios=ratios)
    industry = get_industry_intelligence(symbol)
    outlook, cagr = industry_outlook(symbol)
    management = get_management(symbol, info=info, financials=financials, ratios=ratios)
    share = _subject_share(peers, symbol)
    moat = moat_assessment(symbol, ratios=ratios, market_share_proxy=share)
    risk = risk_assessment(symbol, ratios=ratios, info=info)
    product_news = any(i.category == "product-ai" for i in news.items)

    report_progress(3, 5, "Scoring")
    score = compute_score(
        symbol, ratios,
        dcf=dcf, sector=profile.sector, market_share_proxy=share,
        promoter_holding=management.promoter_holding,
        industry_outlook=outlook, industry_cagr_hint=cagr,
        product_news=product_news, esg_total=esg,
    )

    report_progress(4, 5, "Buffett checklist, relative metrics, red flags & thesis")
    # Analyst-grade evidence layer. Each reuses data already fetched above (no extra network),
    # and each degrades gracefully to a mostly-empty result rather than raising.
    relative = relative_comparison(symbol, peers, ratios)
    buffett = buffett_checklist(
        symbol, ratios=ratios, dcf=dcf, moat=moat, management=management,
        financials=financials, info=info, sector=profile.sector,
    )
    growth = growth_outlook(
        symbol, ratios=ratios, info=info, industry=industry, sector=profile.sector,
        payout_ratio=management.dividend_payout_ratio,
    )
    trend = fundamental_trend(symbol, financials=financials)
    red_flags = detect_red_flags(
        symbol, ratios=ratios, financials=financials, info=info, shareholding=shareholding,
    )
    thesis = build_thesis(
        symbol, score=score, ratios=ratios, buffett=buffett, red_flags=red_flags,
        relative=relative, dcf=dcf, shareholding=shareholding, growth=growth,
    )
    ai_signals = build_ai_signals(
        symbol, thesis=thesis, red_flags=red_flags, shareholding=shareholding, growth=growth,
    )
    overall_evidence = ev.aggregate(
        [relative.evidence, buffett.evidence, growth.evidence, trend.evidence,
         shareholding.evidence, red_flags.evidence, thesis.evidence],
        notes=["Overall analysis quality blended across modules."],
    )

    signals = _build_signals(score)
    report.profile = profile
    report.ratios = ratios
    report.peers = peers
    report.industry = industry
    report.news = news
    report.management = management
    report.dcf = dcf
    report.moat = moat
    report.risk = risk
    report.score = score
    report.relative = relative
    report.buffett = buffett
    report.growth_outlook = growth
    report.fundamental_trend = trend
    report.shareholding = shareholding
    report.red_flags = red_flags
    report.thesis = thesis
    report.ai_signals = ai_signals
    report.evidence = overall_evidence
    report.signals = signals
    report.swot_seeds = _build_swot(signals, industry, risk)
    report.growth_driver_hints = _growth_hints_from_outlook(growth, ratios, industry, news)
    report.llm_guidance = _LLM_GUIDANCE

    # Degraded-mode: the source returned essentially nothing (rate-limited / delisted / unsupported).
    if profile.name is None and profile.market_cap is None and not financials.income_statement:
        report.warnings.append(
            "The data source returned little or no data for this symbol — it may be rate-limited, "
            "delisted, or unsupported. Retry shortly, or configure an API key (see the "
            "`provider_status` tool / README 'Data sources & legal')."
        )

    # Fitness-for-purpose caveats (help the reader not misread distorted numbers).
    if (ratios.revenue_growth_yoy is not None and ratios.revenue_growth_yoy < -0.30) or (
        ratios.revenue_cagr_3y is not None and ratios.revenue_cagr_3y < -0.25
    ):
        report.warnings.append(
            "Sharp revenue discontinuity detected — growth metrics may be distorted by a "
            "demerger, divestiture or restructuring rather than an operating decline; check "
            "recent news before trusting the growth score."
        )
    if profile.sector in {"Financial Services", "Financials", "Banks", "Insurance"}:
        report.warnings.append(
            "Financial-sector company: revenue-based growth and generic leverage ratios are less "
            "meaningful here (loan/AUM growth, NIM and asset quality matter more but aren't fully "
            "captured); weight the score accordingly."
        )

    # Surface data caveats.
    if ratios.currency and profile.currency and ratios.currency != profile.currency:
        report.warnings.append(
            f"Statements are in {ratios.currency} but the stock trades in {profile.currency}; "
            "cross-currency figures were FX-adjusted where possible."
        )
    if dcf.note:
        report.warnings.append(f"DCF: {dcf.note}")
    if not peers.peers:
        report.warnings.append(peers.note or "No peer comparison available.")
    if management.note:
        report.warnings.append(management.note)

    elapsed = time.monotonic() - started
    report_progress(5, 5, "Done")
    _log.info("analyze(%s) done in %.1fs (score=%s)", symbol, elapsed,
              report.score.total if report.score else "n/a")
    return report
