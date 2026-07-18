"""Command-line interface for Investo.

    investo analyze "Tata Motors"     # full report
    investo analyze INFY.NS --json    # raw JSON
    investo search "hdfc bank"
    investo score RELIANCE.NS
    investo peers TCS.NS

Handy for local testing without an MCP client.
"""

from __future__ import annotations

import argparse
import json
import sys

from .models import AnalysisReport, CompanyProfile

# Distinguishes "flag absent" from "flag given with no value" for --html/--pdf (see build_parser).
_UNSET = object()


# --------------------------------------------------------------------------------------
# Formatting helpers
# --------------------------------------------------------------------------------------
def _money(value: float | None, currency: str | None) -> str:
    if value is None:
        return "n/a"
    cur = (currency or "").upper()
    if cur == "INR":
        return f"₹{value / 1e7:,.0f} Cr"
    if abs(value) >= 1e9:
        return f"{value / 1e9:,.1f}B {cur}".strip()
    return f"{value:,.0f} {cur}".strip()


def _pct(value: float | None) -> str:
    return f"{value:.1%}" if value is not None else "n/a"


def _num(value: float | None, fmt: str = ".2f") -> str:
    return format(value, fmt) if value is not None else "n/a"


def _rule(title: str) -> str:
    return f"\n\033[1m{title}\033[0m\n" + "-" * max(len(title), 40)


def _dim(text: str) -> str:
    return f"\033[2m{text}\033[0m"


def _bar(normalized: float, width: int = 10) -> str:
    filled = int(round(normalized * width))
    return "█" * filled + "·" * (width - filled)


_STATUS_GLYPH = {"pass": "✓", "warn": "⚠", "fail": "✗", "unknown": "—"}
_ARROW = {"up": "⬆", "flat": "➡", "down": "⬇"}


def _conf(confidence) -> str:
    """Render a Confidence as e.g. '92% High'."""
    if confidence is None:
        return "n/a"
    return f"{confidence.score:.0%} {confidence.tier}"


def _metric(unit: str, value: float | None) -> str:
    """Format a relative-comparison value from its declared unit.

    The unit travels on the metric rather than being inferred from its name — guessing by name
    silently renders any unrecognised ratio (EV/EBITDA, P/S) as a percentage.
    """
    if value is None:
        return "n/a"
    return f"{value:.1f}x" if unit == "ratio" else f"{value:.1%}"


