"""Typed, JSON-serializable data models returned by Investo's tools.

Almost every field is Optional: public data sources frequently omit values, and a tool
should degrade gracefully (return what it has) rather than fail. Downstream consumers
(the host LLM) should treat ``None`` as "unknown / not available".
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore")


# --------------------------------------------------------------------------------------
# Evidence layer — provenance, confidence and per-module quality metadata.
# Attached across the analysis modules so downstream agents can judge reliability
# (see analysis/evidence.py for the deterministic confidence formula).
# --------------------------------------------------------------------------------------
ConfidenceTier = Literal["High", "Medium", "Low"]


class Provenance(_Base):
    """Where a figure came from, and for what period."""

    source: str  # e.g. "Yahoo Finance", "NSE Shareholding Filing", "Annual Reports", "Curated"
    detail: str | None = None  # e.g. "FY21-FY25", "trailing 12m"
    as_of: str | None = None  # ISO date / period label of the underlying data


class Confidence(_Base):
    """Derived reliability of a figure or judgment (never asserted, always computed)."""

    score: float  # 0..1
    tier: ConfidenceTier
    reason: str | None = None  # why this confidence, in plain language


class EvidenceMeta(_Base):
    """Per-module transparency block: how complete/reliable this section is."""

    confidence: Confidence | None = None
    data_coverage: float | None = None  # 0..1 fraction of expected fields present
    sources: list[Provenance] = Field(default_factory=list)
    source_count: int = 0
    missing_fields: list[str] = Field(default_factory=list)
    as_of: str | None = None  # latest underlying data date
    notes: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------------------
# Identity / search
# --------------------------------------------------------------------------------------
class TickerCandidate(_Base):
    """A single search match when resolving a company name to a ticker."""

    symbol: str
    name: str | None = None
    exchange: str | None = None
    market: str | None = None  # "IN" | "US" | other
    quote_type: str | None = None
    score: float | None = None  # ranking hint (higher = better)


class SearchResult(_Base):
    query: str
    resolved: TickerCandidate | None = None
    candidates: list[TickerCandidate] = Field(default_factory=list)
    note: str | None = None


# --------------------------------------------------------------------------------------
# Profile
# --------------------------------------------------------------------------------------
class CompanyProfile(_Base):
    ticker: str
    name: str | None = None
    exchange: str | None = None
    market: str | None = None
    country: str | None = None
    currency: str | None = None
    sector: str | None = None
    industry: str | None = None
    website: str | None = None
    business_summary: str | None = None
    employees: int | None = None
    market_cap: float | None = None
    current_price: float | None = None
    fifty_two_week_high: float | None = None
    fifty_two_week_low: float | None = None
    key_executives: list[dict[str, Any]] = Field(default_factory=list)


# --------------------------------------------------------------------------------------
# Financial statements
# --------------------------------------------------------------------------------------
class FinancialPeriod(_Base):
    """One reporting period's worth of line items for a single statement."""

    period: str  # e.g. "2024-03-31"
    values: dict[str, float | None] = Field(default_factory=dict)


class Financials(_Base):
    ticker: str
    currency: str | None = None
    period_type: Literal["annual", "quarterly"] = "annual"
    income_statement: list[FinancialPeriod] = Field(default_factory=list)
    balance_sheet: list[FinancialPeriod] = Field(default_factory=list)
    cash_flow: list[FinancialPeriod] = Field(default_factory=list)


# --------------------------------------------------------------------------------------
# Ratios
# --------------------------------------------------------------------------------------
class Ratios(_Base):
    ticker: str
    currency: str | None = None

    # Valuation
    pe: float | None = None
    forward_pe: float | None = None
    pb: float | None = None
    peg: float | None = None
    ev_ebitda: float | None = None
    price_to_sales: float | None = None
    dividend_yield: float | None = None

    # Profitability / returns
    roe: float | None = None
    roa: float | None = None
    roce: float | None = None
    roic: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    net_margin: float | None = None

    # Leverage / liquidity
    debt_to_equity: float | None = None
    interest_coverage: float | None = None
    current_ratio: float | None = None
    quick_ratio: float | None = None

    # Growth
    revenue_growth_yoy: float | None = None
    revenue_cagr_3y: float | None = None
    earnings_growth_yoy: float | None = None
    eps_cagr_3y: float | None = None

    # Cash flow
    fcf: float | None = None
    fcf_margin: float | None = None
    ocf_to_ebitda: float | None = None

    # Other
    beta: float | None = None
    rd_intensity: float | None = None  # R&D / revenue


