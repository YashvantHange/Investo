"""Render an :class:`AnalysisReport` as a self-contained, theme-aware HTML one-pager.

A single research-note style page: masthead, a KPI strip (rating, Buffett fit, ownership, risk,
growth, valuation), then card sections for the thesis, relative-to-industry, Buffett checklist,
shareholding, growth engine, fundamentals trend and red flags, closing with an analysis-quality
footer. Confidence is shown as thin meter bars and statuses as semantic pills throughout.

No external assets (CSP-safe): all CSS is inline and fonts are system stacks. ``render_html`` returns
a full standalone document; pass ``standalone=False`` for a body fragment (e.g. an Artifact).
"""

from __future__ import annotations

from html import escape

from ..models import AnalysisReport

# Semantic classes shared by pills/among statuses.
_STATUS_CLASS = {"pass": "good", "warn": "warn", "fail": "bad", "unknown": "muted"}
_RISK_CLASS = {"none": "good", "low": "good", "moderate": "warn", "high": "bad", "severe": "bad"}
_SIGNAL_CLASS = {
    "bullish": "good", "positive": "good", "neutral": "muted", "cautious": "warn", "bearish": "bad",
    "strong": "good", "moderate": "warn", "weak": "bad",
    "cheap": "good", "fair": "muted", "expensive": "warn",
    "Excellent": "good", "Good": "good", "Fair": "muted", "Weak": "warn", "Poor": "bad",
}
_ARROW = {"up": "▲", "flat": "▬", "down": "▼"}


def render_html(report: AnalysisReport, *, standalone: bool = True) -> str:
    """Render the report to HTML. Full document unless ``standalone=False``."""
    body = _body(report)
    style = _CSS
    if not standalone:
        return f"<style>{style}</style>\n{body}"
    title = escape((report.profile.name if report.profile else None) or report.query)
    return (
        f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{title} — Investo analysis</title><style>{style}</style></head>"
        f"<body>{body}</body></html>"
    )


# --------------------------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------------------------
def _body(r: AnalysisReport) -> str:
    parts = [_masthead(r), _kpis(r)]
    parts += [
        _thesis(r), _rating(r), _relative(r), _buffett(r), _shareholding(r),
        _growth(r), _trend(r), _red_flags(r), _quality(r),
    ]
    inner = "\n".join(p for p in parts if p)
    return f"<main class=\"page\">{inner}<footer class=\"disclaimer\">Research and education " \
           f"only — not investment advice. Data: public sources.</footer></main>"


def _masthead(r: AnalysisReport) -> str:
    p = r.profile
    name = escape((p.name if p else None) or r.query)
    ticker = escape(r.resolved.symbol if r.resolved else "")
    sub = " · ".join(escape(x) for x in ((p.sector if p else None), (p.industry if p else None),
                                         (p.exchange if p else None)) if x)
    price = _money(p.current_price, p.currency) if p and p.current_price else ""
    cap = _money(p.market_cap, p.currency) if p and p.market_cap else ""
    facts = []
    if price:
        facts.append(f"<span class=\"fact\"><em>Price</em>{price}</span>")
    if cap:
        facts.append(f"<span class=\"fact\"><em>Market cap</em>{cap}</span>")
    if p and p.fifty_two_week_low and p.fifty_two_week_high:
        facts.append(f"<span class=\"fact\"><em>52-wk</em>{_num(p.fifty_two_week_low)}–"
                     f"{_num(p.fifty_two_week_high)}</span>")
    verdict = ""
    if r.thesis and r.thesis.verdict:
        cls = _SIGNAL_CLASS.get(r.thesis.quality or "", "muted")
        verdict = f"<div class=\"verdict pill {cls}\">{escape(r.thesis.verdict)}</div>"
    return (
        f"<header class=\"masthead\"><div class=\"mast-top\"><span class=\"eyebrow\">Investo "
        f"equity research</span>{verdict}</div>"
        f"<h1>{name} <span class=\"ticker\">{ticker}</span></h1>"
        f"<p class=\"sub\">{sub}</p><div class=\"facts\">{''.join(facts)}</div></header>"
    )


