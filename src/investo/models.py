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