# --------------------------------------------------------------------------------------
# Peers
# --------------------------------------------------------------------------------------
class PeerRow(_Base):
    ticker: str
    name: str | None = None
    market_cap: float | None = None
    revenue_ttm: float | None = None
    net_margin: float | None = None
    operating_margin: float | None = None
    pe: float | None = None
    pb: float | None = None
    roe: float | None = None
    revenue_growth_yoy: float | None = None
    debt_to_equity: float | None = None
    market_share_proxy: float | None = None  # revenue / sum(revenue) within peer set


class PeerComparison(_Base):
    ticker: str
    sector: str | None = None
    peers: list[PeerRow] = Field(default_factory=list)
    summary: list[str] = Field(default_factory=list)  # grounded observations
    note: str | None = None


# --------------------------------------------------------------------------------------
# Industry intelligence
# --------------------------------------------------------------------------------------
class IndustryIntelligence(_Base):
    ticker: str
    sector: str | None = None
    industry: str | None = None
    sub_domains: list[str] = Field(default_factory=list)
    demand_drivers: list[str] = Field(default_factory=list)
    future_demand: str | None = None
    industry_cagr: str | None = None  # curated string e.g. "~10-12% (FY24-30, est.)"
    risks: list[str] = Field(default_factory=list)
    source: Literal["curated", "keyed", "unknown"] = "curated"
    note: str | None = None


# --------------------------------------------------------------------------------------
# News
# --------------------------------------------------------------------------------------
NewsCategory = Literal["earnings", "m&a", "management", "legal-regulatory", "product-ai", "general"]


class NewsItem(_Base):
    title: str
    publisher: str | None = None
    link: str | None = None
    published: str | None = None  # ISO date string
    category: NewsCategory = "general"


class NewsFeed(_Base):
    ticker: str
    items: list[NewsItem] = Field(default_factory=list)
    note: str | None = None


# --------------------------------------------------------------------------------------
# Management
# --------------------------------------------------------------------------------------
class Management(_Base):
    ticker: str
    key_executives: list[dict[str, Any]] = Field(default_factory=list)
    promoter_holding: float | None = None       # % (best-effort; often unavailable for India)
    insider_holding: float | None = None        # %
    institutional_holding: float | None = None   # %
    roic: float | None = None
    dividend_payout_ratio: float | None = None
    buyback_signal: bool | None = None
    capital_allocation_notes: list[str] = Field(default_factory=list)
    note: str | None = None


# --------------------------------------------------------------------------------------
# DCF
# --------------------------------------------------------------------------------------
class DCFResult(_Base):
    ticker: str
    currency: str | None = None
    base_fcf: float | None = None
    growth_rate: float | None = None
    discount_rate: float | None = None
    terminal_growth: float | None = None
    years: int | None = None
    enterprise_value: float | None = None
    equity_value: float | None = None
    intrinsic_value_per_share: float | None = None
    current_price: float | None = None
    margin_of_safety: float | None = None   # (intrinsic - price) / intrinsic
    expected_return: float | None = None    # (intrinsic - price) / price
    assumptions: list[str] = Field(default_factory=list)
    note: str | None = None


# --------------------------------------------------------------------------------------
# Moat & Risk
# --------------------------------------------------------------------------------------
class MoatSignals(_Base):
    ticker: str
    gross_margin: float | None = None
    margin_stability: float | None = None  # lower stdev => more durable
    roic: float | None = None
    market_share_proxy: float | None = None
    rd_intensity: float | None = None
    scale_rank: int | None = None  # rank within peer set by revenue (1 = largest)
    moat_score: float | None = None  # 0-10 heuristic
    sources: list[str] = Field(default_factory=list)  # candidate moat sources present
    signals: list[str] = Field(default_factory=list)
    note: str | None = None


class RiskSignals(_Base):
    ticker: str
    debt_to_equity: float | None = None
    interest_coverage: float | None = None
    beta: float | None = None
    currency_exposure: str | None = None
    customer_concentration: str | None = None
    regulatory_flags: list[str] = Field(default_factory=list)
    risk_score: float | None = None  # 0-5 heuristic (higher = safer)
    signals: list[str] = Field(default_factory=list)
    note: str | None = None


# --------------------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------------------
class ScoreBucket(_Base):
    name: str
    weight: float           # max points this bucket contributes to the 100
    score: float            # points earned (0..weight)
    normalized: float       # 0..1 (score / weight)
    kind: Literal["computed", "heuristic"] = "computed"
    rationale: str | None = None
    drivers: dict[str, float | None] = Field(default_factory=dict)


class Score(_Base):
    ticker: str
    total: float                 # 0..100
    verdict: str                 # e.g. "Strong" | "Fair" | "Weak"
    buckets: list[ScoreBucket] = Field(default_factory=list)
    esg_included: bool = False
    note: str | None = None


