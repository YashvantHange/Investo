"""Evidence-layer tests: the deterministic confidence formula and aggregation (no network)."""

from investo.analysis import evidence as ev
from investo.models import EvidenceMeta, Provenance


def test_source_weight_matches_real_labels():
    assert ev.source_weight(ev.SRC_NSE_FILING) == 0.95
    assert ev.source_weight(ev.SRC_YAHOO) == 0.80
    assert ev.source_weight(ev.SRC_CURATED) == 0.70
    assert ev.source_weight(ev.SRC_HEURISTIC) == 0.50
    assert ev.source_weight("something unknown") == 0.60  # default


def test_tier_thresholds():
    assert ev.tier(0.85) == "High"
    assert ev.tier(0.70) == "Medium"
    assert ev.tier(0.40) == "Low"


def test_confidence_rewards_good_source_coverage_and_history():
    strong = ev.confidence(
        sources=[Provenance(source=ev.SRC_NSE_FILING)], coverage=1.0, history_years=8)
    weak = ev.confidence(sources=[ev.SRC_HEURISTIC], coverage=0.3, history_years=1)
    assert strong.score > weak.score
    assert strong.tier == "High"
    assert weak.tier == "Low"
    assert 0.0 <= weak.score <= 1.0 and 0.0 <= strong.score <= 1.0


def test_cross_source_agreement_bonus():
    one = ev.confidence(sources=[Provenance(source=ev.SRC_STATEMENTS)], coverage=1.0)
    two = ev.confidence(
        sources=[Provenance(source=ev.SRC_STATEMENTS), Provenance(source=ev.SRC_YAHOO)],
        coverage=1.0)
    assert two.score >= one.score


def test_build_meta_computes_coverage_and_latest_date():
    meta = ev.build_meta(
        sources=[Provenance(source=ev.SRC_STATEMENTS, as_of="2025-03-31"),
                 Provenance(source=ev.SRC_YAHOO, as_of="2026-06-30")],
        expected=4, missing_fields=["x"], history_years=4)
    assert meta.data_coverage == 0.75  # (4-1)/4
    assert meta.as_of == "2026-06-30"  # latest wins
    assert meta.source_count == 2
    assert meta.confidence is not None


def test_aggregate_blends_modules():
    a = ev.build_meta(sources=[Provenance(source=ev.SRC_STATEMENTS)], expected=2, present=2)
    b = ev.build_meta(sources=[Provenance(source=ev.SRC_HEURISTIC)], expected=2, present=1)
    agg = ev.aggregate([a, b, None])
    assert agg.confidence is not None
    assert a.confidence and b.confidence
    lo, hi = sorted((a.confidence.score, b.confidence.score))
    assert lo <= agg.confidence.score <= hi
    assert agg.source_count == 2  # de-duplicated union


def test_aggregate_empty_is_safe():
    agg = ev.aggregate([None, EvidenceMeta()])
    assert agg.confidence is not None
