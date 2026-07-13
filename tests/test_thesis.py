"""Investment-thesis + AI-signals tests (no network)."""

from investo.analysis.thesis import build_ai_signals, build_thesis
from investo.models import (
    BuffettChecklist,
    Ratios,
    RedFlag,
    RedFlagReport,
    Score,
    ScoreBucket,
)


def _score(total: float) -> Score:
    return Score(ticker="X", total=total, verdict="x", buckets=[
        ScoreBucket(name="Profitability", weight=15, score=13, normalized=0.87, rationale="ROE 25%"),
        ScoreBucket(name="Valuation", weight=15, score=3, normalized=0.20, rationale="P/E 40"),
    ])


def test_quality_grade_tracks_score():
    assert build_thesis("X", score=_score(85), ratios=Ratios(ticker="X")).quality == "Excellent"
    assert build_thesis("X", score=_score(38), ratios=Ratios(ticker="X")).quality == "Weak"


def test_valuation_stance_expensive_vs_cheap():
    exp = build_thesis("X", ratios=Ratios(ticker="X", pe=40, pb=8, peg=3))
    cheap = build_thesis("X", ratios=Ratios(ticker="X", pe=8, pb=1.0, peg=0.5))
    assert exp.valuation_stance == "expensive"
    assert cheap.valuation_stance == "cheap"


def test_pros_and_cons_drawn_from_modules():
    th = build_thesis("X", score=_score(60), ratios=Ratios(ticker="X"))
    assert any("Profitability" in p for p in th.pros)  # strong bucket -> pro
    assert any("Valuation" in c for c in th.cons)      # weak bucket -> con


def test_red_flags_feed_cons_and_signals():
    rf = RedFlagReport(ticker="X", flags=[RedFlag(issue="Debt rising", severity="high")],
                       risk_level="high")
    th = build_thesis("X", ratios=Ratios(ticker="X"), red_flags=rf)
    assert any("Debt rising" in c for c in th.cons)
    sig = build_ai_signals("X", thesis=th, red_flags=rf)
    assert sig.risk_level == "high"
    assert "Debt rising" in sig.red_flags
    assert sig.investment_thesis == th.verdict


def test_verdict_combines_quality_and_stance():
    th = build_thesis("X", score=_score(85), ratios=Ratios(ticker="X", pe=40, pb=8, peg=3))
    assert th.verdict == "Excellent Quality, Richly Valued"


def test_confidence_present():
    th = build_thesis("X", score=_score(60), ratios=Ratios(ticker="X"),
                      buffett=BuffettChecklist(ticker="X"))
    assert th.confidence is not None and 0.0 <= th.confidence.score <= 1.0