# --------------------------------------------------------------------------------------
# Relative-to-industry comparison
# --------------------------------------------------------------------------------------
class RelativeMetric(_Base):
    name: str
    company: float | None = None
    industry: float | None = None  # peer-set median (industry proxy)
    percentile: float | None = None  # 0..1 rank within the peer set
    better: bool | None = None  # is the company on the favourable side of the median?
    delta: float | None = None  # company - industry
    higher_is_better: bool = True
    provenance: Provenance | None = None


class RelativeComparison(_Base):
    ticker: str
    metrics: list[RelativeMetric] = Field(default_factory=list)
    peer_count: int = 0
    summary: list[str] = Field(default_factory=list)
    evidence: EvidenceMeta | None = None
    note: str | None = None


# --------------------------------------------------------------------------------------
# Warren Buffett checklist
# --------------------------------------------------------------------------------------
CriterionStatus = Literal["pass", "warn", "fail", "unknown"]


class TrendPoint(_Base):
    period: str
    value: float | None = None


class BuffettCriterion(_Base):
    name: str
    weight: float  # contribution to the weighted /100 score
    value: float | None = None
    threshold: str  # human-readable rule, e.g. "ROE > 15%"
    status: CriterionStatus = "unknown"
    reason: str | None = None  # the WHY
    confidence: Confidence | None = None
    provenance: Provenance | None = None
    trend: list[TrendPoint] = Field(default_factory=list)  # newest-first historical values
    trend_verdict: str | None = None  # e.g. "Consistently Excellent"


class BuffettChecklist(_Base):
    ticker: str
    criteria: list[BuffettCriterion] = Field(default_factory=list)
    weighted_score: float | None = None  # 0..100 (weights of applicable criteria renormalized)
    passed_count: int = 0
    applicable_count: int = 0
    verdict: str | None = None  # e.g. "Strong Buffett fit"
    evidence: EvidenceMeta | None = None
    note: str | None = None


# --------------------------------------------------------------------------------------
# Shareholding pattern (ownership)
# --------------------------------------------------------------------------------------
OwnershipSignal = Literal["bullish", "positive", "neutral", "cautious", "bearish"]


class HolderBreakdown(_Base):
    """One quarter's ownership split (percentages as fractions of 1.0)."""

    period: str  # e.g. "2026-03-31" or "current (Yahoo)"
    promoter: float | None = None
    fii: float | None = None  # foreign institutional
    dii: float | None = None  # domestic institutional
    institutional: float | None = None  # combined, when FII/DII not separated
    public: float | None = None
    retail: float | None = None
    promoter_pledge: float | None = None
    provenance: Provenance | None = None


class ShareholdingPattern(_Base):
    ticker: str
    source: Literal["bse", "nse", "yahoo", "unknown"] = "unknown"
    latest: HolderBreakdown | None = None
    history: list[HolderBreakdown] = Field(default_factory=list)  # newest-first
    top_institutions: list[dict[str, Any]] = Field(default_factory=list)
    observations: list[str] = Field(default_factory=list)  # smart alerts
    ownership_signal: OwnershipSignal | None = None
    evidence: EvidenceMeta | None = None
    note: str | None = None


# --------------------------------------------------------------------------------------
# 5-year growth engine
# --------------------------------------------------------------------------------------
GrowthSignal = Literal["strong", "moderate", "weak"]
DriverSource = Literal["curated", "industry", "news", "derived"]


class GrowthDriver(_Base):
    rank: int
    name: str
    detail: str | None = None
    contribution_pct: float | None = None  # estimated share of forward growth (fraction of 1.0)
    confidence: Confidence | None = None
    risks: list[str] = Field(default_factory=list)
    source: DriverSource = "derived"


class Catalyst(_Base):
    year: int | None = None
    event: str
    confidence: Confidence | None = None


class GrowthOutlook(_Base):
    ticker: str
    primary_engine: str | None = None
    sustainable_growth: float | None = None  # ROE * (1 - payout)
    historical_revenue_cagr_3y: float | None = None
    historical_eps_cagr_3y: float | None = None
    analyst_growth_est: float | None = None  # forward, best-effort
    industry_cagr: str | None = None
    blended_5y_low: float | None = None
    blended_5y_high: float | None = None
    drivers: list[GrowthDriver] = Field(default_factory=list)
    catalysts: list[Catalyst] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    growth_signal: GrowthSignal | None = None
    evidence: EvidenceMeta | None = None
    note: str | None = None


# --------------------------------------------------------------------------------------
# Fundamentals trend
# --------------------------------------------------------------------------------------
HealthGrade = Literal["Excellent", "Good", "Stable", "Weak", "Poor"]