def _kpis(r: AnalysisReport) -> str:
    tiles = []
    if r.score:
        tiles.append(_tile("Rating", f"{r.score.total:.0f}", "/100", r.score.verdict,
                           _score_class(r.score.total)))
    if r.buffett and r.buffett.weighted_score is not None:
        tiles.append(_tile("Buffett fit", f"{r.buffett.weighted_score:.0f}", "/100",
                           r.buffett.verdict, _score_class(r.buffett.weighted_score)))
    if r.shareholding and r.shareholding.ownership_signal:
        own = r.shareholding.ownership_signal
        tiles.append(_tile("Ownership", own.title(), "", "trend", _SIGNAL_CLASS.get(own, "muted")))
    if r.growth_outlook and r.growth_outlook.growth_signal:
        gs = r.growth_outlook.growth_signal
        tiles.append(_tile("Growth 5Y", gs.title(), "", "engine", _SIGNAL_CLASS.get(gs, "muted")))
    if r.red_flags:
        rl = str(r.red_flags.risk_level)
        tiles.append(_tile("Risk", rl.title(), "", f"{len(r.red_flags.flags)} flags",
                           _RISK_CLASS.get(rl, "muted")))
    if r.thesis and r.thesis.valuation_stance:
        vs = r.thesis.valuation_stance
        tiles.append(_tile("Valuation", vs.title(), "", "vs value", _SIGNAL_CLASS.get(vs, "muted")))
    if not tiles:
        return ""
    return f"<section class=\"kpis\">{''.join(tiles)}</section>"


def _thesis(r: AnalysisReport) -> str:
    t = r.thesis
    if not t:
        return ""
    pros = "".join(f"<li>{escape(x)}</li>" for x in t.pros) or "<li class=\"muted\">—</li>"
    cons = "".join(f"<li>{escape(x)}</li>" for x in t.cons) or "<li class=\"muted\">—</li>"
    summary = f"<p class=\"lead\">{escape(t.summary)}</p>" if t.summary else ""
    conf = _meter(t.confidence.score, t.confidence.tier) if t.confidence else ""
    return _card(
        "Investment thesis", summary +
        f"<div class=\"proscons\"><div class=\"pros\"><h4>Pros</h4><ul>{pros}</ul></div>"
        f"<div class=\"cons\"><h4>Cons</h4><ul>{cons}</ul></div></div>",
        aside=conf)


def _rating(r: AnalysisReport) -> str:
    s = r.score
    if not s:
        return ""
    rows = "".join(
        f"<tr><td>{escape(b.name)}</td><td class=\"barcell\">{_bar(b.normalized)}</td>"
        f"<td class=\"num\">{b.score:.1f}/{b.weight:.0f}</td>"
        f"<td class=\"muted small\">{escape(b.rationale or '')}</td></tr>"
        for b in s.buckets)
    return _card(f"Rating — {s.total:.1f}/100 ({escape(s.verdict)})",
                 f"<table class=\"grid\"><tbody>{rows}</tbody></table>")


def _relative(r: AnalysisReport) -> str:
    rel = r.relative
    if not rel or not rel.metrics:
        return ""
    rows = "".join(
        f"<tr><td>{escape(m.name)}</td><td class=\"num\">{_metric(m.unit, m.company)}</td>"
        f"<td class=\"num muted\">{_metric(m.unit, m.industry)}</td>"
        f"<td>{_band_pill(m.percentile, m.better)}</td></tr>"
        for m in rel.metrics)
    head = "<thead><tr><th>Metric</th><th class=\"num\">Company</th>" \
           "<th class=\"num\">Industry</th><th>Standing</th></tr></thead>"
    title = "Relative to industry"
    if rel.peer_group_label:
        title += f" — {escape(rel.peer_group_label)}"
    aside = f"<span class=\"tag\">{rel.peer_count - 1} peers · {escape(rel.basis)}</span>"
    return _card(title, f"<table class=\"grid\">{head}<tbody>{rows}</tbody></table>", aside=aside)


