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


# --------------------------------------------------------------------------------------
# Zero coverage means zero. The 0.4 coverage floor exists so a couple of gaps don't collapse
# a score; applying it to a module that computed *nothing* manufactured a plausible 0.37 out
# of no data at all.
# --------------------------------------------------------------------------------------
def test_zero_coverage_earns_no_confidence():
    c = ev.confidence(sources=[Provenance(source=ev.SRC_YAHOO)], coverage=0.0)
    assert c.score == 0.0  # was 0.4 * 0.80 = 0.32
    assert c.tier == "Low"


def test_zero_coverage_gets_no_corroboration_bonus():
    # Two sources cannot agree on a figure that was never computed.
    c = ev.confidence(
        sources=[Provenance(source=ev.SRC_YAHOO), Provenance(source=ev.SRC_CURATED)],
        coverage=0.0)
    assert c.score == 0.0  # was 0.32 + 0.05 = 0.37
    assert "cross-source agreement" not in (c.reason or "")


def test_partial_coverage_still_gets_the_softening_floor():
    # The floor must survive for real-but-incomplete data; only zero is special.
    c = ev.confidence(sources=[Provenance(source=ev.SRC_YAHOO)], coverage=0.1)
    assert c.score > 0.3


def test_missing_coverage_is_still_neutral():
    # None means "not applicable", not "nothing found" — point-in-time modules must not be hit.
    assert ev.confidence(sources=[Provenance(source=ev.SRC_YAHOO)], coverage=None).score == 0.80


def test_reliability_factor_discounts_the_score():
    full = ev.confidence(sources=[Provenance(source=ev.SRC_YAHOO)], coverage=1.0)
    half = ev.confidence(sources=[Provenance(source=ev.SRC_YAHOO)], coverage=1.0,
                         reliability_factor=0.5)
    assert half.score == round(full.score * 0.5, 3)


def test_reliability_factor_defaults_to_no_discount():
    a = ev.confidence(sources=[Provenance(source=ev.SRC_YAHOO)], coverage=1.0)
    b = ev.confidence(sources=[Provenance(source=ev.SRC_YAHOO)], coverage=1.0,
                      reliability_factor=None)
    assert a.score == b.score


def test_build_meta_passes_reliability_through():
    meta = ev.build_meta(sources=[Provenance(source=ev.SRC_YAHOO)], present=2, expected=2,
                         reliability_factor=0.5)
    assert meta.confidence.score < 0.5


# --------------------------------------------------------------------------------------
# Aggregation weights by coverage, so an empty module neither drags the report down nor
# props it up.
# --------------------------------------------------------------------------------------
def test_aggregate_ignores_a_module_that_found_nothing():
    real = ev.build_meta(sources=[Provenance(source=ev.SRC_STATEMENTS)], present=2, expected=2)
    empty = ev.build_meta(sources=[Provenance(source=ev.SRC_YAHOO)], present=0, expected=7)
    agg = ev.aggregate([real, empty])
    assert agg.confidence.score == real.confidence.score  # the empty module carried no weight


def test_aggregate_says_when_modules_came_back_empty():
    real = ev.build_meta(sources=[Provenance(source=ev.SRC_STATEMENTS)], present=2, expected=2)
    empty = ev.build_meta(sources=[Provenance(source=ev.SRC_YAHOO)], present=0, expected=7)
    agg = ev.aggregate([real, empty])
    # A report built on one of two modules must not read like a report built on two.
    assert any("found no data" in n for n in agg.notes)


def test_aggregate_of_only_empty_modules_is_zero_not_a_default():
    empty = ev.build_meta(sources=[Provenance(source=ev.SRC_YAHOO)], present=0, expected=7)
    agg = ev.aggregate([empty, empty])
    assert agg.confidence.score == 0.0


def test_aggregate_weights_point_in_time_modules_fully():
    # coverage=None modules have no coverage to weight by; they must not be dropped.
    pit = ev.build_meta(sources=[Provenance(source=ev.SRC_YAHOO)])
    agg = ev.aggregate([pit])
    assert agg.confidence.score == pit.confidence.score
