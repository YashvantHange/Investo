# Changelog

All notable changes to Investo are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **PDF export** — `investo analyze --pdf [FILE]` renders the research note to PDF, with **no new
  required dependency**. It shells out to a system Chrome/Edge/Chromium/Brave if one is installed
  (the usual case), falls back to a Playwright-managed Chromium (`pip install 'investo[pdf]' &&
  playwright install chromium`), and otherwise fails with a message naming all three remedies —
  while still leaving the `.html` on disk. `INVESTO_CHROME` overrides browser discovery;
  `INVESTO_PDF_TIMEOUT` and `INVESTO_EXPORT_DIR` are configurable. The engine lives in
  `investo.export` (`save_html`, `save_pdf`, `find_browser`, `html_to_pdf`).

### Changed
- **`investo analyze` output flags now compose.** `--json`, `--html` and `--pdf` each do one thing
  and can be combined; previously `--html` silently suppressed `--json`. Bare `--html`/`--pdf` write
  `investo-<SYMBOL>-<YYYY-MM-DD>.<ext>`; parent directories are created; a PDF-engine failure exits
  2 (with the `.html` retained) and prints to stderr.
- **`investo analyze --html` now renders an institutional research note, not a dashboard.** The old
  one-pager (rounded cards, KPI tiles, coloured status pills, ✓/▲ emoji, no charts) read as a
  generated artifact and covered fewer sections than the terminal report. The new renderer
  (`investo.render`) is a print-ready equity-research document: numbered sections, a serif text
  face at a readable measure, hand-written inline-SVG exhibits (score decomposition, a diverging
  peer-percentile chart, a margin-vs-growth scatter, sparklines, intrinsic-value-vs-price), `@page`
  A4 furniture with running header/footer, footnotes, and a **Source:** line under every exhibit
  that names the provenance and says when a figure is an Investo estimate rather than a forecast.
  Status is carried by typography, not coloured lozenges; the document is self-contained and
  CSP-safe. `render_html(report, standalone=False)` still returns a body fragment for embedding.
- The renderer covers every section the terminal report does — valuation/DCF, peers, industry,
  moat, risk, SWOT and news — which the old HTML silently dropped.
- **One section registry** (`investo.render.sections`) is now the single ordered source of truth;
  the host-LLM guidance in `analyze_company` is generated from it, so the narrative and the
  rendered document can no longer describe different reports.
- **Analysis modules emit plain prose.** `thesis`/`ownership`/`buffett` observations no longer
  carry ✓/✗/⚠/→ glyphs; presentation is the renderer's job, and the renderer strips any residual
  dingbats at the boundary as a backstop.

### Removed
- `investo.analysis.report_html` — replaced by the `investo.render` package. (The only importer was
  the CLI.)

### Fixed
- **Relative-to-industry reported 0.37 confidence over zero data.** A company in no curated peer
  group (KPIT and the whole automotive ER&D cohort were in none) computed no metrics, then scored
  `0.80 × (0.4 + 0.6×0) = 0.32` plus a `+0.05` **cross-source agreement bonus awarded over zero
  rows** — a confident-looking number manufactured from nothing, which then leaked into the
  report-level and thesis-level aggregates. Zero coverage now scores **0.00** with a reason that
  says why. The same arithmetic was scoring 0.37 for every `unknown` Buffett criterion; that is
  fixed too.
- **Dead tickers in `data/peers.yaml`**, each of which silently dropped a company out of its own
  peer table: `TATAMOTORS.NS` (superseded by the `TMCV.NS`/`TMPV.NS` demerger, both already
  listed), `SPICEJET.NS` (resolves on BSE only → `SPICEJET.BO`), plus `LTIM.NS` and `AKZOINDIA.NS`
  removed as unresolvable across `.NS`/`.BO`. Added `scripts/validate_peers.py` to catch this
  class of rot, which no offline test can.

### Added
- **Automotive ER&D peer group** (`KPITTECH.NS`, `TATAELXSI.NS`, `TATATECH.NS`, `LTTS.NS`,
  `CYIENT.NS`) — the market treats these as one cohort, and Yahoo's "Information Technology
  Services" classification points the entire analysis at the wrong drivers, CAGR and risks. Plus
  `auto_components`, `hospitals_diagnostics` and `capital_goods_defence`.
- **Peer-resolution ladder** (`peers.resolve_peer_group`): curated membership → keyword match on
  Yahoo's industry/sector → Finnhub → none. The resulting `PeerBasis` travels on `PeerComparison`,
  `RelativeComparison` and `IndustryIntelligence`, so a guessed cohort can never be presented with
  the confidence of a deliberate one.
