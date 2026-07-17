# Investo 📈

[![CI](https://github.com/YashvantHange/Investo/actions/workflows/ci.yml/badge.svg)](https://github.com/YashvantHange/Investo/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-server-purple.svg)](https://modelcontextprotocol.io)
[![Cursor Directory](https://img.shields.io/badge/Cursor-listed-000000.svg)](https://cursor.directory)

**An AI investment-analysis agent you run from Claude or Cursor.**

> ⚠️ **Research and education only — not investment advice.**

Give Investo a company name — Indian (NSE/BSE) or global — and it gathers public financial
data and produces a full analysis: what the company does, its financials & ratios, a
competitor comparison, DCF intrinsic value, economic moat, risks, management, recent news,
SWOT seeds, and a **0–100 investment rating**.

Investo is a [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server. It
exposes tools to an AI client (Claude Code, Claude Desktop, Cursor); the client calls those
tools and writes the analysis narrative grounded in the structured data Investo returns.

> **Primary focus: Indian companies listed on NSE (`.NS`) and BSE (`.BO`).** US/global
> companies are supported too.

---

## What it produces

For any company, Investo supplies the evidence for:

1. **Domain / sector** — what the business does and its sub-domains.
2. **Financials & ratios** — income statement, balance sheet, cash flow + valuation,
   profitability, leverage, liquidity, growth, cash-flow ratios.
3. **Competitor analysis** — auto-compares against sector peers (e.g. Infosys → TCS, Wipro,
   HCL, Tech Mahindra, LTIMindtree).
4. **Industry intelligence** — sub-domains, demand drivers, CAGR, risks.
5. **News analysis** — recent headlines categorized (earnings, M&A, management, legal, product/AI).
6. **Management analysis** — executives, promoter/insider holding, capital allocation.
7. **DCF valuation** — intrinsic value/share, margin of safety, expected return.
8. **Economic moat** — brand / network / cost / scale / switching-cost signals.
9. **Risk analysis** — debt, currency, concentration, regulation, tech obsolescence.
10. **Rating out of 100** — a balanced 11-bucket score with per-bucket rationale.
11. **Warren Buffett checklist** — a weighted 0–100 quality-fit score; each criterion (ROE, ROIC,
    debt, owner earnings, margin of safety, management, moat) shows value vs threshold, a
    pass/warn/fail with the *reason*, a confidence, and its multi-year trend.
12. **Relative to industry** — key metrics vs the peer-set median with favourable-side percentiles.
13. **Shareholding pattern** — promoter/FII/DII/public split + promoter pledge, with
    quarter-over-quarter smart observations and an ownership signal (NSE/BSE filings; Yahoo fallback).
14. **5-year growth engine** — the primary engine plus ranked drivers (estimated contribution %,
    per-driver risks), a catalyst timeline, and a blended growth band.
15. **Fundamentals trend, red-flags, and an investment thesis** — multi-year health at a glance,
    automated deterioration warnings, and a synthesized pros/cons verdict.

Every section carries a **confidence score, provenance and reasoning** (the evidence layer), so an
AI agent — or you — can judge how far to trust each conclusion. A machine-readable `ai_signals`
digest and a self-contained, print-ready **research note** (`--html`) — numbered sections, inline
SVG exhibits, footnotes and per-exhibit source lines, styled as an institutional equity-research
document rather than a dashboard — are available too.

### Rating buckets (out of 100)

| Growth | Profitability | Cash Flow | Debt | Valuation | Moat | Management | Industry | Innovation | Risk | ESG* |
|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| 15 | 15 | 10 | 10 | 15 | 10 | 10 | 5 | 5 | 5 | 5* |

\*ESG is optional; when unavailable the remaining buckets renormalize to 100.

---

## Install

Requires **Python 3.10+**.

```bash
git clone https://github.com/YashvantHange/Investo
cd Investo
python -m venv .venv
# Windows: .venv\Scripts\activate   |   macOS/Linux: source .venv/bin/activate
pip install -e .
```

No API keys are required — Investo works out of the box using free Yahoo Finance data and
Google/Yahoo news. Optional keys (Alpha Vantage / FMP / Finnhub) enable richer/fallback data;
copy `.env.example` to `.env` and fill in any you have.

---

## Try it from the command line

```bash
investo analyze "Infosys"
investo analyze "Reliance Industries"
investo analyze "Tata Motors"
investo analyze AAPL
investo analyze "Reliance Industries" --html reliance.html   # self-contained research note
investo analyze "Infosys" --pdf infosys.pdf                  # PDF via headless Chrome/Edge
investo analyze "Infosys" --json --html infy.html           # flags compose; nothing is discarded
investo search "tata motors"
```

`--pdf` needs a Chromium-family browser: it uses a system **Chrome, Edge, Chromium or Brave** if one
is installed (no setup), falls back to a managed Chromium via `pip install 'investo[pdf]' &&
playwright install chromium`, and otherwise prints exactly how to fix it while still leaving the
`.html` on disk. Point `INVESTO_CHROME` at a specific executable to override discovery. Bare `--html`
/ `--pdf` (no filename) write `investo-<SYMBOL>-<date>.<ext>` in the working directory.

## Use it from Claude Code / Cursor

Do the one-time setup (creates the venv the launcher looks for):

```bash
python -m venv .venv
.venv\Scripts\pip install -e .     # macOS/Linux: .venv/bin/pip install -e .
```

**Claude Code** — this repo ships a project-scoped `.mcp.json` that runs
`python scripts/mcp_launcher.py`. **No paths to edit** — the launcher finds the project's
`.venv` itself and works on Windows/macOS/Linux. Opening the folder in Claude Code offers to
load the `investo` server (approve on first use); the included `CLAUDE.md` makes the agent
introduce itself as **Investo**.

**Cursor** — Investo is in the **[Cursor Directory](https://cursor.directory)**. One-click
install (requires [`uv`](https://docs.astral.sh/uv/) — the Python equivalent of `npx`):

[![Add to Cursor](https://cursor.com/deeplink/mcp-install-dark.svg)](cursor://anysphere.cursor-deeplink/mcp/install?name=investo&config=eyJjb21tYW5kIjogInV2eCIsICJhcmdzIjogWyItLWZyb20iLCAiZ2l0K2h0dHBzOi8vZ2l0aHViLmNvbS9ZYXNodmFudEhhbmdlL0ludmVzdG8iLCAiaW52ZXN0by1tY3AiXX0=)

Or add manually to `.cursor/mcp.json` (project) **or** `~/.cursor/mcp.json` (global) — both work:

```json
{ "command": "uvx", "args": ["--from", "git+https://github.com/YashvantHange/Investo", "investo-mcp"] }
```

`uvx` builds & runs Investo straight from GitHub — **no clone, no venv, works from any folder.**

**Claude Desktop** — use the same `uvx` config (see `examples/claude_desktop_config.json`), or
install the one-click **`.mcpb` bundle** (`scripts/build_mcpb.sh`).

**From source (no `uv`)** — clone, `python -m venv .venv && pip install -e .`, then point the
MCP config at the launcher: `{ "command": "python", "args": ["<ABSOLUTE>/scripts/mcp_launcher.py"] }`
(the launcher finds the venv itself). This is what a project-scoped `.mcp.json` uses.

See [`PUBLISHING.md`](PUBLISHING.md) for PyPI / `.mcpb` / MCP-registry release steps.

Then ask: *"Analyse Infosys"*, *"Compare HDFC Bank with its peers"*, *"What's the DCF value
of Reliance?"*

> **How the launcher works:** [`scripts/mcp_launcher.py`](scripts/mcp_launcher.py) is a tiny
> standard-library script. When a client runs it with any `python`, it re-launches the server
> inside the project's `.venv` (or uses the current interpreter if `investo` is already
> installed there). That's why the committed config needs no machine-specific paths.

---

## MCP tools

| Tool | Purpose |
|---|---|
| `search_company` | Resolve a name to an NSE/BSE/global ticker |
| `get_company_profile` | Sector, business summary, market cap, executives |
| `get_financials` | Income statement / balance sheet / cash flow |
| `get_key_ratios` | Valuation, profitability, leverage, growth, cash-flow ratios |
| `compare_peers` | Competitor comparison table |
| `get_industry_intelligence` | Sub-domains, demand drivers, CAGR, risks |
| `get_news` | Categorized recent headlines |
| `get_management` | Executives, holdings, capital allocation |
| `dcf_valuation` | Intrinsic value, margin of safety, expected return |
| `moat_assessment` | Economic-moat signals + heuristic score |
| `risk_assessment` | Risk signals + heuristic score |
| `score_company` | 0–100 composite rating |
| `buffett_checklist` | Warren-Buffett quality checklist: weighted 0–100 fit, per-criterion pass/warn/fail + reason, confidence & multi-year trend |
| `relative_metrics` | Key metrics vs the peer-set median (industry proxy) with favourable-side percentiles |
| `shareholding_pattern` | Promoter/FII/DII/public split + pledge, QoQ smart observations & ownership signal (NSE/BSE filings, Yahoo fallback) |
| `growth_outlook` | 5-year growth engine: ranked drivers (contribution %, risks), catalyst timeline, blended growth band |
| `fundamental_trend` | Multi-year revenue/profit/margin/EPS/ROE with per-year direction & health grade |
| `red_flags` | Automated deterioration warnings + overall risk level |
| `investment_thesis` | Synthesized pros/cons, quality grade, valuation stance & one-line verdict |
| `ai_signals` | Compact machine-readable digest (thesis, quality, confidence, ownership/growth signals, risk, valuation) |
| `technical_snapshot` | Price/momentum context: 50/200-DMA + golden/death cross, RSI, volatility, drawdown, beta, 52-week position (context, not a signal) |
| `dcf_sensitivity` | Intrinsic value across a discount-rate × terminal-growth grid + the growth implied by today's price |
| `compare_companies` | Head-to-head across 2–6 named tickers (not a curated group) |
| `peer_group_directory` | List the curated peer groups and their members |
| `export_report` | Render a full analysis to an HTML/PDF file (writes a file; path sandboxed) |
| `analyze_company` | Everything above bundled into one report (with a confidence/provenance evidence layer) |
| `get_sec_facts` | SEC EDGAR cross-check (US/ADR only) |

---

## Configuration

All optional — set as environment variables (or in `.env`; see `.env.example`):

| Variable | Purpose | Default |
|---|---|---|
| `ALPHAVANTAGE_API_KEY` / `FMP_API_KEY` / `FINNHUB_API_KEY` | Licensed data (primary when set) | — |
| `INVESTO_LOG_LEVEL` | Log verbosity **to stderr** (DEBUG/INFO/WARNING/ERROR) | `WARNING` |
| `INVESTO_RATE_MIN_INTERVAL` | Min seconds between Yahoo calls | `0.0` |
| `INVESTO_AV_DAILY_CAP` | Alpha Vantage daily cap before Yahoo fallback | `25` |
| `INVESTO_SEC_CONTACT` | Contact for the SEC EDGAR User-Agent | repo URL |
| `INVESTO_ENABLE_INDIA_HOLDINGS` | Fetch NSE/BSE shareholding filings (else Yahoo fallback) | `true` |
| `INVESTO_DEFAULT_MARKET` | `IN` or `US` | `IN` |
| `INVESTO_DCF_*` | DCF discount / terminal / years overrides | see `.env.example` |

## Data sources & legal

Investo prefers **licensed** data when you configure a key, and falls back to free Yahoo data
otherwise:

- **With an API key** (`ALPHAVANTAGE_API_KEY` / `FMP_API_KEY` / `FINNHUB_API_KEY`): licensed
  fundamentals are used as the **primary** source and take precedence for the fields they cover
  (recommended for production / commercial use).
- **Without a key** (default, zero-config): Yahoo Finance is used via `yfinance`, which relies on
  Yahoo's **public but unofficial** endpoints. This is best-effort, may be rate-limited, and is
  subject to Yahoo's terms of service. For **NSE/BSE** fundamentals Yahoo remains the practical
  source of record even when a key is set, because the licensed APIs' India coverage is limited.

The provider in effect is reported by the `provider_status` in tool output. See
[`SECURITY.md`](SECURITY.md) for the full list of endpoints Investo contacts.

### Privacy — what leaves your machine

Only the **company name or ticker** you ask about is sent to the data endpoints above. Investo
has **no telemetry**, stores no personal data, and reads API keys only from environment
variables (never logged). It is read-only and does not modify your system.

### Known limitations

- **Promoter/insider shareholding** for NSE/BSE has no clean free API — best-effort, often
  unavailable for Indian names.
- **Industry CAGR / market share** are curated/estimated (`data/*.yaml`), not live. Each peer group
  carries an `updated_at` so you can judge staleness rather than assume freshness.
- **Peer lists** start curated for major Indian sectors and are extensible via `data/peers.yaml`.
  A ticker in no group falls back to a keyword match on its Yahoo industry; that guess is reported
  as `basis: sector-fallback` and scored below a curated group. After editing peers.yaml, run
  `python scripts/validate_peers.py` — a dead ticker silently drops a company out of its own peer
  table, and no offline test can catch it.
- **Confidence is about evidence quality, not about being right** — see [docs/confidence.md](docs/confidence.md)
  for how it's computed and where it stops being trustworthy.
- Sharp reporting discontinuities (e.g. a demerger) can distort growth; Investo flags a warning
  when it detects one, but read the note in context.

> ⚠️ **Investo is for research and education only — not investment advice.** Do your own
> due diligence.

---

## License

MIT
