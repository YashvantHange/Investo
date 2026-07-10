"""Typed, JSON-serializable data models returned by Investo's tools.

Almost every field is Optional: public data sources frequently omit values, and a tool
should degrade gracefully (return what it has) rather than fail. Downstream consumers
(the host LLM) should treat ``None`` as "unknown / not available".
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore")


# --------------------------------------------------------------------------------------
# Identity / search
# --------------------------------------------------------------------------------------
class TickerCandidate(_Base):
    """A single search match when resolving a company name to a ticker."""

    symbol: str
    name: Optional[str] = None
    exchange: Optional[str] = None
    market: Optional[str] = None  # "IN" | "US" | other
    quote_type: Optional[str] = None
    score: Optional[float] = None  # ranking hint (higher = better)


class SearchResult(_Base):
    query: str
    resolved: Optional[TickerCandidate] = None
    candidates: list[TickerCandidate] = Field(default_factory=list)
    note: Optional[str] = None


# --------------------------------------------------------------------------------------
# Profile
# --------------------------------------------------------------------------------------
class CompanyProfile(_Base):
    ticker: str
    name: Optional[str] = None
    exchange: Optional[str] = None
    market: Optional[str] = None
    country: Optional[str] = None
    currency: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    website: Optional[str] = None
    business_summary: Optional[str] = None
    employees: Optional[int] = None
    market_cap: Optional[float] = None
    current_price: Optional[float] = None
    fifty_two_week_high: Optional[float] = None
    fifty_two_week_low: Optional[float] = None
    key_executives: list[dict[str, Any]] = Field(default_factory=list)


# --------------------------------------------------------------------------------------
# Financial statements
# --------------------------------------------------------------------------------------
class FinancialPeriod(_Base):
    """One reporting period's worth of line items for a single statement."""

    period: str  # e.g. "2024-03-31"
    values: dict[str, Optional[float]] = Field(default_factory=dict)


class Financials(_Base):
    ticker: str
    currency: Optional[str] = None
    period_type: Literal["annual", "quarterly"] = "annual"
    income_statement: list[FinancialPeriod] = Field(default_factory=list)
    balance_sheet: list[FinancialPeriod] = Field(default_factory=list)
    cash_flow: list[FinancialPeriod] = Field(default_factory=list)


# --------------------------------------------------------------------------------------
# Ratios
# --------------------------------------------------------------------------------------
class Ratios(_Base):
    ticker: str
    currency: Optional[str] = None

    # Valuation
    pe: Optional[float] = None
    forward_pe: Optional[float] = None
    pb: Optional[float] = None
    peg: Optional[float] = None
    ev_ebitda: Optional[float] = None
    price_to_sales: Optional[float] = None
    dividend_yield: Optional[float] = None

    # Profitability / returns
    roe: Optional[float] = None
    roa: Optional[float] = None
    roce: Optional[float] = None
    roic: Optional[float] = None
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    net_margin: Optional[float] = None

    # Leverage / liquidity
    debt_to_equity: Optional[float] = None
    interest_coverage: Optional[float] = None
    current_ratio: Optional[float] = None
    quick_ratio: Optional[float] = None

    # Growth
    revenue_growth_yoy: Optional[float] = None
    revenue_cagr_3y: Optional[float] = None
    earnings_growth_yoy: Optional[float] = None
    eps_cagr_3y: Optional[float] = None

    # Cash flow
    fcf: Optional[float] = None
    fcf_margin: Optional[float] = None
    ocf_to_ebitda: Optional[float] = None

    # Other
    beta: Optional[float] = None
    rd_intensity: Optional[float] = None  # R&D / revenue


# --------------------------------------------------------------------------------------
# Peers
# --------------------------------------------------------------------------------------
class PeerRow(_Base):
    ticker: str
    name: Optional[str] = None
    market_cap: Optional[float] = None
    revenue_ttm: Optional[float] = None
    net_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    pe: Optional[float] = None
    pb: Optional[float] = None
    roe: Optional[float] = None
    revenue_growth_yoy: Optional[float] = None
    debt_to_equity: Optional[float] = None
    market_share_proxy: Optional[float] = None  # revenue / sum(revenue) within peer set


class PeerComparison(_Base):
    ticker: str
    sector: Optional[str] = None
    peers: list[PeerRow] = Field(default_factory=list)
    summary: list[str] = Field(default_factory=list)  # grounded observations
    note: Optional[str] = None


# --------------------------------------------------------------------------------------
# Industry intelligence
# --------------------------------------------------------------------------------------
class IndustryIntelligence(_Base):
    ticker: str
    sector: Optional[str] = None
    industry: Optional[str] = None
    sub_domains: list[str] = Field(default_factory=list)
    demand_drivers: list[str] = Field(default_factory=list)
    future_demand: Optional[str] = None
    industry_cagr: Optional[str] = None  # curated string e.g. "~10-12% (FY24-30, est.)"
    risks: list[str] = Field(default_factory=list)
    source: Literal["curated", "keyed", "unknown"] = "curated"
    note: Optional[str] = None


