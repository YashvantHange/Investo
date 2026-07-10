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
from typing import Optional

from .models import AnalysisReport


# --------------------------------------------------------------------------------------
# Formatting helpers
# --------------------------------------------------------------------------------------
def _money(value: Optional[float], currency: Optional[str]) -> str:
    if value is None:
        return "n/a"
    cur = (currency or "").upper()
    if cur == "INR":
        return f"₹{value / 1e7:,.0f} Cr"
    if abs(value) >= 1e9:
        return f"{value / 1e9:,.1f}B {cur}".strip()
    return f"{value:,.0f} {cur}".strip()


def _pct(value: Optional[float]) -> str:
    return f"{value:.1%}" if value is not None else "n/a"


def _num(value: Optional[float], fmt: str = ".2f") -> str:
    return format(value, fmt) if value is not None else "n/a"


def _rule(title: str) -> str:
    return f"\n\033[1m{title}\033[0m\n" + "-" * max(len(title), 40)


def _bar(normalized: float, width: int = 10) -> str:
    filled = int(round(normalized * width))
    return "█" * filled + "·" * (width - filled)


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

    p = r.profile
    out.append(f"\n\033[1m{p.name or r.resolved.symbol}\033[0m  ({r.resolved.symbol})")
    out.append(f"{p.sector or 'n/a'} / {p.industry or 'n/a'}  ·  {p.exchange or ''}  ·  {p.country or ''}")
    if p.market_cap:
        out.append(f"Market cap {_money(p.market_cap, p.currency)}  ·  Price {_num(p.current_price)} {p.currency or ''}")
    if p.business_summary:
        summary = p.business_summary
        out.append("\n" + (summary[:400] + ("…" if len(summary) > 400 else "")))

    # Rating
    s = r.score
    if s:
        out.append(_rule(f"RATING: {s.total}/100  —  {s.verdict}"))
        for b in s.buckets:
            out.append(f"  {b.name:18} {_bar(b.normalized)} {b.score:5.1f}/{b.weight:<4.0f} {b.rationale}")

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
            mc = _money(row.market_cap, r.profile.currency)
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

    out.append("\n\033[2mResearch only — not investment advice. Data: public sources (Yahoo Finance).\033[0m")
    return "\n".join(out)


# --------------------------------------------------------------------------------------
# Command handlers
# --------------------------------------------------------------------------------------
def _cmd_analyze(args: argparse.Namespace) -> int:
    from .analysis.report import analyze
    report = analyze(args.query, args.market)
    if args.json:
        print(json.dumps(report.model_dump(), indent=2, default=str))
    else:
        print(render_report(report))
    return 0


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
    print(json.dumps(result, indent=2, default=str))
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
    pa.add_argument("--json", action="store_true", help="Emit raw JSON")
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


def main(argv: Optional[list[str]] = None) -> int:
    # Ensure ₹, box-drawing and arrow glyphs print on Windows (cp1252) consoles.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