- **Three more relative metrics** — EV/EBITDA, ROA and P/S (7 → 10). Coverage is measured against
  the metrics the peer set can actually rank on, so adding a metric Indian peers rarely report
  doesn't silently mark every Indian company down.
- **A peer group can reframe the industry narrative**, not just its outlook and CAGR: KPIT's
  sub-domains are now SDV, ADAS and EV powertrain rather than "IT services & outsourcing". Yahoo's
  raw `industry` string is preserved alongside — it's a fact, and hiding the disagreement would be
  worse than showing it.
- **`docs/confidence.md`** — worked examples, the reasoning behind each factor, and the known
  limitations of the confidence model.
- `evidence.confidence(reliability_factor=…)` for module-specific discounts, and per-group
  provenance (`version`, `updated_at`, `source`) in `peers.yaml`.

### Changed
- **`ev.aggregate` blends modules by a coverage-weighted mean.** A module that found nothing now
  carries zero weight rather than dragging the report down, and the evidence block says how many
  modules came back empty.
- `RelativeMetric` carries a `unit` (`ratio`/`percent`); renderers no longer guess from the metric
  name, which rendered any unrecognised ratio (EV/EBITDA, P/S) as a percentage.

### Added
- **Listed in the [Cursor Directory](https://cursor.directory)** with a one-click "Add to Cursor"
  install. The recommended config is now **`uvx --from git+…/Investo investo-mcp`** — it builds
  & runs Investo straight from GitHub with **no clone and no venv** (requires `uv`), so it works
  from a global config for any user. The `python scripts/mcp_launcher.py` launcher remains the
  from-source option for project-scoped setups. Verified end-to-end via an MCP stdio handshake.
- **Rate limiting** (`sources/ratelimit.py`): per-provider minimum call interval + an Alpha
  Vantage daily cap that falls back to Yahoo when exhausted; tunable via
  `INVESTO_RATE_MIN_INTERVAL` / `INVESTO_AV_DAILY_CAP`.
- **Application logging** to **stderr** (stdout stays clean for MCP JSON-RPC), controlled by
  `INVESTO_LOG_LEVEL`; logs tool calls, provider selection, timings and rate-limit events.
- **Stronger input validation**: `market`/`period` are enums and `get_news` `limit` is bounded
  (1–50) in the tool JSON schemas; company name/ticker is sanitized (non-empty, length-capped).
- **Progress notifications** during `analyze_company` (runs off the event loop; emits
  resolve → fetch → compute → score → done).
- Typed `SecFacts` / `ProviderStatus` models so **all 15 tools expose a precise output schema**.
- **Provider facade** (`sources/data.py`): licensed keyed APIs (Alpha Vantage / FMP) are the
  primary source when a key is set, with Yahoo Finance as the zero-config fallback; a
  `provider_status` tool reports the active mode.
- **MCP polish**: all tools carry `readOnlyHint` / `openWorldHint` annotations, human titles,
  and typed pydantic returns so clients get an output schema + structured content.
- **Packaging & distribution**: PyPI-ready metadata (classifiers, `py.typed`, bundled data),
  `server.json` (MCP registry), `manifest.json` + build scripts (`.mcpb` Claude Desktop
  bundle), CI (ruff/mypy/pytest on 3.10–3.12 × Linux/Windows) and a Trusted-Publishing
  release workflow.
- **Docs**: `SECURITY.md` (data-flow & privacy disclosure), `PUBLISHING.md`, `CONTRIBUTING.md`,
  README "Data sources & legal" + "Privacy" sections and badges.
- **Trust caveats**: warnings for sharp revenue discontinuities (demerger/restructuring) and
  financial-sector companies; degraded-mode messaging when a source returns no data.
- Configurable SEC EDGAR contact via `INVESTO_SEC_CONTACT`.
- Expanded offline test suite (41 tests) covering ratios, news categorization, config, the
  provider facade, and report assembly.

### Changed
- **~4–5× faster `analyze_company`**: independent network fetches (financials, peers, news,
  ESG) now run concurrently; peer rows are fetched in parallel.
- In-process caches now have TTLs (15 min for company info, 1 h for FX).
- Dropped the weak "quarter" news keyword to reduce earnings/management misclassification.

## [0.1.0]

### Added
- Initial release: MCP server + CLI with 14 tools — profile, financial statements, ratios,
  competitor comparison, DCF valuation, economic moat, risk, management, news, SWOT seeds and a
  0-100 rating across 11 weighted buckets. India-first (NSE/BSE) with US/global support.
