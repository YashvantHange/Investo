"""The stylesheet, as one constant.

Deliberately a Python string rather than a ``.css`` file: any non-``.py`` asset needs its own
``force-include`` entry in pyproject to reach the wheel, and a stylesheet that silently fails to
ship is a worse problem than a long string literal.

The design is an institutional equity-research note, not a web dashboard. The distinction is not
cosmetic — rounded cards, KPI tiles, coloured status pills and emoji ticks are the visual grammar
of a generated artifact, and a reader clocks them instantly. This document uses the grammar of
print instead: numbered sections, a serif text face at a readable measure, rules rather than
boxes, exhibit captions with source lines, tabular figures, and status carried by typography
rather than by a coloured lozenge.

Colour is scoped to the exhibits, where it encodes data. Chrome and prose stay in ink.

Three themes are declared: light (default), an OS dark-mode override, and explicit
``data-theme`` scopes so a host's theme toggle wins in both directions. Print forces light — a
dark-mode host would otherwise emit a PDF with a black page.
"""

from __future__ import annotations

CSS = """
:root{
  color-scheme:light;
  --paper:#ffffff; --plane:#f7f7f5;
  --ink:#0b0b0b; --ink-2:#52514e; --ink-3:#898781;
  --rule:#e1e0d9; --rule-strong:#c3c2b7;
  --accent:#2a78d6;
  --pos:#2a78d6; --neg:#d03b3b; --mid:#f0efec;
  --track:#cde2fb;
  --good:#0ca30c; --warn:#fab219; --serious:#ec835a; --critical:#d03b3b;
  --serif:"Iowan Old Style","Palatino Linotype",Palatino,"Book Antiqua",Georgia,serif;
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --measure:34em;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    color-scheme:dark;
    --paper:#17191b; --plane:#0d0d0d;
    --ink:#ffffff; --ink-2:#c3c2b7; --ink-3:#898781;
    --rule:#2c2c2a; --rule-strong:#383835;
    --accent:#3987e5;
    --pos:#3987e5; --neg:#e66767; --mid:#383835;
    --track:#184f95;
  }
}
:root[data-theme="dark"]{
  color-scheme:dark;
  --paper:#17191b; --plane:#0d0d0d;
  --ink:#ffffff; --ink-2:#c3c2b7; --ink-3:#898781;
  --rule:#2c2c2a; --rule-strong:#383835;
  --accent:#3987e5;
  --pos:#3987e5; --neg:#e66767; --mid:#383835;
  --track:#184f95;
}

*{box-sizing:border-box}
body{
  margin:0;background:var(--plane);color:var(--ink);
  font-family:var(--serif);font-size:10.5pt;line-height:1.52;
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;
}
.paper{
  max-width:210mm;margin:0 auto;padding:22mm 18mm 18mm;background:var(--paper);
  min-height:100vh;
}

/* ---------- Masthead: the front-page block of a research note ---------- */
.masthead{border-bottom:1.5pt solid var(--ink);padding-bottom:10pt;margin-bottom:14pt}
.eyebrow{
  font-family:var(--sans);font-size:7.5pt;font-weight:650;letter-spacing:.18em;
  text-transform:uppercase;color:var(--ink-2);
  display:flex;justify-content:space-between;align-items:baseline;gap:12pt;
  border-bottom:.5pt solid var(--rule);padding-bottom:6pt;margin-bottom:10pt;
}
.masthead h1{
  font-family:var(--serif);font-size:23pt;font-weight:600;line-height:1.12;
  margin:0 0 2pt;letter-spacing:-.01em;text-wrap:balance;
}
.masthead .ticker{font-family:var(--sans);font-size:11pt;font-weight:500;color:var(--ink-3);
  letter-spacing:.02em;margin-left:6pt}
.masthead .standfirst{
  font-size:11pt;color:var(--ink-2);margin:4pt 0 0;max-width:var(--measure);font-style:italic;
}
.verdict-line{
  font-family:var(--sans);font-size:8pt;font-weight:650;letter-spacing:.1em;
  text-transform:uppercase;color:var(--accent);white-space:nowrap;
}

/* ---------- Key data: a rule-ruled strip, not a row of tiles ---------- */
.keydata{
  display:grid;grid-template-columns:repeat(auto-fit,minmax(96pt,1fr));
  gap:0;border-bottom:.5pt solid var(--rule);margin-bottom:16pt;
}
.kd{padding:7pt 10pt 8pt;border-left:.5pt solid var(--rule)}
.kd:first-child{border-left:none;padding-left:0}
.kd dt{
  font-family:var(--sans);font-size:7pt;font-weight:600;letter-spacing:.1em;
  text-transform:uppercase;color:var(--ink-3);margin:0 0 2pt;
}
.kd dd{margin:0;font-family:var(--sans);font-size:11pt;font-weight:600;
  font-variant-numeric:tabular-nums;color:var(--ink)}

/* ---------- Sections ---------- */
.sec{margin:0 0 15pt;break-inside:auto}
.sec > h2{
  font-family:var(--serif);font-size:12.5pt;font-weight:600;margin:0 0 7pt;
  padding-bottom:3pt;border-bottom:.5pt solid var(--rule-strong);
  break-after:avoid;page-break-after:avoid;
}
.sec > h2 .n{
  font-family:var(--sans);font-size:8pt;font-weight:700;color:var(--accent);
  margin-right:7pt;letter-spacing:.04em;
}
.sec > h2 .h2note{
  font-family:var(--sans);font-size:8pt;font-weight:500;color:var(--ink-3);
  float:right;letter-spacing:.03em;text-transform:none;
}
.sec p{margin:0 0 7pt;max-width:var(--measure)}
.lede{font-size:11pt;color:var(--ink)}
.muted{color:var(--ink-3)}
.small{font-size:8.5pt}

/* ---------- Exhibits ---------- */
.exhibit{margin:9pt 0 11pt;break-inside:avoid;page-break-inside:avoid}
.exhibit .cap{
  font-family:var(--sans);font-size:7.5pt;font-weight:650;letter-spacing:.09em;
  text-transform:uppercase;color:var(--ink-2);margin-bottom:5pt;
}
.exhibit .cap .lbl{color:var(--accent);margin-right:5pt}
.exhibit .src{
  font-family:var(--sans);font-size:7pt;color:var(--ink-3);margin-top:4pt;line-height:1.4;
  padding-top:3pt;border-top:.5pt solid var(--rule);
}
svg.viz{width:100%;height:auto;display:block;overflow:visible}
svg.viz.spark{width:120px;height:28px;display:inline-block;vertical-align:middle}
.vt{font-family:var(--sans);font-size:8.5px;fill:var(--ink-2)}
.vnum{font-variant-numeric:tabular-nums;fill:var(--ink)}
.vtick{font-size:7.5px;fill:var(--ink-3);font-variant-numeric:tabular-nums}
.vmuted{fill:var(--ink-3);font-size:7.5px}
.vlabel{font-size:8px;fill:var(--ink-2)}
.vlabel.strong{fill:var(--ink);font-weight:650}
.vbar{fill:var(--accent)}
.vbar.pos{fill:var(--pos)} .vbar.neg{fill:var(--neg)} .vbar.muted{fill:var(--rule-strong)}
.vtrack{fill:var(--track);opacity:.5}
.vgrid{stroke:var(--rule);stroke-width:1}
.vaxis{stroke:var(--rule-strong);stroke-width:1}
.vline{fill:none;stroke:var(--accent);stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.vdot{fill:var(--accent);stroke:var(--paper);stroke-width:2}
.vdot.peer{fill:var(--ink-3)}
.vdot.subject{fill:var(--accent)}

/* ---------- Tables: rules, tabular figures, no zebra ---------- */
table.data{
  width:100%;border-collapse:collapse;font-family:var(--sans);font-size:8.5pt;
  margin:6pt 0;break-inside:auto;
}
table.data thead th{
  font-size:7pt;font-weight:650;letter-spacing:.09em;text-transform:uppercase;
  color:var(--ink-3);text-align:left;padding:0 6pt 4pt;
  border-bottom:.75pt solid var(--rule-strong);white-space:nowrap;
}
table.data td{padding:4.5pt 6pt;border-bottom:.5pt solid var(--rule);vertical-align:top}
table.data tbody tr:last-child td{border-bottom:none}
table.data tr{break-inside:avoid;page-break-inside:avoid}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
th.num{text-align:right}
td.name{font-weight:550;color:var(--ink)}
.reason{color:var(--ink-2);font-size:8pt;line-height:1.4}

/* Status as typography, not as a coloured lozenge. */
.st{font-family:var(--sans);font-size:7.5pt;font-weight:700;letter-spacing:.06em;
  text-transform:uppercase;white-space:nowrap}
.st.pass,.st.good{color:var(--good)}
.st.warn{color:var(--serious)}
.st.fail,.st.bad{color:var(--critical)}
.st.unknown,.st.flat{color:var(--ink-3)}
.delta.pos{color:var(--good)} .delta.neg{color:var(--critical)}
.trend-seq{font-family:var(--sans);letter-spacing:.14em;font-size:9pt}
.up{color:var(--good)} .down{color:var(--critical)} .flat{color:var(--ink-3)}

/* ---------- Pros/cons: two columns, hairline between ---------- */
.twocol{display:grid;grid-template-columns:1fr 1fr;gap:0 18pt;margin:8pt 0}
.twocol > div{padding-left:12pt;border-left:.5pt solid var(--rule)}
.twocol > div:first-child{padding-left:0;border-left:none}
.twocol h3{
  font-family:var(--sans);font-size:7.5pt;font-weight:650;letter-spacing:.1em;
  text-transform:uppercase;margin:0 0 5pt;color:var(--ink-2);
}
.twocol ul{margin:0;padding-left:13pt;font-size:9.5pt}
.twocol li{margin-bottom:3.5pt;padding-left:2pt}

ul.plain{margin:0 0 7pt;padding-left:13pt;font-size:9.5pt;max-width:var(--measure)}
ul.plain li{margin-bottom:3pt}
dl.defs{margin:6pt 0;font-size:9.5pt}
dl.defs dt{font-family:var(--sans);font-size:7.5pt;font-weight:650;letter-spacing:.08em;
  text-transform:uppercase;color:var(--ink-3);margin-top:6pt}
dl.defs dd{margin:1pt 0 0}

/* ---------- Catalyst timeline: a ruled list, not a graphic ---------- */
.timeline{list-style:none;margin:6pt 0;padding:0;font-size:9.5pt}
.timeline li{display:flex;gap:10pt;padding:3.5pt 0;border-bottom:.5pt solid var(--rule)}
.timeline li:last-child{border-bottom:none}
.timeline .yr{font-family:var(--sans);font-weight:650;font-size:8pt;color:var(--accent);
  min-width:34pt;font-variant-numeric:tabular-nums}

/* ---------- Footnotes & running furniture ---------- */
.footnotes{
  margin-top:16pt;padding-top:7pt;border-top:.5pt solid var(--rule-strong);
  font-size:8pt;color:var(--ink-2);
}
.footnotes ol{margin:0;padding-left:14pt}
.footnotes li{margin-bottom:3pt}
sup.fn{font-size:6.5pt;font-weight:700;color:var(--accent);vertical-align:super;
  font-family:var(--sans);margin-left:1pt}
.disclaimer{
  margin-top:12pt;padding-top:7pt;border-top:1.5pt solid var(--ink);
  font-size:7.5pt;color:var(--ink-3);line-height:1.45;
}
.runhead,.runfoot{display:none}

/* ---------- Print ---------- */
@page{size:A4;margin:16mm 15mm}
@media print{
  /* Force light: a dark-mode host would otherwise print a black page. */
  :root{
    color-scheme:light !important;
    --paper:#ffffff; --plane:#ffffff;
    --ink:#000000; --ink-2:#3a3a38; --ink-3:#6b6a66;
    --rule:#d8d7d0; --rule-strong:#a8a7a2;
    --accent:#1c5cab; --pos:#1c5cab; --neg:#b3302f; --mid:#f0efec; --track:#dce9fa;
    --good:#0a7d0a; --warn:#a5740c; --serious:#b0552f; --critical:#b3302f;
  }
  body{background:#fff;font-size:9.5pt}
  .paper{max-width:none;margin:0;padding:0;min-height:0}
  .runhead{
    display:block;position:fixed;top:-11mm;left:0;right:0;
    font-family:var(--sans);font-size:6.5pt;letter-spacing:.1em;text-transform:uppercase;
    color:var(--ink-3);border-bottom:.5pt solid var(--rule);padding-bottom:2mm;
  }
  .runfoot{
    display:block;position:fixed;bottom:-11mm;left:0;right:0;
    font-family:var(--sans);font-size:6.5pt;color:var(--ink-3);
    border-top:.5pt solid var(--rule);padding-top:2mm;
  }
  .runhead .r,.runfoot .r{float:right}
  .sec{break-inside:auto}
  .exhibit,.twocol,table.data tr{break-inside:avoid}
  .sec > h2{break-after:avoid}
  .masthead{break-after:avoid}
  a{text-decoration:none;color:inherit}
}
@media (max-width:640px){
  .paper{padding:16px}
  .twocol{grid-template-columns:1fr}
  .twocol > div{padding-left:0;border-left:none;margin-top:10pt}
  .masthead h1{font-size:19pt}
}
"""
