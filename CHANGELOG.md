# Changelog

All notable changes to Investo are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
