"""Publication-renderer tests (no network).

The old renderer shipped 462 lines with no tests at all. These cover what matters for a document
that gets exported and shared: it renders from a partial report without raising, it escapes
untrusted company data, it stays self-contained so the PDF path has nothing to fetch, and it
doesn't look machine-generated.
"""

import xml.etree.ElementTree as ET
from html import escape

from investo.models import (
    AnalysisReport,
    CompanyProfile,
    Confidence,
    DCFResult,
    EvidenceMeta,
    FundamentalTrend,
    IndustryIntelligence,
    InvestmentThesis,
    MetricTrend,
    PeerComparison,
    PeerRow,
    Ratios,
    RelativeComparison,
    RelativeMetric,
    Score,
    ScoreBucket,
    TickerCandidate,
)
from investo.render import render_html
from investo.render.sections import SECTIONS


def _report() -> AnalysisReport:
    """A fat report exercising every section, in the shape of the reported KPIT case."""
    return AnalysisReport(
        query="KPIT Technologies",
        resolved=TickerCandidate(symbol="KPITTECH.NS", name="KPIT Technologies Limited",
                                 exchange="NSE"),
        profile=CompanyProfile(
            ticker="KPITTECH.NS", name="KPIT Technologies Limited", sector="Technology",
            industry="Software - Infrastructure", exchange="NSE", currency="INR",
            current_price=1234.5, market_cap=3.4e11,
            fifty_two_week_low=980.0, fifty_two_week_high=1890.0,
        ),
        ratios=Ratios(ticker="KPITTECH.NS", pe=23.7, pb=4.2, ev_ebitda=10.8,
                      price_to_sales=2.3, roe=0.197, net_margin=0.099,
                      operating_margin=0.159, debt_to_equity=0.2),
        thesis=InvestmentThesis(
            ticker="KPITTECH.NS", verdict="Quality compounder, de-rated",
            summary="Cheapest in its ER&D cohort on every multiple while growing fastest.",
            pros=["Fastest revenue growth in its peer set", "Lowest EV/EBITDA in the cohort"],
            cons=["Client concentration among a few OEMs", "Net margin below the peer median"],
            quality="Good", valuation_stance="cheap",
            confidence=Confidence(score=0.68, tier="Medium", reason="test"),
        ),
        score=Score(ticker="KPITTECH.NS", total=68.4, verdict="Strong", buckets=[
            ScoreBucket(name="Profitability", weight=15, score=12.0, normalized=0.8,
                        rationale="ROE 19.7% beats the peer median"),
            ScoreBucket(name="Growth", weight=10, score=8.0, normalized=0.8,
                        rationale="12% revenue growth"),
        ]),
        relative=RelativeComparison(
            ticker="KPITTECH.NS", peer_count=5, basis="curated",
            peer_group_label="Automotive ER&D",
            metrics=[
                RelativeMetric(name="ROE", company=0.197, industry=0.171, percentile=1.0,
                               better=True, delta=0.026, unit="percent"),
                RelativeMetric(name="EV/EBITDA", company=10.8, industry=22.4, percentile=1.0,
                               better=True, delta=-11.6, higher_is_better=False, unit="ratio"),
                RelativeMetric(name="Net margin", company=0.099, industry=0.108, percentile=0.25,
                               better=False, delta=-0.009, unit="percent"),
            ],
            evidence=EvidenceMeta(confidence=Confidence(score=0.77, tier="Medium", reason="t"),
                                  data_coverage=1.0, source_count=2),
        ),
        peers=PeerComparison(
            ticker="KPITTECH.NS", basis="curated", peer_group_key="auto_erd",
            peer_group_label="Automotive ER&D",
            summary=["#3 of 5 by market cap in its peer set."],
            peers=[
                PeerRow(ticker="KPITTECH.NS", name="KPIT Technologies", market_cap=3.4e11,
                        net_margin=0.099, revenue_growth_yoy=0.12, pe=23.7, ev_ebitda=10.8),
                PeerRow(ticker="TATAELXSI.NS", name="Tata Elxsi", market_cap=3.6e11,
                        net_margin=0.166, revenue_growth_yoy=0.02, pe=33.5, ev_ebitda=26.3),
                PeerRow(ticker="CYIENT.NS", name="Cyient", market_cap=1.4e11,
                        net_margin=0.059, revenue_growth_yoy=-0.01, pe=21.8, ev_ebitda=10.7),
            ],
        ),
        industry=IndustryIntelligence(
            ticker="KPITTECH.NS", sector="Technology", industry="Software - Infrastructure",
            peer_group="Automotive ER&D", basis="curated", as_of="2026-07",
            sub_domains=["Software-defined vehicles (SDV)", "ADAS & autonomous driving"],
            demand_drivers=["OEM transition to software-defined vehicles"],
            future_demand="Structural rather than cyclical.",
            industry_cagr="~12-15% (SDV, EV & ADAS engineering spend; est.)",
            risks=["OEM R&D budget cuts"],
        ),
        dcf=DCFResult(ticker="KPITTECH.NS", currency="INR", intrinsic_value_per_share=1500.0,
                      current_price=1234.5, margin_of_safety=0.215,
                      note="Statements reported in INR."),
        fundamental_trend=FundamentalTrend(
            ticker="KPITTECH.NS", overall_health="Good",
            metrics=[MetricTrend(name="Revenue", periods=["FY26", "FY25", "FY24"],
                                 values=[100.0, 88.0, 70.0], directions=["up", "up"],
                                 health="Excellent", cagr=0.19)],
        ),
        evidence=EvidenceMeta(confidence=Confidence(score=0.72, tier="Medium", reason="blended"),
                              data_coverage=0.86, source_count=4, as_of="2026-07-15",
                              missing_fields=["promoter_pledge"]),
        warnings=["Promoter holding unavailable for NSE via Yahoo."],
    )