def _buffett(r: AnalysisReport) -> str:
    b = r.buffett
    if not b or not b.criteria:
        return ""
    rows = ""
    for c in b.criteria:
        pill = f"<span class=\"pill {_STATUS_CLASS.get(c.status, 'muted')}\">{c.status}</span>"
        trend = f"<span class=\"tag\">{escape(c.trend_verdict)}</span>" if c.trend_verdict else ""
        conf = _mini_meter(c.confidence.score) if c.confidence else ""
        rows += (f"<tr><td>{pill}</td><td>{escape(c.name)}{trend}</td>"
                 f"<td class=\"muted small\">{escape(c.reason or '')}</td>"
                 f"<td class=\"num\">{conf}</td></tr>")
    title = f"Warren Buffett checklist — {b.weighted_score:.0f}/100"
    if b.verdict:
        title += f" ({escape(b.verdict)})"
    return _card(title, f"<table class=\"grid\"><tbody>{rows}</tbody></table>")


def _shareholding(r: AnalysisReport) -> str:
    sh = r.shareholding
    if not sh or not sh.latest:
        return ""
    lt = sh.latest
    chips = "".join(
        f"<span class=\"chip\"><em>{lbl}</em>{val:.1%}</span>"
        for lbl, val in (("Promoter", lt.promoter), ("FII", lt.fii), ("DII", lt.dii),
                         ("Institutional", lt.institutional), ("Public", lt.public),
                         ("Pledge", lt.promoter_pledge)) if val is not None)
    obs = "".join(f"<li>{escape(o)}</li>" for o in sh.observations)
    obs_html = f"<ul class=\"obs\">{obs}</ul>" if obs else ""
    sig = ""
    if sh.ownership_signal:
        sig = f"<span class=\"pill {_SIGNAL_CLASS.get(sh.ownership_signal, 'muted')}\">" \
              f"{sh.ownership_signal}</span>"
    note = f"<p class=\"muted small\">{escape(sh.note)}</p>" if sh.note else ""
    return _card(f"Shareholding ({escape(sh.source)})",
                 f"<div class=\"chips\">{chips}</div>{obs_html}{note}", aside=sig)


def _growth(r: AnalysisReport) -> str:
    g = r.growth_outlook
    if not g or not g.drivers:
        return ""
    engine = f"<p class=\"lead\">{escape(g.primary_engine)}</p>" if g.primary_engine else ""
    drivers = ""
    for d in g.drivers:
        share = d.contribution_pct or 0
        risks = f"<span class=\"muted small\">{escape(', '.join(d.risks[:2]))}</span>" if d.risks else ""
        drivers += (
            f"<div class=\"driver\"><div class=\"drow\"><span class=\"dname\">{escape(d.name)}</span>"
            f"<span class=\"num\">{share:.0%}</span></div>"
            f"<div class=\"track\"><span style=\"width:{share * 100:.0f}%\"></span></div>{risks}</div>")
    catalysts = ""
    if g.catalysts:
        items = "".join(
            f"<li><span class=\"yr\">{c.year or ''}</span>{escape(c.event)}</li>"
            for c in g.catalysts if c.event)
        catalysts = f"<div class=\"timeline\"><h4>Catalysts</h4><ul>{items}</ul></div>"
    band = ""
    if g.blended_5y_low is not None and g.blended_5y_high is not None:
        band = f"<span class=\"tag\">{g.blended_5y_low:.0%}–{g.blended_5y_high:.0%} blended</span>"
    sig = ""
    if g.growth_signal:
        sig = f"<span class=\"pill {_SIGNAL_CLASS.get(g.growth_signal, 'muted')}\">" \
              f"{g.growth_signal}</span>{band}"
    return _card("Growth engine — next 5 years",
                 f"{engine}<div class=\"drivers\">{drivers}</div>{catalysts}", aside=sig)


def _trend(r: AnalysisReport) -> str:
    ft = r.fundamental_trend
    if not ft or not ft.metrics:
        return ""
    rows = ""
    for m in ft.metrics:
        arrows = "".join(
            f"<span class=\"arr {d}\">{_ARROW.get(d, '·')}</span>" for d in m.directions)
        cagr = f"{m.cagr:+.1%}" if m.cagr is not None else "—"
        cls = _SIGNAL_CLASS.get(m.health or "", "muted")
        rows += (f"<tr><td>{escape(m.name)}</td><td class=\"arrows\">{arrows}</td>"
                 f"<td><span class=\"pill {cls}\">{escape(m.health or '')}</span></td>"
                 f"<td class=\"num\">{cagr}</td></tr>")
    head = "<thead><tr><th>Metric</th><th>Trend</th><th>Health</th>" \
           "<th class=\"num\">CAGR</th></tr></thead>"
    title = "Fundamentals trend"
    if ft.overall_health:
        title += f" — {escape(ft.overall_health)}"
    return _card(title, f"<table class=\"grid\">{head}<tbody>{rows}</tbody></table>")