# --------------------------------------------------------------------------------------
# News
# --------------------------------------------------------------------------------------
NewsCategory = Literal["earnings", "m&a", "management", "legal-regulatory", "product-ai", "general"]


class NewsItem(_Base):
    title: str
    publisher: Optional[str] = None
    link: Optional[str] = None
    published: Optional[str] = None  # ISO date string
    category: NewsCategory = "general"


class NewsFeed(_Base):
    ticker: str
    items: list[NewsItem] = Field(default_factory=list)
    note: Optional[str] = None


# --------------------------------------------------------------------------------------
# Management
# --------------------------------------------------------------------------------------
class Management(_Base):
    ticker: str
    key_executives: list[dict[str, Any]] = Field(default_factory=list)
    promoter_holding: Optional[float] = None       # % (best-effort; often unavailable for India)
    insider_holding: Optional[float] = None        # %
    institutional_holding: Optional[float] = None   # %
    roic: Optional[float] = None
    dividend_payout_ratio: Optional[float] = None
    buyback_signal: Optional[bool] = None
    capital_allocation_notes: list[str] = Field(default_factory=list)
    note: Optional[str] = None


# --------------------------------------------------------------------------------------
# DCF
# --------------------------------------------------------------------------------------
class DCFResult(_Base):
    ticker: str
    currency: Optional[str] = None
    base_fcf: Optional[float] = None
    growth_rate: Optional[float] = None
    discount_rate: Optional[float] = None
    terminal_growth: Optional[float] = None
    years: Optional[int] = None
    enterprise_value: Optional[float] = None
    equity_value: Optional[float] = None
    intrinsic_value_per_share: Optional[float] = None
    current_price: Optional[float] = None
    margin_of_safety: Optional[float] = None   # (intrinsic - price) / intrinsic
    expected_return: Optional[float] = None    # (intrinsic - price) / price
    assumptions: list[str] = Field(default_factory=list)
    note: Optional[str] = None


# --------------------------------------------------------------------------------------
# Moat & Risk
# --------------------------------------------------------------------------------------
class MoatSignals(_Base):
    ticker: str
    gross_margin: Optional[float] = None
    margin_stability: Optional[float] = None  # lower stdev => more durable
    roic: Optional[float] = None
    market_share_proxy: Optional[float] = None
    rd_intensity: Optional[float] = None
    scale_rank: Optional[int] = None  # rank within peer set by revenue (1 = largest)
    moat_score: Optional[float] = None  # 0-10 heuristic
    sources: list[str] = Field(default_factory=list)  # candidate moat sources present
    signals: list[str] = Field(default_factory=list)
    note: Optional[str] = None


class RiskSignals(_Base):
    ticker: str
    debt_to_equity: Optional[float] = None
    interest_coverage: Optional[float] = None
    beta: Optional[float] = None
    currency_exposure: Optional[str] = None
    customer_concentration: Optional[str] = None
    regulatory_flags: list[str] = Field(default_factory=list)
    risk_score: Optional[float] = None  # 0-5 heuristic (higher = safer)
    signals: list[str] = Field(default_factory=list)
    note: Optional[str] = None


# --------------------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------------------
class ScoreBucket(_Base):
    name: str
    weight: float           # max points this bucket contributes to the 100
    score: float            # points earned (0..weight)
    normalized: float       # 0..1 (score / weight)
    kind: Literal["computed", "heuristic"] = "computed"
    rationale: Optional[str] = None
    drivers: dict[str, Optional[float]] = Field(default_factory=dict)


class Score(_Base):
    ticker: str
    total: float                 # 0..100
    verdict: str                 # e.g. "Strong" | "Fair" | "Weak"
    buckets: list[ScoreBucket] = Field(default_factory=list)
    esg_included: bool = False
    note: Optional[str] = None


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
    resolved: Optional[TickerCandidate] = None
    profile: Optional[CompanyProfile] = None
    ratios: Optional[Ratios] = None
    peers: Optional[PeerComparison] = None
    industry: Optional[IndustryIntelligence] = None
    news: Optional[NewsFeed] = None
    management: Optional[Management] = None
    dcf: Optional[DCFResult] = None
    moat: Optional[MoatSignals] = None
    risk: Optional[RiskSignals] = None
    score: Optional[Score] = None
    signals: list[Signal] = Field(default_factory=list)
    swot_seeds: list[SwotSeed] = Field(default_factory=list)
    growth_driver_hints: list[str] = Field(default_factory=list)
    llm_guidance: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
