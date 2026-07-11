"""Report signal / SWOT / growth-hint assembly tests (no network)."""

from investo.analysis.report import _build_growth_hints, _build_signals, _build_swot
from investo.models import (
    IndustryIntelligence,
    NewsFeed,
    NewsItem,
    Ratios,
    RiskSignals,
    Score,
    ScoreBucket,
)


def _score() -> Score:
    return Score(
        ticker="X", total=70.0, verdict="Strong",
        buckets=[
            ScoreBucket(name="Profitability", weight=15, score=13, normalized=0.87, kind="computed",
                        rationale="ROE 30%"),
            ScoreBucket(name="Growth", weight=15, score=3, normalized=0.20, kind="computed",
                        rationale="revenue flat"),
            ScoreBucket(name="Valuation", weight=15, score=8, normalized=0.53, kind="computed",
                        rationale="P/E 20"),
        ],
    )


def test_signals_split_by_bucket_score():
    signals = _build_signals(_score())
    pos = [s for s in signals if s.polarity == "positive"]
    neg = [s for s in signals if s.polarity == "negative"]
    assert any(s.category == "Profitability" for s in pos)   # normalized 0.87 >= 0.66
    assert any(s.category == "Growth" for s in neg)          # normalized 0.20 <= 0.34
    # Valuation at 0.53 is neither strongly positive nor negative.
    assert all(s.category != "Valuation" for s in signals)


def test_swot_maps_signals_and_industry():
    signals = _build_signals(_score())
    industry = IndustryIntelligence(ticker="X", demand_drivers=["Cloud", "AI"], risks=["Cyclical"])
    risk = RiskSignals(ticker="X", regulatory_flags=["RBI"])
    swot = _build_swot(signals, industry, risk)
    buckets = {s.bucket for s in swot}
    assert "strength" in buckets and "weakness" in buckets
    assert any(s.bucket == "opportunity" and s.text == "Cloud" for s in swot)
    assert any(s.bucket == "threat" for s in swot)


def test_growth_hints_from_news_and_industry():
    ratios = Ratios(ticker="X", revenue_cagr_3y=0.18, rd_intensity=0.05)
    industry = IndustryIntelligence(ticker="X", demand_drivers=["Digitization"])
    news = NewsFeed(ticker="X", items=[NewsItem(title="new AI product", category="product-ai")])
    hints = _build_growth_hints(ratios, industry, news)
    joined = " ".join(hints)
    assert "product" in joined.lower()
    assert "18" in joined            # revenue CAGR mentioned
    assert "Digitization" in hints