def _red_flags(r: AnalysisReport) -> str:
    rf = r.red_flags
    if not rf:
        return ""
    if not rf.flags:
        body = "<p class=\"good\">✓ No material red flags detected.</p>"
    else:
        items = "".join(
            f"<li><span class=\"pill {_RISK_CLASS.get(f.severity, 'muted')}\">{f.severity}</span>"
            f"<span>{escape(f.issue)} — <span class=\"muted\">{escape(f.detail or '')}</span></span></li>"
            for f in rf.flags)
        body = f"<ul class=\"flags\">{items}</ul>"
    cls = _RISK_CLASS.get(str(rf.risk_level), "muted")
    aside = f"<span class=\"pill {cls}\">risk: {rf.risk_level}</span>"
    return _card("Red flags", body, aside=aside)


def _quality(r: AnalysisReport) -> str:
    em = r.evidence
    if not em or not em.confidence:
        return ""
    stats = [
        f"<span class=\"fact\"><em>Confidence</em>{em.confidence.score:.0%} {em.confidence.tier}</span>",
    ]
    if em.data_coverage is not None:
        stats.append(f"<span class=\"fact\"><em>Coverage</em>{em.data_coverage:.0%}</span>")
    stats.append(f"<span class=\"fact\"><em>Sources</em>{em.source_count}</span>")
    if em.as_of:
        stats.append(f"<span class=\"fact\"><em>As of</em>{escape(em.as_of)}</span>")
    missing = ""
    if em.missing_fields:
        missing = f"<p class=\"muted small\">Missing: {escape(', '.join(em.missing_fields))}</p>"
    return _card("Analysis quality", f"<div class=\"facts\">{''.join(stats)}</div>{missing}")


# --------------------------------------------------------------------------------------
# Building blocks
# --------------------------------------------------------------------------------------
def _card(title: str, body: str, *, aside: str = "") -> str:
    aside_html = f"<div class=\"card-aside\">{aside}</div>" if aside else ""
    return (f"<section class=\"card\"><div class=\"card-head\"><h3>{title}</h3>{aside_html}</div>"
            f"<div class=\"card-body\">{body}</div></section>")


def _tile(label: str, value: str, unit: str, sub: str | None, cls: str) -> str:
    unit_html = f"<span class=\"unit\">{unit}</span>" if unit else ""
    sub_html = f"<span class=\"tsub\">{escape(sub)}</span>" if sub else ""
    return (f"<div class=\"tile {cls}\"><span class=\"tlabel\">{escape(label)}</span>"
            f"<span class=\"tval\">{escape(value)}{unit_html}</span>{sub_html}</div>")


def _bar(normalized: float) -> str:
    pct = max(0, min(100, round(normalized * 100)))
    return f"<span class=\"track\"><span style=\"width:{pct}%\"></span></span>"


def _meter(score: float, tier: str) -> str:
    pct = max(0, min(100, round(score * 100)))
    return (f"<div class=\"meter\"><span class=\"mlabel\">confidence {pct}% · {escape(tier)}</span>"
            f"<span class=\"track\"><span style=\"width:{pct}%\"></span></span></div>")


def _mini_meter(score: float) -> str:
    pct = max(0, min(100, round(score * 100)))
    return f"<span class=\"track mini\"><span style=\"width:{pct}%\"></span></span>" \
           f"<span class=\"small muted\"> {pct}%</span>"


def _band_pill(percentile: float | None, better: bool | None) -> str:
    if percentile is None:
        return "<span class=\"muted\">—</span>"
    if percentile >= 0.75:
        label, cls = "top quartile", "good"
    elif percentile >= 0.5:
        label, cls = "above median", "good"
    elif percentile >= 0.25:
        label, cls = "below median", "warn"
    else:
        label, cls = "bottom quartile", "bad"
    return f"<span class=\"pill {cls}\">{label}</span>"


def _score_class(total: float) -> str:
    if total >= 65:
        return "good"
    if total >= 45:
        return "warn"
    return "bad"