# --------------------------------------------------------------------------------------
# Report renderer
# --------------------------------------------------------------------------------------
def render_report(r: AnalysisReport) -> str:
    out: list[str] = []
    if r.resolved is None:
        out.append(f"Could not resolve '{r.query}'.")
        for w in r.warnings:
            out.append(f"  ! {w}")
        return "\n".join(out)

    p = r.profile or CompanyProfile(ticker=r.resolved.symbol)
    out.append(f"\n\033[1m{p.name or r.resolved.symbol}\033[0m  ({r.resolved.symbol})")
    out.append(f"{p.sector or 'n/a'} / {p.industry or 'n/a'}  ·  {p.exchange or ''}  ·  {p.country or ''}")
    if p.market_cap:
        out.append(f"Market cap {_money(p.market_cap, p.currency)}  ·  Price {_num(p.current_price)} {p.currency or ''}")
    if p.business_summary:
        summary = p.business_summary
        out.append("\n" + (summary[:400] + ("…" if len(summary) > 400 else "")))

    # Investment thesis (lead with the synthesis)
    th = r.thesis
    if th:
        title = f"INVESTMENT THESIS — {th.verdict}" if th.verdict else "INVESTMENT THESIS"
        out.append(_rule(title))
        if th.summary:
            out.append(f"  {th.summary}")
        if th.confidence:
            out.append(f"  Confidence: {_conf(th.confidence)}")
        if th.pros:
            out.append("  \033[1mPros\033[0m")
            for pro in th.pros:
                out.append(f"    + {pro}")
        if th.cons:
            out.append("  \033[1mCons\033[0m")
            for con in th.cons:
                out.append(f"    − {con}")

    # Rating
    s = r.score
    if s:
        out.append(_rule(f"RATING: {s.total}/100  —  {s.verdict}"))
        for b in s.buckets:
            out.append(f"  {b.name:18} {_bar(b.normalized)} {b.score:5.1f}/{b.weight:<4.0f} {b.rationale}")

    # Relative to industry
    rel = r.relative
    if rel and rel.metrics:
        title = "RELATIVE TO INDUSTRY"
        if rel.peer_group_label:
            title += f" — {rel.peer_group_label.upper()}"
        out.append(_rule(title))
        out.append(f"  {'Metric':18}{'Company':>10}{'Industry':>10}   Standing")
        for m in rel.metrics:
            band = "top quartile" if (m.percentile or 0) >= 0.75 else \
                   "above median" if (m.percentile or 0) >= 0.5 else \
                   "below median" if (m.percentile or 0) >= 0.25 else "bottom quartile"
            out.append(f"  {m.name:18}{_metric(m.unit, m.company):>10}"
                       f"{_metric(m.unit, m.industry):>10}   {band}")
        # Say how the peer set was found — a guessed cohort must not read like a curated one.
        out.append(f"  {_dim(f'{rel.peer_count - 1} peers, basis: {rel.basis}')}")
    elif rel and rel.note:
        out.append(_rule("RELATIVE TO INDUSTRY"))
        out.append(f"  {_dim(rel.note)}")

    # Buffett checklist
    bf = r.buffett
    if bf and bf.criteria:
        head = f"BUFFETT CHECKLIST: {bf.weighted_score}/100"
        if bf.verdict:
            head += f"  —  {bf.verdict}"
        out.append(_rule(head))
        for crit in bf.criteria:
            glyph = _STATUS_GLYPH.get(crit.status, "—")
            trend = f"  [{crit.trend_verdict}]" if crit.trend_verdict else ""
            out.append(f"  {glyph} {crit.name:26} {_conf(crit.confidence):>9}  {crit.reason}{trend}")

    # Shareholding pattern
    sh = r.shareholding
    if sh and sh.latest:
        sig = f"  —  ownership: {sh.ownership_signal}" if sh.ownership_signal else ""
        out.append(_rule(f"SHAREHOLDING ({sh.source}){sig}"))
        lt = sh.latest
        split = [(lbl, val) for lbl, val in (
            ("Promoter", lt.promoter), ("FII", lt.fii), ("DII", lt.dii),
            ("Institutional", lt.institutional), ("Public", lt.public),
            ("Pledge", lt.promoter_pledge)) if val is not None]
        if split:
            out.append("  " + "   ".join(f"{lbl} {val:.1%}" for lbl, val in split))
        for o in sh.observations:
            out.append(f"    • {o}")
        if sh.note:
            out.append(f"    ({sh.note})")

    # Growth engine (next 5 years)
    g = r.growth_outlook
    if g and g.drivers:
        band = ""
        if g.blended_5y_low is not None and g.blended_5y_high is not None:
            band = f"  ({g.blended_5y_low:.0%}–{g.blended_5y_high:.0%} blended)"
        out.append(_rule(f"GROWTH ENGINE — 5Y: {g.growth_signal or 'n/a'}{band}"))
        if g.primary_engine:
            out.append(f"  Primary: {g.primary_engine}")
        for drv in g.drivers:
            share = f"{drv.contribution_pct:.0%}" if drv.contribution_pct is not None else " — "
            risks = f"  risks: {', '.join(drv.risks[:2])}" if drv.risks else ""
            out.append(f"    {drv.rank}. {drv.name:24} {share:>5}{risks}")
        if g.catalysts:
            cats = "  ".join(f"{c.year}: {c.event}" for c in g.catalysts if c.event)
            out.append(f"  Catalysts: {cats}")

    # Fundamentals trend (health at a glance)
    ft = r.fundamental_trend
    if ft and ft.metrics:
        out.append(_rule(f"FUNDAMENTALS TREND — overall: {ft.overall_health or 'n/a'}"))
        for mt in ft.metrics:
            arrows = "".join(_ARROW.get(step, "·") for step in mt.directions)
            cagr = f"{mt.cagr:+.1%}" if mt.cagr is not None else "n/a"
            out.append(f"  {mt.name:12} {arrows:6} {mt.health or '':10} CAGR {cagr}")

    # Red flags
    rf = r.red_flags
    if rf:
        out.append(_rule(f"RED FLAGS — risk level: {rf.risk_level}"))
        if not rf.flags:
            out.append("  ✓ No material red flags detected.")
        for flag in rf.flags:
            out.append(f"  ⚠ [{flag.severity:8}] {flag.issue} — {flag.detail}")

    # Valuation / DCF
    d = r.dcf
    ra = r.ratios
    if ra:
        out.append(_rule("VALUATION & RATIOS"))
        out.append(f"  P/E {_num(ra.pe, '.1f')}  P/B {_num(ra.pb, '.1f')}  EV/EBITDA {_num(ra.ev_ebitda, '.1f')}  "
                   f"Div yield {_pct(ra.dividend_yield)}")
        out.append(f"  ROE {_pct(ra.roe)}  ROCE {_pct(ra.roce)}  ROIC {_pct(ra.roic)}  Net margin {_pct(ra.net_margin)}")
        out.append(f"  D/E {_num(ra.debt_to_equity)}  Int.cov {_num(ra.interest_coverage, '.1f')}x  "
                   f"Rev YoY {_pct(ra.revenue_growth_yoy)}  Rev CAGR3y {_pct(ra.revenue_cagr_3y)}")
    if d and d.intrinsic_value_per_share:
        out.append(f"  DCF intrinsic {_num(d.intrinsic_value_per_share, '.0f')} {d.currency} vs price "
                   f"{_num(d.current_price, '.0f')}  →  margin of safety {_pct(d.margin_of_safety)}, "
                   f"expected return {_pct(d.expected_return)}")
        if d.note:
            out.append(f"    ({d.note})")

    # Peers
    pc = r.peers
    if pc and pc.peers:
        out.append(_rule(f"PEERS — {pc.sector or ''}"))
        out.append(f"  {'Ticker':13}{'MktCap':>12}{'NetM':>7}{'PE':>7}{'ROE':>7}{'RevGr':>7}{'Share':>7}")
        for row in pc.peers:
            mc = _money(row.market_cap, p.currency)
            out.append(f"  {row.ticker:13}{mc:>12}{_pct(row.net_margin):>7}"
                       f"{_num(row.pe, '.1f'):>7}{_pct(row.roe):>7}"
                       f"{_pct(row.revenue_growth_yoy):>7}{_pct(row.market_share_proxy):>7}")
        for line in pc.summary:
            out.append(f"  • {line}")

    # Industry
    ii = r.industry
    if ii and ii.sub_domains:
        out.append(_rule("INDUSTRY"))
        out.append(f"  Sub-domains: {', '.join(ii.sub_domains)}")
        out.append(f"  CAGR: {ii.industry_cagr or 'n/a'}  ·  Outlook drivers: {', '.join(ii.demand_drivers[:4])}")

    # Moat / Risk
    if r.moat or r.risk:
        out.append(_rule("MOAT & RISK"))
        if r.moat:
            out.append(f"  Moat {r.moat.moat_score}/10 — sources: {', '.join(r.moat.sources) or 'assess qualitatively'}")
            for sg in r.moat.signals[:3]:
                out.append(f"    + {sg}")
        if r.risk:
            out.append(f"  Safety {r.risk.risk_score}/5")
            for sg in r.risk.signals[:3]:
                out.append(f"    ! {sg}")

    # SWOT seeds
    if r.swot_seeds:
        out.append(_rule("SWOT (seeds)"))
        for bucket in ("strength", "weakness", "opportunity", "threat"):
            items = [sw.text for sw in r.swot_seeds if sw.bucket == bucket]
            if items:
                out.append(f"  {bucket.upper():12} " + " | ".join(items[:4]))

    # News
    if r.news and r.news.items:
        out.append(_rule("RECENT NEWS"))
        for item in r.news.items[:6]:
            out.append(f"  [{item.category:16}] {item.title[:80]}")

    # Growth drivers
    if r.growth_driver_hints:
        out.append(_rule("GROWTH DRIVERS"))
        for h in r.growth_driver_hints[:6]:
            out.append(f"  → {h}")

    if r.warnings:
        out.append(_rule("NOTES"))
        for w in r.warnings:
            out.append(f"  ! {w}")

    # Analysis quality footer — transparency for downstream judgement.
    em = r.evidence
    if em and em.confidence:
        out.append(_rule("ANALYSIS QUALITY"))
        parts = [f"Confidence {em.confidence.score:.0%} ({em.confidence.tier})"]
        if em.data_coverage is not None:
            parts.append(f"Coverage {em.data_coverage:.0%}")
        parts.append(f"Sources {em.source_count}")
        if em.as_of:
            parts.append(f"As of {em.as_of}")
        out.append("  " + "  ·  ".join(parts))
        if em.missing_fields:
            out.append(f"  Missing: {', '.join(em.missing_fields)}")

    out.append("\n\033[2mResearch only — not investment advice. Data: public sources (Yahoo Finance).\033[0m")
    return "\n".join(out)