# --------------------------------------------------------------------------------------
# Document shape
# --------------------------------------------------------------------------------------
def test_renders_a_full_standalone_document():
    html = render_html(_report())
    assert html.startswith("<!doctype html>")
    assert "<title>KPIT Technologies Limited — Investo equity research</title>" in html
    assert html.rstrip().endswith("</html>")


def test_fragment_mode_omits_the_document_shell():
    frag = render_html(_report(), standalone=False)
    assert frag.startswith("<style>")
    assert "<html" not in frag and "<!doctype" not in frag


def test_a_bare_report_still_renders():
    # analyze() degrades gracefully; the renderer must too, or an unresolvable ticker 500s.
    html = render_html(AnalysisReport(query="nonexistent"))
    assert html.startswith("<!doctype html>")
    assert "nonexistent" in html


def test_sections_without_evidence_are_omitted_not_padded():
    html = render_html(AnalysisReport(query="x"))
    # No thesis/score/etc. in a bare report -> no empty headings.
    for title in ("Investment thesis", "Rating", "Buffett checklist"):
        assert title not in html


def test_every_populated_section_appears_with_its_number():
    html = render_html(_report())
    for key in ("thesis", "score", "relative", "peers", "industry", "dcf",
                "fundamental_trend", "evidence", "warnings"):
        section = next(s for s in SECTIONS if s.key == key)
        assert escape(section.title) in html, f"{key} section missing"
        assert f'id="s{section.number}"' in html


def test_print_furniture_is_present():
    html = render_html(_report())
    assert "@page" in html
    assert "size:A4" in html
    assert "break-inside:avoid" in html
    assert "@media print" in html


def test_print_forces_light_so_a_dark_host_does_not_emit_a_black_page():
    html = render_html(_report())
    printed = html.split("@media print")[1]
    assert "color-scheme:light !important" in printed