class MetricTrend(_Base):
    name: str
    periods: list[str] = Field(default_factory=list)  # newest-first labels
    values: list[float | None] = Field(default_factory=list)
    directions: list[str] = Field(default_factory=list)  # per YoY step: "up"|"flat"|"down"
    health: HealthGrade | None = None
    cagr: float | None = None


class FundamentalTrend(_Base):
    ticker: str
    metrics: list[MetricTrend] = Field(default_factory=list)
    financial_health: dict[str, str] = Field(default_factory=dict)  # {"Revenue": "Excellent", ...}
    overall_health: HealthGrade | None = None
    evidence: EvidenceMeta | None = None
    note: str | None = None


# --------------------------------------------------------------------------------------
# Red flags
# --------------------------------------------------------------------------------------
Severity = Literal["low", "moderate", "high", "severe"]


class RedFlag(_Base):
    issue: str
    severity: Severity = "moderate"
    detail: str | None = None
    provenance: Provenance | None = None


class RedFlagReport(_Base):
    ticker: str
    flags: list[RedFlag] = Field(default_factory=list)
    risk_level: Severity | Literal["none"] = "none"
    evidence: EvidenceMeta | None = None
    note: str | None = None


# --------------------------------------------------------------------------------------
# Investment thesis + AI-ready digest
# --------------------------------------------------------------------------------------
QualityGrade = Literal["Excellent", "Good", "Fair", "Weak", "Poor"]
ValuationStance = Literal["cheap", "fair", "expensive"]


class InvestmentThesis(_Base):
    ticker: str
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    quality: QualityGrade | None = None
    valuation_stance: ValuationStance | None = None
    verdict: str | None = None  # one-liner, e.g. "High Quality, Fairly Expensive"
    summary: str | None = None
    confidence: Confidence | None = None
    evidence: EvidenceMeta | None = None


class AiSignals(_Base):
    """Compact, machine-consumable digest for headless AI agents."""

    ticker: str
    investment_thesis: str | None = None
    overall_quality: QualityGrade | None = None
    confidence: float | None = None  # 0..1
    ownership_signal: OwnershipSignal | None = None
    growth_signal: GrowthSignal | None = None
    risk_level: Severity | Literal["none"] | None = None
    valuation_stance: ValuationStance | None = None
    red_flags: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------------------
# Signals / SWOT seeds / master report
# --------------------------------------------------------------------------------------
class Signal(_Base):
    polarity: Literal["positive", "negative", "neutral"]
    category: str
    text: str


SwotBucket = Literal["strength", "weakness", "opportunity", "threat"]


class SwotSeed(_Base):
    bucket: SwotBucket
    text: str


class AnalysisReport(_Base):
    """Master evidence bundle returned by analyze_company.

    The host LLM turns this into the sector explainer, SWOT, growth drivers,
    advantages/disadvantages, and the final rating narrative.
    """

    query: str
    resolved: TickerCandidate | None = None
    profile: CompanyProfile | None = None
    ratios: Ratios | None = None
    peers: PeerComparison | None = None
    industry: IndustryIntelligence | None = None
    news: NewsFeed | None = None
    management: Management | None = None
    dcf: DCFResult | None = None
    moat: MoatSignals | None = None
    risk: RiskSignals | None = None
    score: Score | None = None
    # Analyst-grade evidence layer (see analysis/*.py). Optional so the report degrades
    # gracefully when a module can't be computed for a given symbol.
    relative: RelativeComparison | None = None
    buffett: BuffettChecklist | None = None
    shareholding: ShareholdingPattern | None = None
    growth_outlook: GrowthOutlook | None = None
    fundamental_trend: FundamentalTrend | None = None
    red_flags: RedFlagReport | None = None
    thesis: InvestmentThesis | None = None
    ai_signals: AiSignals | None = None
    evidence: EvidenceMeta | None = None  # overall report quality/coverage
    signals: list[Signal] = Field(default_factory=list)
    swot_seeds: list[SwotSeed] = Field(default_factory=list)
    growth_driver_hints: list[str] = Field(default_factory=list)
    llm_guidance: str | None = None
    warnings: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------------------
# Provider status & SEC facts (typed so every tool exposes a precise output schema)
# --------------------------------------------------------------------------------------
class ProviderStatus(_Base):
    primary_when_available: str
    fallback: str
    alphavantage: bool
    fmp: bool
    finnhub: bool
    note: str | None = None


class SecFact(_Base):
    concept: str
    value: float | None = None
    end: str | None = None
    form: str | None = None


class SecFacts(_Base):
    cik: int | None = None
    entity: str | None = None
    facts: list[SecFact] = Field(default_factory=list)
    error: str | None = None