# --------------------------------------------------------------------------------------
# Command handlers
# --------------------------------------------------------------------------------------
def _cmd_analyze(args: argparse.Namespace) -> int:
    from .analysis.report import analyze
    report = analyze(args.query, args.market)

    # --json / --html / --pdf are composable and each does exactly one thing. If none is given,
    # print the terminal report. Nothing is silently discarded when several are combined.
    want_html = getattr(args, "html", _UNSET) is not _UNSET
    want_pdf = getattr(args, "pdf", _UNSET) is not _UNSET
    exit_code = 0

    if args.json:
        print(json.dumps(report.model_dump(), indent=2, default=str))

    if want_html:
        from .export import file_url, save_html
        out = save_html(report, args.html)  # args.html is None when the flag is bare
        print(f"Wrote HTML report to {out}")
        print(f"  Open: {file_url(out)}")  # clickable — opens in the browser on click

    if want_pdf:
        from .export import PdfExportError, file_url, save_pdf
        try:
            out, engine, warnings = save_pdf(report, args.pdf)
            for w in warnings:
                print(f"warning: {w}", file=sys.stderr)
            print(f"Wrote PDF report to {out}  ({engine})")
            print(f"  Open: {file_url(out)}")  # the pdf
            sidecar = out.with_suffix(".html")
            if sidecar.exists():
                print(f"  HTML: {file_url(sidecar)}")  # the html written alongside it
        except PdfExportError as exc:
            # The .html sidecar is still on disk; a failed export is still a failed command.
            print(f"error: PDF export failed.\n{exc}", file=sys.stderr)
            exit_code = 2

    # Automatic HTML report: write one by default unless the user asked for a specific artifact
    # (--html / --pdf already produce a document) or opted out with --no-html. The announcement
    # goes to stderr so `investo analyze X --json` stays pipeable on stdout.
    if not (want_html or want_pdf or getattr(args, "no_html", False)):
        from .export import file_url, save_html
        out = save_html(report, None)
        print(f"Wrote HTML report to {out}", file=sys.stderr)
        print(f"  Open: {file_url(out)}", file=sys.stderr)

    if not (args.json or want_html or want_pdf):
        print(render_report(report))
    return exit_code


