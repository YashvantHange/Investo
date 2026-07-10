"""The master orchestrator behind ``analyze_company``.

Resolves a query to a ticker, gathers every module's output, computes the composite score,
and derives grounded *signals*, *SWOT seeds* and *growth-driver hints* that the host LLM turns
into the final narrative (what the company does, competitor comparison, SWOT,
advantages/disadvantages, growth drivers, risks, and the rating).
"""

from __future__ import annotations

from typing import Optional

from ..models import AnalysisReport, Signal, SwotSeed
from ..resolve import resolve
from ..sources import yahoo
from ..sources.news import get_news
from .dcf import compute_dcf
from .industry import get_industry_intelligence, industry_outlook
from .management import get_management
from .moat import moat_assessment
from .peers import compare_peers
from .ratios import compute_ratios
from .risk import risk_assessment
from .scoring import compute_score

_LLM_GUIDANCE = (
    "You are Investo. Using ONLY the structured evidence in this report (do not invent "
    "numbers), write: (1) what the company does and its sector/sub-domains; (2) a competitor "
    "comparison from `peers`; (3) a SWOT built from `swot_seeds`; (4) advantages and "
    "disadvantages from `signals`; (5) growth drivers from `growth_driver_hints`; (6) key "
    "risks from `risk`; then (7) present the rating `score.total`/100 with its bucket table "
    "and the DCF. Close with a one-line reminder that this is research, not investment advice."
)


def _subject_share(peers, symbol: str) -> Optional[float]:
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


def analyze(query: str, market: str = "IN") -> AnalysisReport:
    search = resolve(query, market)
    report = AnalysisReport(query=query, resolved=search.resolved)
    if search.note:
        report.warnings.append(search.note)
    if search.resolved is None:
        report.warnings.append("Could not resolve the company to a ticker.")
        report.llm_guidance = "Ask the user for a ticker (e.g. INFY.NS) or a clearer company name."
        return report

    symbol = search.resolved.symbol
    info = yahoo.get_info(symbol)

    profile = yahoo.get_profile(symbol)
    financials = yahoo.get_financials(symbol)
    ratios = compute_ratios(symbol, info=info, financials=financials)
    dcf = compute_dcf(symbol, info=info, financials=financials, ratios=ratios)
    peers = compare_peers(symbol)
    industry = get_industry_intelligence(symbol)
    outlook, cagr = industry_outlook(symbol)
    news = get_news(symbol, profile.name)
    management = get_management(symbol, info=info, financials=financials, ratios=ratios)
    share = _subject_share(peers, symbol)
    moat = moat_assessment(symbol, ratios=ratios, market_share_proxy=share)
    risk = risk_assessment(symbol, ratios=ratios, info=info)
    esg = yahoo.get_esg_score(symbol)
    product_news = any(i.category == "product-ai" for i in news.items)

    score = compute_score(
        symbol, ratios,
        dcf=dcf, sector=profile.sector, market_share_proxy=share,
        promoter_holding=management.promoter_holding,
        industry_outlook=outlook, industry_cagr_hint=cagr,
        product_news=product_news, esg_total=esg,
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
    report.signals = signals
    report.swot_seeds = _build_swot(signals, industry, risk)
    report.growth_driver_hints = _build_growth_hints(ratios, industry, news)
    report.llm_guidance = _LLM_GUIDANCE

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
    return report
