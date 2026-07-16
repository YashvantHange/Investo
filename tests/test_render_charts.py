"""Chart-primitive tests (no network).

Hand-written SVG has no visual test, so these pin what *is* checkable: it parses, it never
crashes on degenerate data, and it can't smuggle a script or a remote asset into the page.
"""

import dataclasses
import xml.etree.ElementTree as ET

import pytest

from investo.render import charts


def _parses(svg: str) -> ET.Element:
    return ET.fromstring(svg)


def test_hbar_renders_and_parses():
    svg = charts.hbar_chart([("Profitability", 0.8, "12.0/15"), ("Growth", 0.4, "4.0/10")],
                            title="Score decomposition")
    root = _parses(svg)
    assert root.tag.endswith("svg")
    assert root.get("role") == "img"
    assert "Profitability" in svg


def test_diverging_bars_put_the_midpoint_at_the_industry_median():
    rows = [("ROE", 1.0, "19.7%", "top"), ("Net margin", 0.0, "9.9%", "bottom")]
    svg = charts.diverging_bars(rows, title="Relative standing")
    _parses(svg)
    assert "industry median" in svg
    assert 'class="vbar pos"' in svg  # the winner grows right
    assert 'class="vbar neg"' in svg  # the loser grows left


def test_scatter_highlights_the_subject_and_labels_every_point():
    svg = charts.scatter(
        [("KPITTECH", 0.10, 0.12, True), ("TATAELXSI", 0.17, 0.05, False),
         ("CYIENT", 0.06, -0.01, False)],
        title="Peers", x_label="Net margin", y_label="Revenue growth")
    _parses(svg)
    assert 'class="vdot subject"' in svg
    assert 'class="vdot peer"' in svg
    # Identity never rests on colour alone.
    for name in ("KPITTECH", "TATAELXSI", "CYIENT"):
        assert name in svg


def test_sparkline_and_value_vs_price_render():
    assert _parses(charts.sparkline([1.0, 2.0, 1.5, 3.0], tip="Revenue")) is not None
    svg = charts.value_vs_price(1200.0, 1000.0, currency_fmt=lambda v: f"Rs {v:,.0f}")
    _parses(svg)
    assert "margin of safety" in svg


def test_value_vs_price_names_a_premium_as_a_premium():
    svg = charts.value_vs_price(800.0, 1000.0, currency_fmt=lambda v: f"Rs {v:,.0f}")
    assert "premium to value" in svg
    assert "-20%" in svg


# --------------------------------------------------------------------------------------
# Degenerate input must not crash a whole report
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize("call", [
    lambda: charts.hbar_chart([], title="t"),
    lambda: charts.diverging_bars([], title="t"),
    lambda: charts.scatter([], title="t", x_label="x", y_label="y"),
    lambda: charts.scatter([("A", None, None, False)], title="t", x_label="x", y_label="y"),
    lambda: charts.sparkline([]),
    lambda: charts.sparkline([None, None]),
    lambda: charts.sparkline([1.0]),
    lambda: charts.value_vs_price(None, 10.0, currency_fmt=str),
    lambda: charts.value_vs_price(10.0, None, currency_fmt=str),
    lambda: charts.value_vs_price(0.0, 0.0, currency_fmt=str),
])
def test_empty_or_degenerate_input_returns_empty_not_an_exception(call):
    assert call() == ""


def test_identical_values_do_not_divide_by_zero():
    # A cohort where every peer reports the same margin must not blow up the axis.
    svg = charts.scatter([("A", 0.1, 0.1, True), ("B", 0.1, 0.1, False)],
                         title="t", x_label="x", y_label="y")
    _parses(svg)
    svg = charts.sparkline([2.0, 2.0, 2.0])
    _parses(svg)


def test_out_of_range_fractions_are_clamped():
    svg = charts.hbar_chart([("A", 5.0, "x"), ("B", -3.0, "y")], title="t")
    _parses(svg)  # no negative widths, no overflow


# --------------------------------------------------------------------------------------
# Self-contained and CSP-safe: the PDF path must have nothing to fetch
# --------------------------------------------------------------------------------------
def _all_charts() -> list[str]:
    return [
        charts.hbar_chart([("A", 0.5, "1")], title="t"),
        charts.diverging_bars([("A", 0.5, "1", "tip")], title="t"),
        charts.scatter([("A", 0.1, 0.2, True), ("B", 0.3, 0.4, False)],
                       title="t", x_label="x", y_label="y"),
        charts.sparkline([1.0, 2.0]),
        charts.value_vs_price(2.0, 1.0, currency_fmt=str),
    ]


@pytest.mark.parametrize("svg", _all_charts())
def test_charts_carry_no_script_or_remote_asset(svg):
    # The SVG namespace is a URI, not a fetch — strip it before looking for real remote refs.
    low = svg.lower().replace('xmlns="http://www.w3.org/2000/svg"', "")
    assert "<script" not in low
    assert "onload=" not in low and "onclick=" not in low
    assert "href" not in low
    assert "http://" not in low and "https://" not in low


@pytest.mark.parametrize("svg", _all_charts())
def test_charts_are_responsive_not_fixed_pixel(svg):
    assert "viewBox" in svg


def test_chart_text_is_escaped():
    svg = charts.hbar_chart([("<script>alert(1)</script>", 0.5, "&<>")], title="t")
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg
    _parses(svg)


def test_chart_dataclass_carries_its_provenance():
    c = charts.Chart(title="t", svg="<svg/>", caption="cap", source="Source: Yahoo")
    assert c.source and c.caption
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.title = "mutated"  # frozen: an exhibit's provenance can't drift from its figure
