"""The section registry — one ordered source of truth for what a report contains.

Investo had three hand-maintained section lists that had to agree: ``report._LLM_GUIDANCE``,
``cli.render_report`` and the old ``report_html._body``. They drifted (the HTML renderer silently
dropped valuation, peers, industry, moat, SWOT and news). This registry is the list; the HTML
document and the LLM guidance are both **generated** from it, so those two can no longer disagree.

The registry is deliberately **pure data and output-agnostic** — no renderer functions live here.
Each backend owns its own ``{key: renderer}`` dispatch table (see ``html.HTML_RENDERERS``), which
is what lets a future Markdown or DOCX backend reuse the ordering and titles without inheriting
HTML's assumptions.

``cli.render_report`` stays hand-rolled: ANSI codes and fixed-width columns are genuinely
different constraints, and forcing it through this registry would be churn for no gain. The
``key`` is asserted against ``AnalysisReport``'s real fields by ``tests/test_sections.py`` so the
registry cannot rot away from the model.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Section:
    """One numbered section of the research note."""

    key: str        # must name a real AnalysisReport field
    number: int
    title: str
    llm_hint: str   # how the host LLM should narrate this section


SECTIONS: tuple[Section, ...] = (
    Section(
        key="thesis", number=1, title="Investment thesis",
        llm_hint="lead with `thesis`: the one-line `verdict`, the `summary`, then a Pros vs Cons "
                 "table from `thesis.pros`/`thesis.cons`. State `thesis.quality` and "
                 "`thesis.valuation_stance`.",
    ),
    Section(
        key="score", number=2, title="Rating",
        llm_hint="`score.total`/100 (`score.verdict`) with the bucket table; explain the main "
                 "drivers rather than restating every row.",
    ),
    Section(
        key="relative", number=3, title="Relative to industry",
        llm_hint="a table of company vs industry (peer-set median) with the percentile band per "
                 "metric. State `relative.basis` and the peer-set size — a `sector-fallback` "
                 "cohort is a guess and must be described as one, and percentiles are a rank "
                 "within the set, not the market.",
    ),
    Section(
        key="peers", number=4, title="Peer group",
        llm_hint="the competitor table from `peers`, naming `peers.peer_group_label`. Say who is "
                 "bigger, who earns more, who is cheaper.",
    ),
    Section(
        key="industry", number=5, title="Industry & competitive position",
        llm_hint="sub-domains, demand drivers and industry CAGR from `industry`. Note that CAGR "
                 "is an Investo curated estimate with an `as_of` date, not a third-party "
                 "forecast, and that `industry.peer_group` may deliberately reframe Yahoo's "
                 "broader `industry` label.",
    ),
    Section(
        key="dcf", number=6, title="Valuation",
        llm_hint="the DCF intrinsic value and margin of safety from `dcf`, cross-checked against "
                 "P/E, P/B and EV/EBITDA in `ratios`. Respect any low-confidence or "
                 "currency-mismatch note rather than presenting the number as precise.",
    ),
    Section(
        key="growth_outlook", number=7, title="Growth engine — next five years",
        llm_hint="the `primary_engine`, a ranked table of `drivers` (name, contribution %, key "
                 "risks), the `catalysts` timeline, and the blended 5y band with "
                 "`growth_signal`.",
    ),
    Section(
        key="fundamental_trend", number=8, title="Fundamentals trend",
        llm_hint="a compact table per metric with the direction sequence, `health` grade and "
                 "CAGR, then the `overall_health`.",
    ),
    Section(
        key="buffett", number=9, title="Buffett checklist",
        llm_hint="the weighted `weighted_score`/100 and `verdict`, then each criterion with its "
                 "status, the `reason`, its `confidence.tier` and any `trend_verdict`. An "
                 "`unknown` criterion means no data, not a failure.",
    ),
    Section(
        key="shareholding", number=10, title="Shareholding",
        llm_hint="the latest promoter/FII/DII/public split and pledge, the quarter-over-quarter "
                 "`observations` and the `ownership_signal`. Name the source — an exchange "
                 "filing and a Yahoo snapshot are not equivalent.",
    ),
    Section(
        key="moat", number=11, title="Competitive moat",
        llm_hint="the moat signals and the 0-10 heuristic score from `moat`, with what actually "
                 "protects (or fails to protect) the economics.",
    ),
    Section(
        key="risk", number=12, title="Risk assessment",
        llm_hint="leverage, currency, concentration and regulatory exposure from `risk`.",
    ),
    Section(
        key="red_flags", number=13, title="Red flags",
        llm_hint="the `risk_level` and every flag with its severity. Say so explicitly when there "
                 "are none — silence reads as an oversight.",
    ),
    Section(
        key="swot_seeds", number=14, title="SWOT",
        llm_hint="build the SWOT from `swot_seeds`, grouped strength/weakness/opportunity/threat.",
    ),
    Section(
        key="news", number=15, title="Recent developments",
        llm_hint="the material items from `news`, categorised, with dates. Skip the noise.",
    ),
    Section(
        key="warnings", number=16, title="Notes & caveats",
        llm_hint="surface every `warnings` entry (currency mismatch, low-confidence DCF, missing "
                 "promoter data) in the reader's language.",
    ),
    Section(
        key="evidence", number=17, title="Evidence & data quality",
        llm_hint="overall confidence (score + tier), data coverage, source count, the latest data "
                 "date and any `missing_fields`. This is what lets a reader discount the rest.",
    ),
)

SECTIONS_BY_KEY: dict[str, Section] = {s.key: s for s in SECTIONS}


def build_guidance() -> str:
    """Generate the host-LLM instructions from the registry.

    Generated rather than hand-written so the narrative the LLM produces and the document the
    renderer produces can never describe different reports.
    """
    lines = [
        "You are Investo. Produce a PROFESSIONAL, ANALYST-GRADE report in clean, well-formatted "
        "Markdown using ONLY the structured evidence here — never invent numbers. Use headed "
        "sections and tables; keep it scannable. Open with a header: name, ticker, price, market "
        "cap, 52-week range. Then:",
    ]
    lines += [f"{s.number}. {s.title.upper()} (`{s.key}`): {s.llm_hint}" for s in SECTIONS]
    lines.append(
        "Omit any section whose evidence is absent rather than padding it. Surface confidence and "
        "provenance wherever the evidence provides them so the reader can judge reliability — a "
        "low-confidence figure presented as fact is worse than no figure. Close with one line: "
        "research/education only, not investment advice."
    )
    return "\n".join(lines)
