"""The HTML backend: an institutional equity-research note.

Section *order and titles* come from :mod:`sections`; this module owns only the HTML rendering of
each, dispatched through ``HTML_RENDERERS``. A section whose evidence is absent renders nothing
at all rather than an empty heading — a report should be shorter when less is known, not padded.

Everything is self-contained (inline CSS, system fonts, hand-written SVG, no script), which keeps
it CSP-safe and, more practically, means the headless-Chrome PDF path has nothing to fetch.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from ..models import AnalysisReport
from . import charts
from .css import CSS
from .fmt import EM_DASH, esc, metric, money, num, pct, price, ratio, signed_pct, tone
from .sections import SECTIONS

_ARROW = {"up": "▲", "flat": "—", "down": "▼"}
_STATUS_CLASS = {"pass": "pass", "warn": "warn", "fail": "fail", "unknown": "unknown"}
_TONE_CLASS = {
    "bullish": "good", "positive": "good", "strong": "good", "cheap": "good",
    "Excellent": "good", "Good": "good",
    "neutral": "flat", "fair": "flat", "Fair": "flat", "moderate": "warn",
    "cautious": "warn", "Weak": "warn", "weak": "warn", "expensive": "warn",
    "bearish": "bad", "Poor": "bad",
    "none": "good", "low": "good", "high": "bad", "severe": "bad", "critical": "bad",
}


def render_html(report: AnalysisReport, *, standalone: bool = True) -> str:
    """Render the report as a research note. Full document unless ``standalone=False``."""
    body = _document(report)
    if not standalone:
        return f"<style>{CSS}</style>\n{body}"
    name = _name(report)
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{esc(name)} — Investo equity research</title>"
        f"<style>{CSS}</style></head><body>{body}</body></html>"
    )


# --------------------------------------------------------------------------------------
# Document
# --------------------------------------------------------------------------------------
def _document(r: AnalysisReport) -> str:
    parts = [_runhead(r), _masthead(r), _keydata(r)]
    for section in SECTIONS:
        renderer = HTML_RENDERERS.get(section.key)
        if renderer is None:
            continue
        inner = renderer(r)
        if not inner:
            continue  # no evidence -> no section, rather than an empty heading
        parts.append(
            f'<section class="sec" id="s{section.number}">'
            f'<h2><span class="n">{section.number}</span>{esc(section.title)}</h2>'
            f"{inner}</section>"
        )
    parts.append(_footnotes(r))
    parts.append(_disclaimer())
    parts.append(_runfoot(r))
    return f'<main class="paper">{"".join(p for p in parts if p)}</main>'


def _name(r: AnalysisReport) -> str:
    return (r.profile.name if r.profile else None) or r.query


def _symbol(r: AnalysisReport) -> str:
    return r.resolved.symbol if r.resolved else ""


def _today() -> str:
    return date.today().strftime("%d %B %Y")


def _runhead(r: AnalysisReport) -> str:
    return (f'<div class="runhead">{esc(_name(r))} · {esc(_symbol(r))}'
            f'<span class="r">Investo equity research · {esc(_today())}</span></div>')


def _runfoot(r: AnalysisReport) -> str:
    return ('<div class="runfoot">Research and education only — not investment advice.'
            '<span class="r">Generated from public data</span></div>')


def _masthead(r: AnalysisReport) -> str:
    p = r.profile
    bits = [x for x in ((p.sector if p else None), (p.industry if p else None),
                        (p.exchange if p else None)) if x]
    if r.industry and r.industry.peer_group:
        bits.insert(0, r.industry.peer_group)
    verdict = ""
    if r.thesis and r.thesis.verdict:
        verdict = f'<span class="verdict-line">{esc(r.thesis.verdict)}</span>'
    stand = ""
    if r.thesis and r.thesis.summary:
        stand = f'<p class="standfirst">{esc(r.thesis.summary)}</p>'
    return (
        '<header class="masthead">'
        f'<div class="eyebrow"><span>Investo equity research · {esc(_today())}</span>{verdict}</div>'
        f'<h1>{esc(_name(r))}<span class="ticker">{esc(_symbol(r))}</span></h1>'
        f'<p class="small muted" style="margin:0">{esc(" · ".join(bits))}</p>'
        f"{stand}</header>"
    )


def _keydata(r: AnalysisReport) -> str:
    p = r.profile
    cur = p.currency if p else None
    items: list[tuple[str, str]] = []
    if p and p.current_price is not None:
        items.append(("Price", price(p.current_price, cur)))
    if p and p.market_cap is not None:
        items.append(("Market cap", money(p.market_cap, cur)))
    if p and p.fifty_two_week_low is not None and p.fifty_two_week_high is not None:
        items.append(("52-week range", f"{num(p.fifty_two_week_low, 0)}–"
                                       f"{num(p.fifty_two_week_high, 0)}"))
    if r.score:
        items.append(("Investo rating", f"{r.score.total:.0f}/100"))
    if r.ratios and r.ratios.pe is not None:
        items.append(("P/E", ratio(r.ratios.pe)))
    if r.dcf and r.dcf.margin_of_safety is not None:
        items.append(("Margin of safety", signed_pct(r.dcf.margin_of_safety, 0)))
    if not items:
        return ""
    cells = "".join(f'<div class="kd"><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>' for k, v in items)
    return f'<dl class="keydata">{cells}</dl>'


def _exhibit(label: str, chart: charts.Chart | None) -> str:
    """Place a figure with its caption and source line. Never composes them here."""
    if chart is None or not chart.svg:
        return ""
    src = f'<div class="src">{esc(chart.source)}</div>' if chart.source else ""
    cap = f'<div class="cap"><span class="lbl">{esc(label)}</span>{esc(chart.caption or chart.title)}</div>'
    return f'<figure class="exhibit">{cap}{chart.svg}{src}</figure>'


def _h2note(text: str) -> str:
    return f'<span class="h2note">{esc(text)}</span>'


# --------------------------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------------------------
def _thesis(r: AnalysisReport) -> str:
    t = r.thesis
    if not t:
        return ""
    pros = "".join(f"<li>{esc(x)}</li>" for x in t.pros)
    cons = "".join(f"<li>{esc(x)}</li>" for x in t.cons)
    if not (pros or cons):
        return ""
    empty = '<li class="muted">—</li>'
    body = (
        '<div class="twocol">'
        f'<div><h3>The case for</h3><ul>{pros or empty}</ul></div>'
        f'<div><h3>The case against</h3><ul>{cons or empty}</ul></div>'
        "</div>"
    )
    facts = []
    if t.quality:
        facts.append(f'Quality <span class="st {_TONE_CLASS.get(t.quality, "flat")}">'
                     f"{esc(t.quality)}</span>")
    if t.valuation_stance:
        facts.append(f'Valuation <span class="st {_TONE_CLASS.get(t.valuation_stance, "flat")}">'
                     f"{esc(t.valuation_stance)}</span>")
    if t.confidence:
        facts.append(f'<span class="muted">Confidence {t.confidence.score:.0%} '
                     f"{esc(t.confidence.tier)}</span>")
    line = f'<p class="small">{" · ".join(facts)}</p>' if facts else ""
    return body + line


def _score(r: AnalysisReport) -> str:
    s = r.score
    if not s or not s.buckets:
        return ""
    rows = [(b.name, b.normalized, f"{b.score:.1f}/{b.weight:.0f}") for b in s.buckets]
    svg = charts.hbar_chart(
        rows, title=f"Score decomposition for {_name(r)}",
        desc="Points earned in each weighted bucket, out of that bucket's maximum.")
    chart = charts.Chart(
        title="Score decomposition",
        svg=svg,
        caption="Points earned per weighted bucket",
        source="Source: Investo composite scoring model (analysis/scoring.py). Weights are the "
               "model's own judgement, not a market consensus.",
    )
    reasons = "".join(
        f'<tr><td class="name">{esc(b.name)}</td>'
        f'<td class="num">{b.score:.1f}/{b.weight:.0f}</td>'
        f'<td class="reason">{esc(b.rationale or "")}</td></tr>'
        for b in s.buckets)
    table = (f'<table class="data"><thead><tr><th>Bucket</th><th class="num">Score</th>'
             f"<th>Rationale</th></tr></thead><tbody>{reasons}</tbody></table>")
    lede = (f'<p class="lede"><strong>{s.total:.1f} / 100</strong> — {esc(s.verdict)}.</p>')
    return lede + _exhibit("Exhibit 1", chart) + table


def _relative(r: AnalysisReport) -> str:
    rel = r.relative
    if not rel:
        return ""
    if not rel.metrics:
        note = rel.note or "No peer comparison available."
        return f'<p class="muted">{esc(note)}</p>'

    rows = [
        (m.name, m.percentile or 0.0, metric(m.unit, m.company),
         f"{m.name}: {metric(m.unit, m.company)} vs industry {metric(m.unit, m.industry)}")
        for m in rel.metrics
    ]
    svg = charts.diverging_bars(
        rows, title=f"{_name(r)} versus its peer group",
        desc="Each metric's favourable-side percentile within the peer set; the midpoint is the "
             "peer median.")
    n_peers = max(rel.peer_count - 1, 0)
    # Plain text: _exhibit escapes the source line once when it places the figure. Pre-escaping
    # here would double-encode (& -> &amp; -> &amp;amp;).
    group = f" — {rel.peer_group_label}" if rel.peer_group_label else ""
    src = (f"Source: Yahoo Finance fundamentals; Investo {rel.basis} peer group{group} "
           f"({n_peers} peers). Percentiles are a rank within the set, not the market.")
    if rel.basis == "sector-fallback":
        src += " This cohort was inferred from the company's industry label, not curated."
    chart = charts.Chart(title="Standing versus peer group", svg=svg,
                         caption="Favourable-side percentile by metric", source=src)

    body = ""
    for m in rel.metrics:
        body += (f'<tr><td class="name">{esc(m.name)}</td>'
                 f'<td class="num">{metric(m.unit, m.company)}</td>'
                 f'<td class="num muted">{metric(m.unit, m.industry)}</td>'
                 f'<td class="num delta {"pos" if m.better else "neg"}">'
                 f'{metric(m.unit, m.delta) if m.delta is not None else EM_DASH}</td>'
                 f'<td><span class="st {tone(m.percentile)}">'
                 f'{esc(_band_text(m.percentile))}</span></td></tr>')
    table = (
        '<table class="data"><thead><tr><th>Metric</th><th class="num">Company</th>'
        '<th class="num">Industry</th><th class="num">Delta</th><th>Standing</th>'
        f"</tr></thead><tbody>{body}</tbody></table>"
    )
    note = _h2note(f"{n_peers} peers · {rel.basis}")
    return note + _exhibit("Exhibit 2", chart) + table


def _band_text(percentile: float | None) -> str:
    from .fmt import band
    return band(percentile)


def _peers(r: AnalysisReport) -> str:
    pc = r.peers
    if not pc or not pc.peers:
        return f'<p class="muted">{esc(pc.note)}</p>' if pc and pc.note else ""
    subject = _symbol(r)
    pts = [(row.ticker.split(".")[0], row.net_margin, row.revenue_growth_yoy,
            row.ticker == subject)
           for row in pc.peers if row.net_margin is not None
           and row.revenue_growth_yoy is not None]
    ex = ""
    if len(pts) >= 2:
        svg = charts.scatter(pts, title=f"{_name(r)} against its peer group",
                             x_label="Net margin", y_label="Revenue growth",
                             desc="Each peer positioned by net margin and revenue growth; the "
                                  "subject company is highlighted.")
        ex = _exhibit("Exhibit 3", charts.Chart(
            title="Margin versus growth",
            svg=svg,
            caption="Net margin versus revenue growth",
            source="Source: Yahoo Finance (trailing twelve months). Revenue and market cap are "
                   "normalised to the subject's trading currency.",
        ))
    body = ""
    for row in pc.peers:
        is_sub = row.ticker == subject
        body += (
            f'<tr><td class="name">{"<strong>" if is_sub else ""}{esc(row.name or row.ticker)}'
            f'{"</strong>" if is_sub else ""}<br><span class="muted small">'
            f'{esc(row.ticker)}</span></td>'
            f'<td class="num">{money(row.market_cap, r.profile.currency if r.profile else None)}</td>'
            f'<td class="num">{pct(row.net_margin)}</td>'
            f'<td class="num">{pct(row.revenue_growth_yoy)}</td>'
            f'<td class="num">{ratio(row.pe)}</td>'
            f'<td class="num">{ratio(row.ev_ebitda)}</td></tr>'
        )
    table = (
        '<table class="data"><thead><tr><th>Company</th><th class="num">Market cap</th>'
        '<th class="num">Net margin</th><th class="num">Rev growth</th><th class="num">P/E</th>'
        f'<th class="num">EV/EBITDA</th></tr></thead><tbody>{body}</tbody></table>'
    )
    obs = "".join(f"<li>{esc(s)}</li>" for s in pc.summary)
    obs_html = f'<ul class="plain">{obs}</ul>' if obs else ""
    note = _h2note(pc.peer_group_label) if pc.peer_group_label else ""
    return note + ex + table + obs_html


def _industry(r: AnalysisReport) -> str:
    ii = r.industry
    if not ii:
        return ""
    blocks: list[str] = []
    if ii.future_demand:
        blocks.append(f'<p class="lede">{esc(ii.future_demand)}</p>')
    defs = ""
    if ii.sub_domains:
        defs += f"<dt>Sub-domains</dt><dd>{esc(' · '.join(ii.sub_domains))}</dd>"
    if ii.demand_drivers:
        defs += f"<dt>Demand drivers</dt><dd>{esc(' · '.join(ii.demand_drivers))}</dd>"
    if ii.industry_cagr:
        stamp = f" (Investo estimate, as of {esc(ii.as_of)})" if ii.as_of else " (Investo estimate)"
        defs += f"<dt>Industry growth</dt><dd>{esc(ii.industry_cagr)}<span class='muted small'>{stamp}</span></dd>"
    if ii.risks:
        defs += f"<dt>Industry risks</dt><dd>{esc(' · '.join(ii.risks))}</dd>"
    if defs:
        blocks.append(f'<dl class="defs">{defs}</dl>')
    if not blocks:
        return ""
    # Say plainly when Investo's framing departs from the exchange's classification.
    if ii.peer_group and ii.industry and ii.basis == "curated":
        blocks.append(
            f'<p class="small muted">Framed as <strong>{esc(ii.peer_group)}</strong>; the '
            f'exchange classifies it as “{esc(ii.industry)}”, which understates how much of the '
            f'business tracks its own cohort rather than the broader sector.</p>')
    elif ii.note:
        blocks.append(f'<p class="small muted">{esc(ii.note)}</p>')
    head = _h2note(ii.peer_group) if ii.peer_group else ""
    return head + "".join(blocks)


def _valuation(r: AnalysisReport) -> str:
    d = r.dcf
    ra = r.ratios
    if not d and not ra:
        return ""
    cur = (r.profile.currency if r.profile else None)
    blocks: list[str] = []
    if d and d.intrinsic_value_per_share is not None:
        lede = (f'<p class="lede">DCF intrinsic value '
                f'<strong>{price(d.intrinsic_value_per_share, cur)}</strong> per share')
        if d.margin_of_safety is not None:
            word = "above" if d.margin_of_safety > 0 else "below"
            lede += (f", {signed_pct(abs(d.margin_of_safety), 0).lstrip('+')} {word} the market "
                     f"price")
        lede += ".</p>"
        blocks.append(lede)
        svg = charts.value_vs_price(d.intrinsic_value_per_share, d.current_price,
                                    currency_fmt=lambda v: price(v, cur))
        if svg:
            blocks.append(_exhibit("Exhibit 4", charts.Chart(
                title="Intrinsic value versus market price",
                svg=svg,
                caption="Two-stage DCF against the current price",
                source="Source: Investo two-stage DCF (analysis/dcf.py) over Yahoo Finance "
                       "statements. A DCF is a model, not a measurement — its output moves "
                       "sharply with the discount rate and terminal growth assumed.",
            )))
    if ra:
        pairs = [
            ("P/E", ratio(ra.pe)), ("Forward P/E", ratio(ra.forward_pe)),
            ("P/B", ratio(ra.pb)), ("PEG", ratio(ra.peg)),
            ("EV/EBITDA", ratio(ra.ev_ebitda)), ("P/S", ratio(ra.price_to_sales)),
            ("ROE", pct(ra.roe)), ("ROCE", pct(ra.roce)),
            ("Operating margin", pct(ra.operating_margin)), ("Net margin", pct(ra.net_margin)),
            ("Debt/Equity", ratio(ra.debt_to_equity)), ("Current ratio", ratio(ra.current_ratio)),
            ("Dividend yield", pct(ra.dividend_yield)),
        ]
        live = [(k, v) for k, v in pairs if v != EM_DASH]
        if live:
            cells = "".join(f'<div class="kd"><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>'
                            for k, v in live)
            blocks.append(f'<dl class="keydata" style="margin-bottom:6pt">{cells}</dl>')
    if d and d.note:
        blocks.append(f'<p class="small muted">{esc(d.note)}</p>')
    return "".join(blocks)


def _growth(r: AnalysisReport) -> str:
    g = r.growth_outlook
    if not g or not g.drivers:
        return ""
    blocks: list[str] = []
    if g.primary_engine:
        blocks.append(f'<p class="lede">{esc(g.primary_engine)}</p>')
    rows = [(d.name, d.contribution_pct or 0.0, f"{(d.contribution_pct or 0):.0%}")
            for d in g.drivers]
    svg = charts.hbar_chart(rows, title="Growth drivers by estimated contribution",
                            desc="Each driver's estimated share of five-year growth.")
    blocks.append(_exhibit("Exhibit 5", charts.Chart(
        title="Growth drivers",
        svg=svg,
        caption="Estimated share of five-year growth by driver",
        source="Source: Investo curated growth engine (data/growth.yaml) blended with "
               "data-derived signals. Contributions are estimates, not company guidance.",
    )))
    body = "".join(
        f'<tr><td class="name">{esc(d.name)}</td>'
        f'<td class="num">{(d.contribution_pct or 0):.0%}</td>'
        f'<td class="reason">{esc(", ".join(d.risks[:2]))}</td></tr>'
        for d in g.drivers)
    blocks.append('<table class="data"><thead><tr><th>Driver</th>'
                  '<th class="num">Contribution</th><th>Key risks</th></tr></thead>'
                  f"<tbody>{body}</tbody></table>")
    if g.catalysts:
        items = "".join(f'<li><span class="yr">{esc(c.year or "")}</span>'
                        f"<span>{esc(c.event)}</span></li>"
                        for c in g.catalysts if c.event)
        if items:
            blocks.append(f'<ul class="timeline">{items}</ul>')
    if g.blended_5y_low is not None and g.blended_5y_high is not None:
        blocks.append(f'<p class="small muted">Blended five-year band '
                      f"{g.blended_5y_low:.0%}–{g.blended_5y_high:.0%}"
                      f"{f' · signal: {esc(g.growth_signal)}' if g.growth_signal else ''}.</p>")
    return "".join(blocks)


def _trend(r: AnalysisReport) -> str:
    ft = r.fundamental_trend
    if not ft or not ft.metrics:
        return ""
    body = ""
    for m in ft.metrics:
        arrows = "".join(f'<span class="{d}">{_ARROW.get(d, "·")}</span>' for d in m.directions)
        # `values` are newest-first; a sparkline reads left-to-right in time.
        spark = charts.sparkline(list(reversed(m.values)), tip=f"{m.name} trend") if m.values else ""
        body += (f'<tr><td class="name">{esc(m.name)}</td>'
                 f'<td>{spark}</td>'
                 f'<td class="trend-seq">{arrows}</td>'
                 f'<td><span class="st {_TONE_CLASS.get(m.health or "", "flat")}">'
                 f'{esc(m.health or "")}</span></td>'
                 f'<td class="num">{signed_pct(m.cagr)}</td></tr>')
    note = _h2note(ft.overall_health) if ft.overall_health else ""
    return note + ('<table class="data"><thead><tr><th>Metric</th><th>Trend</th>'
                   '<th>Direction</th><th>Health</th><th class="num">CAGR</th>'
                   f"</tr></thead><tbody>{body}</tbody></table>")


def _buffett(r: AnalysisReport) -> str:
    b = r.buffett
    if not b or not b.criteria:
        return ""
    body = ""
    for c in b.criteria:
        conf = f"{c.confidence.score:.0%}" if c.confidence else EM_DASH
        trend = f' <span class="muted small">{esc(c.trend_verdict)}</span>' if c.trend_verdict else ""
        body += (f'<tr><td><span class="st {_STATUS_CLASS.get(c.status, "unknown")}">'
                 f'{esc(c.status)}</span></td>'
                 f'<td class="name">{esc(c.name)}{trend}</td>'
                 f'<td class="reason">{esc(c.reason or "")}</td>'
                 f'<td class="num muted">{conf}</td></tr>')
    lede = ""
    if b.weighted_score is not None:
        lede = (f'<p class="lede"><strong>{b.weighted_score:.0f} / 100</strong>'
                f'{f" — {esc(b.verdict)}" if b.verdict else ""}.</p>')
    return lede + ('<table class="data"><thead><tr><th>Status</th><th>Criterion</th>'
                   '<th>Reason</th><th class="num">Conf.</th></tr></thead>'
                   f"<tbody>{body}</tbody></table>")


def _shareholding(r: AnalysisReport) -> str:
    sh = r.shareholding
    if not sh or not sh.latest:
        return ""
    lt = sh.latest
    items = [(lbl, pct(v)) for lbl, v in (
        ("Promoter", lt.promoter), ("FII", lt.fii), ("DII", lt.dii),
        ("Institutional", lt.institutional), ("Public", lt.public),
        ("Pledge", lt.promoter_pledge)) if v is not None]
    if not items:
        return ""
    cells = "".join(f'<div class="kd"><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>' for k, v in items)
    obs = "".join(f"<li>{esc(o)}</li>" for o in sh.observations)
    obs_html = f'<ul class="plain">{obs}</ul>' if obs else ""
    note = f'<p class="small muted">{esc(sh.note)}</p>' if sh.note else ""
    head = _h2note(f"{sh.source}"
                   f"{f' · {sh.ownership_signal}' if sh.ownership_signal else ''}")
    return head + f'<dl class="keydata">{cells}</dl>' + obs_html + note


def _moat(r: AnalysisReport) -> str:
    m = r.moat
    if not m or not m.signals:
        return ""
    head = _h2note(f"{m.moat_score:.0f}/10") if m.moat_score is not None else ""
    items = "".join(f"<li>{esc(s)}</li>" for s in m.signals)
    note = f'<p class="small muted">{esc(m.note)}</p>' if m.note else ""
    return head + f'<ul class="plain">{items}</ul>' + note


def _risk(r: AnalysisReport) -> str:
    rk = r.risk
    if not rk or not rk.signals:
        return ""
    head = _h2note(f"safety {rk.risk_score:.1f}/5") if rk.risk_score is not None else ""
    items = "".join(f"<li>{esc(s)}</li>" for s in rk.signals)
    flags = ""
    if rk.regulatory_flags:
        flags = f'<p class="small muted">Regulatory: {esc(", ".join(rk.regulatory_flags))}</p>'
    return head + f'<ul class="plain">{items}</ul>' + flags


def _red_flags(r: AnalysisReport) -> str:
    rf = r.red_flags
    if not rf:
        return ""
    head = _h2note(f"risk: {rf.risk_level}") if rf.risk_level else ""
    if not rf.flags:
        # Say it explicitly — an empty section reads as an oversight, not as an all-clear.
        return head + '<p>No material red flags detected by the automated checks.</p>'
    body = "".join(
        f'<tr><td><span class="st {_TONE_CLASS.get(f.severity, "flat")}">{esc(f.severity)}'
        f'</span></td><td class="name">{esc(f.issue)}</td>'
        f'<td class="reason">{esc(f.detail or "")}</td></tr>'
        for f in rf.flags)
    return head + ('<table class="data"><thead><tr><th>Severity</th><th>Issue</th>'
                   f"<th>Detail</th></tr></thead><tbody>{body}</tbody></table>")


_SWOT_TITLES = {"strength": "Strengths", "weakness": "Weaknesses",
                "opportunity": "Opportunities", "threat": "Threats"}


def _swot(r: AnalysisReport) -> str:
    if not r.swot_seeds:
        return ""
    cols = ""
    for bucket in ("strength", "weakness", "opportunity", "threat"):
        items = [s.text for s in r.swot_seeds if s.bucket == bucket]
        if not items:
            continue
        li = "".join(f"<li>{esc(t)}</li>" for t in items)
        cols += f"<div><h3>{_SWOT_TITLES[bucket]}</h3><ul>{li}</ul></div>"
    return f'<div class="twocol">{cols}</div>' if cols else ""


def _news(r: AnalysisReport) -> str:
    nf = r.news
    if not nf or not nf.items:
        return ""
    body = "".join(
        f'<tr><td class="num muted">{esc((i.published or "")[:10])}</td>'
        f'<td class="name">{esc(i.title)}</td>'
        f'<td class="muted small">{esc(i.category)}</td></tr>'
        for i in nf.items[:12])
    return ('<table class="data"><thead><tr><th class="num">Date</th><th>Headline</th>'
            f"<th>Category</th></tr></thead><tbody>{body}</tbody></table>")


def _warnings(r: AnalysisReport) -> str:
    if not r.warnings:
        return ""
    items = "".join(f"<li>{esc(w)}</li>" for w in r.warnings)
    return f'<ul class="plain">{items}</ul>'


def _evidence(r: AnalysisReport) -> str:
    em = r.evidence
    if not em or not em.confidence:
        return ""
    items = [("Confidence", f"{em.confidence.score:.0%} {em.confidence.tier}")]
    if em.data_coverage is not None:
        items.append(("Data coverage", f"{em.data_coverage:.0%}"))
    items.append(("Sources", str(em.source_count)))
    if em.as_of:
        items.append(("Latest data", em.as_of))
    cells = "".join(f'<div class="kd"><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>' for k, v in items)
    extra = ""
    if em.missing_fields:
        extra += (f'<p class="small muted">Not available: '
                  f"{esc(', '.join(em.missing_fields))}.</p>")
    for note in em.notes:
        extra += f'<p class="small muted">{esc(note)}</p>'
    return f'<dl class="keydata">{cells}</dl>{extra}'


# Each backend owns its own dispatch table; the registry itself stays output-agnostic.
HTML_RENDERERS: dict[str, Callable[[AnalysisReport], str]] = {
    "thesis": _thesis,
    "score": _score,
    "relative": _relative,
    "peers": _peers,
    "industry": _industry,
    "dcf": _valuation,
    "growth_outlook": _growth,
    "fundamental_trend": _trend,
    "buffett": _buffett,
    "shareholding": _shareholding,
    "moat": _moat,
    "risk": _risk,
    "red_flags": _red_flags,
    "swot_seeds": _swot,
    "news": _news,
    "warnings": _warnings,
    "evidence": _evidence,
}


def _footnotes(r: AnalysisReport) -> str:
    notes = [
        "Percentiles in this note are a rank within a small peer set, not a market-wide "
        "percentile. Being best of five is not the same claim as being top-quintile.",
        "Industry growth rates and peer groups are Investo's own curated estimates, dated by "
        "their <em>as of</em> stamp — they are not third-party forecasts.",
        "Confidence measures the quality of the evidence behind a figure, not the likelihood "
        "that the conclusion is correct.",
    ]
    if r.dcf and r.dcf.intrinsic_value_per_share is not None:
        notes.append("The DCF is a two-stage model over reported cash flows; its output is "
                     "highly sensitive to the discount rate and terminal growth assumed.")
    items = "".join(f"<li>{n}</li>" for n in notes)
    return f'<div class="footnotes"><ol>{items}</ol></div>'


def _disclaimer() -> str:
    return ('<div class="disclaimer"><strong>Research and education only — not investment '
            "advice.</strong> Investo is an automated analysis tool. Every figure here is "
            "derived from public data sources that may be incomplete, delayed or wrong, and "
            "every judgement is produced by a deterministic model with no knowledge of your "
            "circumstances. Nothing in this document is a recommendation to buy or sell any "
            "security. Do your own due diligence.</div>")