# --------------------------------------------------------------------------------------
# It must not look machine-generated
# --------------------------------------------------------------------------------------
# ▲/▼ are the single deliberate exception: they encode direction inside a data table's trend
# column, where a glyph is the compact form. Everywhere else — and especially inside prose —
# a tick mark is the visual signature of a generated artifact.
_BANNED = "✓⚠✗➡⬆⬇→🚀📈📉💡🔴🟢⭐❌✅✔✖"


def test_no_dingbats_anywhere_in_the_document():
    html = render_html(_report())
    for ch in _BANNED:
        assert ch not in html, f"{ch!r} leaked into the document"


def test_no_dingbats_survive_from_upstream_prose():
    # The analysis layer used to bake ✓/✗/→ into its own strings, so the renderer printed them
    # faithfully however clean its own markup was. Presentation belongs to the renderer.
    r = _report()
    r.thesis.pros = ["Buffett ✓ Durable moat"]
    r.thesis.cons = ["Buffett ✗ Debt (D/E 0.9 vs < 0.5 → FAIL)"]
    html = render_html(r)
    for ch in "✓✗→":
        assert ch not in html, f"{ch!r} passed straight through the renderer"


def test_status_is_typographic_not_a_coloured_pill():
    html = render_html(_report())
    assert 'class="pill' not in html
    assert "border-radius:99px" not in html


def test_uses_a_serif_text_face_and_numbered_sections():
    html = render_html(_report())
    assert "--serif:" in html
    assert 'class="n">1</span>' in html  # sections are numbered like a research note


# --------------------------------------------------------------------------------------
# Exhibits carry their provenance
# --------------------------------------------------------------------------------------
def test_exhibits_are_captioned_and_sourced():
    html = render_html(_report())
    assert "Exhibit 1" in html
    assert "Exhibit 2" in html
    assert 'class="src"' in html
    assert "Source: Yahoo Finance fundamentals" in html


def test_relative_exhibit_states_the_peer_basis_and_that_it_is_rank_within_set():
    html = render_html(_report())
    assert "Automotive ER&amp;D" in html
    assert "4 peers" in html
    assert "rank within the set, not the market" in html


def test_a_guessed_peer_group_says_so_on_the_exhibit():
    r = _report()
    r.relative.basis = "sector-fallback"
    html = render_html(r)
    assert "inferred from the company&#x27;s industry label, not curated" in html \
        or "inferred from the company's industry label, not curated" in html


def test_curated_estimates_are_never_presented_as_third_party_forecasts():
    html = render_html(_report())
    assert "Investo estimate, as of 2026-07" in html
    assert "not third-party forecasts" in html


def test_industry_reframing_is_stated_rather_than_hidden():
    html = render_html(_report())
    assert "Automotive ER&amp;D" in html
    assert "Software - Infrastructure" in html  # Yahoo's label is shown, not silently replaced


def test_footnotes_and_disclaimer_are_present():
    html = render_html(_report())
    assert 'class="footnotes"' in html
    assert "not a market-wide" in html
    assert "not investment advice" in html


# --------------------------------------------------------------------------------------
# Safety: company names are untrusted, and the PDF path must fetch nothing
# --------------------------------------------------------------------------------------
def test_untrusted_company_data_is_escaped():
    r = _report()
    r.profile.name = "<script>alert(1)</script>"
    r.thesis.pros = ["<img src=x onerror=alert(1)>"]
    html = render_html(r)
    assert "<script>alert(1)</script>" not in html
    assert "<img src=x" not in html
    assert "&lt;script&gt;" in html


def test_document_is_self_contained():
    html = render_html(_report())
    assert "<script" not in html.lower()
    # Only the SVG namespace may reference a remote URL.
    assert html.count("http") == html.count('xmlns="http://www.w3.org/2000/svg"')


def test_every_embedded_svg_parses():
    html = render_html(_report())
    svgs = []
    rest = html
    while "<svg" in rest:
        start = rest.index("<svg")
        end = rest.index("</svg>", start) + len("</svg>")
        svgs.append(rest[start:end])
        rest = rest[end:]
    assert svgs, "the note should carry exhibits"
    for svg in svgs:
        ET.fromstring(svg)
