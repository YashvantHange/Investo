"""The stylesheet, as one constant.

Deliberately a Python string rather than a ``.css`` file: any non-``.py`` asset needs its own
``force-include`` entry in pyproject to reach the wheel, and a stylesheet that silently fails to
ship is a worse problem than a long string literal.

The design is a modern equity-research note: a clean sans face, a masthead with a rating block, a
row of KPI cards, coloured status badges and card-framed data. Everything is driven by design
tokens declared once in ``:root`` — a spacing scale, radii, shadows and a semantic status palette
— so spacing stays consistent, colour is never hardcoded at a call site, and light/dark/print are
decided in one place. Colour is used purposefully (status, polarity, the subject of an exhibit),
never decoratively.

Three themes are declared: light (default), an OS dark-mode override, and explicit ``data-theme``
scopes so a host's theme toggle wins in both directions. Print forces light — a dark-mode host
would otherwise emit a PDF with a black page — and keeps the badge/card fills via
``print-color-adjust:exact``.

Self-contained by construction: inline only, system fonts, no web fonts, no external assets, no
script. That is what lets the headless-Chrome PDF path render with nothing to fetch.
"""

from __future__ import annotations

CSS = """
:root{
  color-scheme:light;
  /* surfaces */
  --paper:#ffffff; --plane:#eef1f6; --surface:#f6f8fb; --surface-2:#eef2f7;
  /* ink */
  --ink:#101828; --ink-2:#475467; --ink-3:#8792a3;
  /* rules */
  --rule:#e6e9ef; --rule-strong:#cdd3dd;
  /* brand + semantic status */
  --accent:#2f6bff; --accent-ink:#1b4fd6;
  --success:#12805c; --success-bg:#e5f4ee;
  --warn:#9a6a00; --warn-bg:#fbf1d9;
  --danger:#c5342c; --danger-bg:#fbe8e6;
  --info:#2f6bff; --info-bg:#e7efff;
  --neutral:#54607a; --neutral-bg:#eceff5;
  /* data-viz */
  --pos:#2f6bff; --neg:#c5342c; --track:#d6e2ff; --mid:#eceff5;
  --good:#12805c; --serious:#9a6a00; --critical:#c5342c;
  /* type */
  --sans:"Segoe UI",system-ui,-apple-system,Roboto,Helvetica,Arial,sans-serif;
  --serif:"Iowan Old Style","Palatino Linotype",Palatino,"Book Antiqua",Georgia,serif;
  --measure:66ch;
  /* spacing scale */
  --space-1:4px; --space-2:8px; --space-3:12px; --space-4:16px; --space-5:24px; --space-6:32px;
  /* radii + shadow */
  --radius:12px; --radius-sm:8px; --radius-pill:999px;
  --shadow:0 1px 2px rgba(16,24,40,.06),0 10px 28px rgba(16,24,40,.06);
  --shadow-sm:0 1px 2px rgba(16,24,40,.09);
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    color-scheme:dark;
    --paper:#161b22; --plane:#0b0d11; --surface:#1b212b; --surface-2:#232b36;
    --ink:#f2f5fa; --ink-2:#c2cad6; --ink-3:#8792a3;
    --rule:#28303b; --rule-strong:#3a434f;
    --accent:#5b8bff; --accent-ink:#8cacff;
    --success:#3ecf8e; --success-bg:#123a2b;
    --warn:#e0b64a; --warn-bg:#3a2f13;
    --danger:#f0776e; --danger-bg:#3a1d1b;
    --info:#5b8bff; --info-bg:#182642;
    --neutral:#aab4c4; --neutral-bg:#232b36;
    --pos:#5b8bff; --neg:#f0776e; --track:#243a63; --mid:#232b36;
    --good:#3ecf8e; --serious:#e0b64a; --critical:#f0776e;
    --shadow:0 1px 2px rgba(0,0,0,.45),0 10px 28px rgba(0,0,0,.4);
    --shadow-sm:0 1px 2px rgba(0,0,0,.5);
  }
}
:root[data-theme="dark"]{
  color-scheme:dark;
  --paper:#161b22; --plane:#0b0d11; --surface:#1b212b; --surface-2:#232b36;
  --ink:#f2f5fa; --ink-2:#c2cad6; --ink-3:#8792a3;
  --rule:#28303b; --rule-strong:#3a434f;
  --accent:#5b8bff; --accent-ink:#8cacff;
  --success:#3ecf8e; --success-bg:#123a2b;
  --warn:#e0b64a; --warn-bg:#3a2f13;
  --danger:#f0776e; --danger-bg:#3a1d1b;
  --info:#5b8bff; --info-bg:#182642;
  --neutral:#aab4c4; --neutral-bg:#232b36;
  --pos:#5b8bff; --neg:#f0776e; --track:#243a63; --mid:#232b36;
  --good:#3ecf8e; --serious:#e0b64a; --critical:#f0776e;
  --shadow:0 1px 2px rgba(0,0,0,.45),0 10px 28px rgba(0,0,0,.4);
  --shadow-sm:0 1px 2px rgba(0,0,0,.5);
}

*{box-sizing:border-box}
body{
  margin:0;background:var(--plane);color:var(--ink);
  font-family:var(--sans);font-size:15px;line-height:1.55;
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;
}
.vh{position:absolute!important;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;
  clip:rect(0 0 0 0);white-space:nowrap;border:0}
.paper{
  max-width:210mm;margin:24px auto;padding:var(--space-6) var(--space-6) var(--space-5);
  background:var(--paper);border-radius:var(--radius);box-shadow:var(--shadow);
}

/* ---------- Status badges (one component, semantic colour) ---------- */
.badge,.st{
  display:inline-block;font-family:var(--sans);font-size:11px;font-weight:650;
  letter-spacing:.01em;line-height:1.4;padding:2px 9px;border-radius:var(--radius-pill);
  border:1px solid transparent;white-space:nowrap;vertical-align:baseline;
}
.badge.success,.st.pass,.st.good,.st.pos,.st.pos-weak{color:var(--success);
  background:var(--success-bg);border-color:color-mix(in srgb,var(--success) 22%,transparent)}
.badge.warn,.st.warn,.st.neg-weak{color:var(--warn);background:var(--warn-bg);
  border-color:color-mix(in srgb,var(--warn) 22%,transparent)}
.badge.danger,.st.fail,.st.bad,.st.neg{color:var(--danger);background:var(--danger-bg);
  border-color:color-mix(in srgb,var(--danger) 22%,transparent)}
.badge.info{color:var(--accent-ink);background:var(--info-bg);
  border-color:color-mix(in srgb,var(--accent) 22%,transparent)}
.badge.neutral,.st.unknown,.st.flat{color:var(--neutral);background:var(--neutral-bg);
  border-color:color-mix(in srgb,var(--neutral) 18%,transparent)}
.delta.pos{color:var(--good);font-weight:600} .delta.neg{color:var(--critical);font-weight:600}

/* ---------- Masthead: name, sector line, and a rating block ---------- */
.masthead{margin-bottom:var(--space-5)}
.mast-top{
  display:flex;justify-content:space-between;align-items:center;gap:var(--space-4);
  padding-bottom:var(--space-3);border-bottom:2px solid var(--ink);margin-bottom:var(--space-4);
}
.brand{font-weight:750;font-size:12px;letter-spacing:.02em;color:var(--accent-ink)}
.mast-date{font-size:12px;color:var(--ink-3)}
.mast-main{display:flex;justify-content:space-between;align-items:flex-start;gap:var(--space-5)}
.mast-id{min-width:0}
.masthead h1{
  font-family:var(--serif);font-size:30px;font-weight:600;line-height:1.1;
  margin:0 0 var(--space-1);letter-spacing:-.01em;text-wrap:balance;
}
.masthead .ticker{font-family:var(--sans);font-size:15px;font-weight:600;color:var(--ink-3);
  margin-left:8px;letter-spacing:.01em}
.masthead .sectors{font-size:13px;color:var(--ink-2);margin:0}
.masthead .standfirst{
  font-size:15px;color:var(--ink-2);margin:var(--space-3) 0 0;max-width:var(--measure);
}
.rating-block{
  flex:0 0 auto;text-align:center;min-width:120px;padding:var(--space-3) var(--space-4);
  border-radius:var(--radius);background:var(--surface);border:1px solid var(--rule);
  box-shadow:var(--shadow-sm);
}
.rating-block.success{background:var(--success-bg);border-color:color-mix(in srgb,var(--success) 30%,transparent)}
.rating-block.info{background:var(--info-bg);border-color:color-mix(in srgb,var(--accent) 30%,transparent)}
.rating-block.warn{background:var(--warn-bg);border-color:color-mix(in srgb,var(--warn) 30%,transparent)}
.rating-block.danger{background:var(--danger-bg);border-color:color-mix(in srgb,var(--danger) 30%,transparent)}
.rating-block .rk{font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;
  color:var(--ink-3);margin-bottom:2px}
.rating-score{font-size:36px;font-weight:750;line-height:1;font-variant-numeric:tabular-nums;color:var(--ink)}
.rating-score .out{font-size:15px;font-weight:600;color:var(--ink-3)}
.rating-verdict{font-size:12px;font-weight:600;color:var(--ink-2);margin-top:var(--space-2);max-width:150px}

/* ---------- KPI cards ---------- */
.kpis{
  display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));
  gap:var(--space-3);margin:var(--space-4) 0;
}
.kpi{
  background:var(--surface);border:1px solid var(--rule);border-radius:var(--radius-sm);
  padding:var(--space-3) var(--space-3) var(--space-3);box-shadow:var(--shadow-sm);
}
.kpi-label{font-size:10.5px;font-weight:650;letter-spacing:.05em;text-transform:uppercase;
  color:var(--ink-3);margin-bottom:var(--space-1)}
.kpi-value{font-size:20px;font-weight:700;font-variant-numeric:tabular-nums;color:var(--ink);line-height:1.15}
.kpi-value .kpi-unit{font-size:13px;font-weight:600;color:var(--ink-3)}
.kpi-sub{margin-top:var(--space-2)}

/* ---------- Key-data facts strip ---------- */
.keydata{
  display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:var(--space-2);
  margin:var(--space-4) 0;
}
.kd{padding:var(--space-2) var(--space-3);background:var(--surface-2);border-radius:var(--radius-sm)}
.kd dt{font-size:10px;font-weight:650;letter-spacing:.05em;text-transform:uppercase;
  color:var(--ink-3);margin:0 0 2px}
.kd dd{margin:0;font-size:15px;font-weight:650;font-variant-numeric:tabular-nums;color:var(--ink)}

/* ---------- Table of contents ---------- */
.toc{
  margin:var(--space-4) 0 var(--space-5);padding:var(--space-3) var(--space-4);
  background:var(--surface);border:1px solid var(--rule);border-radius:var(--radius-sm);
}
.toc-h{font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;
  color:var(--ink-3);margin-bottom:var(--space-2)}
.toc ol{list-style:none;margin:0;padding:0;
  display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:2px var(--space-4)}
.toc a{display:flex;gap:var(--space-2);align-items:baseline;text-decoration:none;color:var(--ink-2);
  font-size:13px;padding:2px 0}
.toc a:hover{color:var(--accent-ink)}
.toc .toc-n{font-weight:700;color:var(--accent);font-variant-numeric:tabular-nums;min-width:16px}

/* ---------- Sections ---------- */
.sec{margin:0 0 var(--space-5);break-inside:auto}
.sec > h2{
  font-family:var(--sans);font-size:18px;font-weight:700;margin:0 0 var(--space-3);
  padding-bottom:var(--space-2);border-bottom:1px solid var(--rule-strong);
  display:flex;align-items:baseline;gap:var(--space-2);
  break-after:avoid;page-break-after:avoid;
}
.sec > h2 .n{
  font-family:var(--sans);font-size:12px;font-weight:750;color:#fff;background:var(--accent);
  border-radius:var(--radius-sm);padding:1px 7px;font-variant-numeric:tabular-nums;
}
.sec > h2 .h2note{
  margin-left:auto;font-size:12px;font-weight:600;color:var(--ink-3);letter-spacing:.01em;
}
.sec p{margin:0 0 var(--space-3);max-width:var(--measure)}
.lede{font-size:16px;color:var(--ink)}
.muted{color:var(--ink-3)}
.small{font-size:12.5px}

/* ---------- Exhibits ---------- */
.exhibit{margin:var(--space-3) 0 var(--space-4);break-inside:avoid;page-break-inside:avoid}
.exhibit .cap{
  font-family:var(--sans);font-size:11px;font-weight:650;letter-spacing:.03em;
  text-transform:uppercase;color:var(--ink-2);margin-bottom:var(--space-2);
}
.exhibit .cap .lbl{color:var(--accent-ink);margin-right:6px}
.exhibit .src{
  font-family:var(--sans);font-size:11px;color:var(--ink-3);margin-top:var(--space-2);
  line-height:1.45;padding-top:var(--space-2);border-top:1px solid var(--rule);
}
svg.viz{width:100%;height:auto;display:block;overflow:visible}
svg.viz.spark{width:120px;height:28px;display:inline-block;vertical-align:middle}
.vt{font-family:var(--sans);font-size:11px;fill:var(--ink-2)}
.vnum{font-variant-numeric:tabular-nums;fill:var(--ink)}
.vtick{font-size:10px;fill:var(--ink-3);font-variant-numeric:tabular-nums}
.vmuted{fill:var(--ink-3);font-size:10px}
.vlabel{font-size:11px;fill:var(--ink-2)}
.vlabel.strong{fill:var(--ink);font-weight:650}
.vbar{fill:var(--accent)}
.vbar.pos{fill:var(--pos)} .vbar.neg{fill:var(--neg)} .vbar.muted{fill:var(--rule-strong)}
.vtrack{fill:var(--track);opacity:.55}
.vgrid{stroke:var(--rule);stroke-width:1}
.vaxis{stroke:var(--rule-strong);stroke-width:1}
.vline{fill:none;stroke:var(--accent);stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.vdot{fill:var(--accent);stroke:var(--paper);stroke-width:2}
.vdot.peer{fill:var(--ink-3)}
.vdot.subject{fill:var(--accent)}

/* ---------- Tables ---------- */
.table-wrap{overflow-x:auto;margin:var(--space-3) 0}
table.data{
  width:100%;border-collapse:collapse;font-family:var(--sans);font-size:13px;
  border:1px solid var(--rule);border-radius:var(--radius-sm);overflow:hidden;break-inside:auto;
}
table.data thead th{
  font-size:10.5px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;
  color:var(--ink-2);text-align:left;padding:var(--space-2) var(--space-3);
  background:var(--surface-2);border-bottom:1px solid var(--rule-strong);white-space:nowrap;
}
table.data td{padding:8px var(--space-3);border-bottom:1px solid var(--rule);vertical-align:top}
table.data tbody tr:nth-child(even) td{background:color-mix(in srgb,var(--surface) 55%,transparent)}
table.data tbody tr:last-child td{border-bottom:none}
table.data tr{break-inside:avoid;page-break-inside:avoid}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
th.num{text-align:right}
td.name{font-weight:600;color:var(--ink)}
.reason{color:var(--ink-2);font-size:12.5px;line-height:1.45}
.trend-seq{font-family:var(--sans);letter-spacing:.1em;font-size:13px}
.up{color:var(--good)} .down{color:var(--critical)} .flat{color:var(--ink-3)}

/* ---------- Pros/cons + SWOT: two columns ---------- */
.twocol{display:grid;grid-template-columns:1fr 1fr;gap:var(--space-4);margin:var(--space-3) 0}
.twocol > div{padding:var(--space-3) var(--space-4);background:var(--surface);
  border:1px solid var(--rule);border-radius:var(--radius-sm)}
.twocol h3{
  font-family:var(--sans);font-size:11px;font-weight:700;letter-spacing:.05em;
  text-transform:uppercase;margin:0 0 var(--space-2);color:var(--ink-2);
}
.twocol ul{margin:0;padding-left:16px;font-size:13.5px}
.twocol li{margin-bottom:var(--space-2);padding-left:2px}

ul.plain{margin:0 0 var(--space-3);padding-left:18px;font-size:14px;max-width:var(--measure)}
ul.plain li{margin-bottom:var(--space-2)}
dl.defs{margin:var(--space-3) 0;font-size:14px}
dl.defs dt{font-family:var(--sans);font-size:11px;font-weight:700;letter-spacing:.04em;
  text-transform:uppercase;color:var(--ink-3);margin-top:var(--space-3)}
dl.defs dd{margin:2px 0 0}

/* ---------- Catalyst timeline ---------- */
.timeline{list-style:none;margin:var(--space-3) 0;padding:0;font-size:14px}
.timeline li{display:flex;gap:var(--space-3);padding:var(--space-2) 0;border-bottom:1px solid var(--rule)}
.timeline li:last-child{border-bottom:none}
.timeline .yr{font-family:var(--sans);font-weight:700;font-size:12px;color:var(--accent);
  min-width:44px;font-variant-numeric:tabular-nums}

/* ---------- Footnotes, disclaimer, colophon, running furniture ---------- */
.footnotes{
  margin-top:var(--space-5);padding-top:var(--space-3);border-top:1px solid var(--rule-strong);
  font-size:12px;color:var(--ink-2);
}
.footnotes ol{margin:0;padding-left:18px}
.footnotes li{margin-bottom:var(--space-2)}
sup.fn{font-size:9px;font-weight:700;color:var(--accent);vertical-align:super;
  font-family:var(--sans);margin-left:1px}
.disclaimer{
  margin-top:var(--space-4);padding:var(--space-3) var(--space-4);border-radius:var(--radius-sm);
  background:var(--surface-2);font-size:11.5px;color:var(--ink-2);line-height:1.5;
}
.colophon{margin-top:var(--space-3);font-size:11px;color:var(--ink-3);text-align:center}
/* Print-pagination scaffold: a single-column table whose header/footer groups repeat on every
   printed page. The groups are hidden on screen, so the table is invisible layout scaffolding. */
table.page{width:100%;border-collapse:collapse;border:0}
table.page > tbody > tr > td,table.page > thead > tr > td,table.page > tfoot > tr > td{
  padding:0;border:0}
.page-head,.page-foot{display:none}
.runhead,.runfoot{font-family:var(--sans);font-size:8pt;color:var(--ink-3)}
.runhead .r,.runfoot .r{float:right}

/* ---------- Print ---------- */
@page{size:A4;margin:14mm 14mm}
@media print{
  /* Force light: a dark-mode host would otherwise print a black page. */
  :root{
    color-scheme:light !important;
    --paper:#ffffff; --plane:#ffffff; --surface:#f6f8fb; --surface-2:#eef2f7;
    --ink:#0b1220; --ink-2:#3a4453; --ink-3:#6b7480;
    --rule:#dfe3ea; --rule-strong:#b7bec9;
    --accent:#1c56d6; --accent-ink:#164bbe;
    --success:#0e6f50; --success-bg:#e5f4ee;
    --warn:#8a5e00; --warn-bg:#fbf1d9;
    --danger:#b32c26; --danger-bg:#fbe8e6;
    --info:#1c56d6; --info-bg:#e7efff;
    --neutral:#4a5568; --neutral-bg:#eceff5;
    --pos:#1c56d6; --neg:#b32c26; --mid:#eceff5; --track:#d6e2ff;
    --good:#0e6f50; --serious:#8a5e00; --critical:#b32c26;
  }
  body{background:#fff;font-size:10.5pt}
  .paper{max-width:none;margin:0;padding:0;box-shadow:none;border-radius:0;min-height:0}
  /* Keep card/badge fills and header rules in the PDF. */
  .badge,.st,.kpi,.kd,.rating-block,.twocol > div,.toc,.disclaimer,
  table.data thead th,table.data tbody tr:nth-child(even) td,.sec > h2 .n{
    -webkit-print-color-adjust:exact;print-color-adjust:exact;
  }
  .toc{break-after:page}
  /* Running furniture: the header/footer groups repeat on every page; the browser reserves
     their height, so the body never collides with them. */
  .page-head{display:table-header-group}
  .page-foot{display:table-footer-group}
  .runhead{border-bottom:.5pt solid var(--rule);padding-bottom:2mm;margin-bottom:7mm}
  .runfoot{border-top:.5pt solid var(--rule);padding-top:2mm;margin-top:7mm}
  /* Breaks: keep headings with content, don't split exhibits/cards/rows, repeat table heads. */
  .sec{break-inside:auto}
  .sec > h2{break-after:avoid}
  .masthead,.mast-main,.rating-block,.kpis,.kpi,.exhibit,.twocol,.table-wrap,
  table.data tr{break-inside:avoid}
  table.data thead{display:table-header-group}
  .table-wrap{overflow:visible}
  p,li{orphans:2;widows:2}
  a{text-decoration:none;color:inherit}
}
@media (max-width:640px){
  .paper{margin:0;border-radius:0;padding:var(--space-4)}
  .mast-main{flex-direction:column}
  .rating-block{align-self:flex-start}
  .twocol{grid-template-columns:1fr}
  .toc ol{grid-template-columns:1fr}
  .masthead h1{font-size:24px}
}
"""