def _cmd_search(args: argparse.Namespace) -> int:
    from .resolve import resolve
    res = resolve(args.query, args.market)
    if args.json:
        print(json.dumps(res.model_dump(), indent=2, default=str))
        return 0
    if res.resolved:
        print(f"Best match: {res.resolved.symbol}  ({res.resolved.name})")
    if res.note:
        print(f"Note: {res.note}")
    print("Candidates:")
    for c in res.candidates[:8]:
        print(f"  {c.symbol:16} {c.market or '':4} {c.name or ''}")
    return 0


def _cmd_score(args: argparse.Namespace) -> int:
    from .server import score_company
    result = score_company(args.ticker, args.market)
    print(json.dumps(result.model_dump(), indent=2, default=str))
    return 0


def _cmd_peers(args: argparse.Namespace) -> int:
    from .analysis.peers import compare_peers
    from .server import _symbol
    result = compare_peers(_symbol(args.ticker, args.market))
    print(json.dumps(result.model_dump(), indent=2, default=str))
    return 0


def _add_market(p: argparse.ArgumentParser) -> None:
    p.add_argument("--market", default="IN", help="Preferred market: IN (NSE/BSE) or US (default: IN)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="investo", description="Investo — company analysis agent.")
    sub = parser.add_subparsers(dest="command", required=True)

    pa = sub.add_parser("analyze", help="Full investment analysis")
    pa.add_argument("query", help="Company name or ticker")
    pa.add_argument("--json", action="store_true", help="Emit raw JSON to stdout")
    # nargs="?" + a distinct default: absent => _UNSET (don't write); bare => None (default name);
    # with a value => that path. This is what lets --json/--html/--pdf compose.
    pa.add_argument("--html", nargs="?", const=None, default=_UNSET, metavar="FILE",
                    help="Write a self-contained HTML research note (default name if FILE omitted)")
    pa.add_argument("--pdf", nargs="?", const=None, default=_UNSET, metavar="FILE",
                    help="Write a PDF via headless Chrome/Edge (default name if FILE omitted)")
    pa.add_argument("--no-html", action="store_true",
                    help="Suppress the HTML report that is otherwise written automatically")
    _add_market(pa)
    pa.set_defaults(func=_cmd_analyze)

    ps = sub.add_parser("search", help="Resolve a name to a ticker")
    ps.add_argument("query")
    ps.add_argument("--json", action="store_true")
    _add_market(ps)
    ps.set_defaults(func=_cmd_search)

    psc = sub.add_parser("score", help="0-100 rating (JSON)")
    psc.add_argument("ticker")
    _add_market(psc)
    psc.set_defaults(func=_cmd_score)

    pp = sub.add_parser("peers", help="Peer comparison (JSON)")
    pp.add_argument("ticker")
    _add_market(pp)
    pp.set_defaults(func=_cmd_peers)
    return parser


def main(argv: list[str] | None = None) -> int:
    # Ensure ₹, box-drawing and arrow glyphs print on Windows (cp1252) consoles.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    from .logging_config import configure_logging
    configure_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