def _metric(unit: str, value: float | None) -> str:
    """Format from the metric's declared unit; guessing by name mis-renders new ratios."""
    if value is None:
        return "—"
    return f"{value:.1f}x" if unit == "ratio" else f"{value:.1%}"


def _money(value: float | None, currency: str | None) -> str:
    if value is None:
        return "—"
    cur = (currency or "").upper()
    if cur == "INR":
        return f"₹{value / 1e7:,.0f} Cr"
    if abs(value) >= 1e9:
        return f"{value / 1e9:,.1f}B {cur}".strip()
    return f"{value:,.0f} {cur}".strip()


def _num(value: float | None) -> str:
    return f"{value:,.0f}" if value is not None else "—"


# --------------------------------------------------------------------------------------
# Styles — token-based, theme-aware, self-contained
# --------------------------------------------------------------------------------------
_CSS = """
:root{
  --ground:#f5f7f6; --surface:#ffffff; --ink:#19222a; --muted:#5c6873; --hair:#e3e8e6;
  --accent:#0e7c86; --good:#1a7f5a; --warn:#b07d19; --bad:#c0392b;
  --good-bg:#e7f3ec; --warn-bg:#f6efdd; --bad-bg:#f7e7e4; --muted-bg:#eef1f0;
  --serif:Iowan Old Style,"Palatino Linotype",Palatino,Georgia,serif;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --mono:ui-monospace,"SF Mono","Cascadia Code",Consolas,monospace;
}
@media (prefers-color-scheme:dark){:root{
  --ground:#0e1418; --surface:#161f26; --ink:#e7edea; --muted:#93a1a9; --hair:#26333b;
  --accent:#42b7c1; --good:#4bbd8a; --warn:#d5a531; --bad:#e07a6c;
  --good-bg:#12281f; --warn-bg:#2a2413; --bad-bg:#2c1a17; --muted-bg:#1b252c;
}}
:root[data-theme="light"]{
  --ground:#f5f7f6; --surface:#ffffff; --ink:#19222a; --muted:#5c6873; --hair:#e3e8e6;
  --accent:#0e7c86; --good:#1a7f5a; --warn:#b07d19; --bad:#c0392b;
  --good-bg:#e7f3ec; --warn-bg:#f6efdd; --bad-bg:#f7e7e4; --muted-bg:#eef1f0;
}
:root[data-theme="dark"]{
  --ground:#0e1418; --surface:#161f26; --ink:#e7edea; --muted:#93a1a9; --hair:#26333b;
  --accent:#42b7c1; --good:#4bbd8a; --warn:#d5a531; --bad:#e07a6c;
  --good-bg:#12281f; --warn-bg:#2a2413; --bad-bg:#2c1a17; --muted-bg:#1b252c;
}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);font-family:var(--sans);
  line-height:1.5;-webkit-font-smoothing:antialiased}
.page{max-width:900px;margin:0 auto;padding:32px 20px 48px;display:flex;flex-direction:column;gap:18px}
.num,.tval,.yr{font-variant-numeric:tabular-nums;font-family:var(--mono)}
h1,h3,h4{text-wrap:balance;margin:0}
.eyebrow{font-family:var(--sans);text-transform:uppercase;letter-spacing:.14em;font-size:11px;
  font-weight:600;color:var(--accent)}
.masthead{border-bottom:2px solid var(--ink);padding-bottom:16px}
.mast-top{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
.masthead h1{font-family:var(--serif);font-size:34px;font-weight:600;line-height:1.1;margin:.3em 0 .1em}
.masthead .ticker{font-family:var(--mono);font-size:16px;color:var(--muted);font-weight:500}
.sub{color:var(--muted);margin:0 0 12px;font-size:14px}
.facts{display:flex;flex-wrap:wrap;gap:8px 20px}
.fact{display:flex;flex-direction:column;font-size:14px;font-variant-numeric:tabular-nums}
.fact em{font-style:normal;text-transform:uppercase;letter-spacing:.08em;font-size:10px;color:var(--muted)}
.verdict{font-size:13px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px}
.tile{background:var(--surface);border:1px solid var(--hair);border-radius:10px;padding:12px 14px;
  display:flex;flex-direction:column;gap:2px;border-top:3px solid var(--muted)}
.tile.good{border-top-color:var(--good)} .tile.warn{border-top-color:var(--warn)}
.tile.bad{border-top-color:var(--bad)} .tile.muted{border-top-color:var(--muted)}
.tlabel{text-transform:uppercase;letter-spacing:.09em;font-size:10px;color:var(--muted);font-weight:600}
.tval{font-size:26px;font-weight:600;line-height:1.1}
.tval .unit{font-size:13px;color:var(--muted);margin-left:1px}
.tsub{font-size:12px;color:var(--muted)}
.card{background:var(--surface);border:1px solid var(--hair);border-radius:12px;padding:18px 20px}
.card-head{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:12px;
  flex-wrap:wrap}
.card-head h3{font-family:var(--serif);font-size:18px;font-weight:600}
.card-body{font-size:14px}
.lead{font-size:15px;margin:0 0 12px;color:var(--ink)}
.proscons{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.proscons h4{font-size:11px;text-transform:uppercase;letter-spacing:.1em;margin-bottom:6px}
.pros h4{color:var(--good)} .cons h4{color:var(--bad)}
.proscons ul{margin:0;padding-left:18px;display:flex;flex-direction:column;gap:5px}
table.grid{width:100%;border-collapse:collapse;font-size:13.5px}
table.grid th{text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:.08em;
  color:var(--muted);font-weight:600;padding:0 8px 6px;border-bottom:1px solid var(--hair)}
table.grid td{padding:7px 8px;border-bottom:1px solid var(--hair);vertical-align:middle}
table.grid tr:last-child td{border-bottom:none}
.num{text-align:right;white-space:nowrap} th.num{text-align:right}
.small{font-size:12px} .muted{color:var(--muted)}
.barcell{width:38%}
.track{display:inline-block;width:100%;min-width:60px;height:7px;background:var(--muted-bg);
  border-radius:99px;overflow:hidden;vertical-align:middle}
.track>span{display:block;height:100%;background:var(--accent);border-radius:99px}
.track.mini{width:52px;min-width:52px}
.pill{display:inline-block;padding:2px 9px;border-radius:99px;font-size:11px;font-weight:600;
  text-transform:capitalize;white-space:nowrap}
.pill.good{background:var(--good-bg);color:var(--good)} .pill.warn{background:var(--warn-bg);color:var(--warn)}
.pill.bad{background:var(--bad-bg);color:var(--bad)} .pill.muted{background:var(--muted-bg);color:var(--muted)}
.tag{display:inline-block;margin-left:8px;font-size:11px;color:var(--muted);border:1px solid var(--hair);
  border-radius:99px;padding:1px 8px}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px}
.chip{display:flex;flex-direction:column;background:var(--muted-bg);border-radius:8px;padding:6px 12px;
  font-variant-numeric:tabular-nums;font-weight:600;font-family:var(--mono)}
.chip em{font-style:normal;font-family:var(--sans);text-transform:uppercase;letter-spacing:.07em;
  font-size:9px;color:var(--muted);font-weight:600}
.obs,.flags{margin:0;padding-left:18px;display:flex;flex-direction:column;gap:5px}
.flags{list-style:none;padding:0}
.flags li{display:flex;gap:10px;align-items:baseline}
.drivers{display:flex;flex-direction:column;gap:12px}
.driver .drow{display:flex;justify-content:space-between;font-weight:600;margin-bottom:4px}
.driver .track{height:9px}
.timeline{margin-top:16px} .timeline h4{font-size:11px;text-transform:uppercase;letter-spacing:.1em;
  color:var(--muted);margin-bottom:6px}
.timeline ul{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:6px}
.timeline li{display:flex;gap:12px;align-items:baseline;font-size:13.5px;
  border-left:2px solid var(--accent);padding-left:12px}
.timeline .yr{color:var(--accent);font-weight:600;min-width:44px}
.arrows{letter-spacing:2px} .arr.up{color:var(--good)} .arr.down{color:var(--bad)} .arr.flat{color:var(--muted)}
.meter{display:flex;flex-direction:column;gap:3px;min-width:150px}
.mlabel{font-size:10px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted)}
.disclaimer{text-align:center;color:var(--muted);font-size:12px;margin-top:8px}
@media (max-width:560px){.proscons{grid-template-columns:1fr}.masthead h1{font-size:27px}}
@media print{body{background:#fff}.card,.tile{border-color:#ccc}}
"""
