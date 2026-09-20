# Security & Privacy

Investo is a local MCP server / CLI. It runs on your machine and only reaches out to public
financial-data endpoints. This document describes exactly what it does with data and network
access, so you (and any directory reviewer) can assess it.

## What leaves your machine

When you analyze a company, Investo sends the **company name or ticker** (and nothing else about
you) to public data endpoints to fetch financials and news:

| Endpoint | Purpose | When |
|---|---|---|
| `query2.finance.yahoo.com`, Yahoo Finance (via `yfinance`) | profile, statements, ratios, holders, ESG, price | always (default source) |
| `news.google.com/rss` | recent company headlines | on `get_news` / `analyze_company` |
| `data.sec.gov`, `www.sec.gov` | US-GAAP facts (US/ADR only) | only on `get_sec_facts` |
| `www.alphavantage.co`, `financialmodelingprep.com`, `finnhub.io` | licensed fundamentals / peers | only if you set the matching API key |

Investo sends **no telemetry, no analytics, and no personal data**. It does not phone home.

## Secrets handling

- API keys are read **only** from environment variables (`ALPHAVANTAGE_API_KEY`, `FMP_API_KEY`,
  `FINNHUB_API_KEY`) — see `.env.example`. They are never logged, printed, or written to disk.
- No credentials are required for the default (Yahoo) mode.

## Execution safety

- **26 of the 28 tools are read-only** data retrieval and computation, annotated
  `readOnlyHint: true`. They execute no shell commands and modify nothing on your system.
- **Two tools write files**, and are annotated `readOnlyHint: false` so a client can gate them:
  - `export_report` — writes the rendered research note to an HTML or PDF file.
  - `analyze_company` — writes an HTML copy of the report alongside its structured result.

  Both write **only** inside the export directory (`INVESTO_EXPORT_DIR`, default the current
  working directory). A path supplied by the model is sandboxed by `server._safe_export_path`,
  which **rejects** absolute paths and `..` traversal rather than silently clamping them.
- **PDF export may launch a browser process.** `--pdf` / `export_report` shell out to a system
  Chrome/Edge/Chromium/Brave (or a Playwright-managed Chromium) in headless mode, with a
  throwaway user-data directory, solely to print the generated HTML. The command line is built
  from a discovered browser path and Investo's own arguments — never from tool input.
  `INVESTO_CHROME` overrides discovery.
- **A loopback preview server may be started.** So that a report link is clickable in a client
  that blocks `file://`, Investo serves the report's directory over a static HTTP server bound
  to **`127.0.0.1` on an ephemeral port** (one per directory, on a daemon thread). It is not
  reachable from the network. Two caveats worth knowing: it serves *every* file in that
  directory, so do not point `INVESTO_EXPORT_DIR` at a directory holding unrelated private
  files; and it currently has no shutdown path, so it lives until the process exits.
- Tool inputs are used only as query/ticker parameters to the endpoints above (URL-encoded);
  there is no `eval`, no dynamic import of user input, and no code execution path from inputs.
- Tool failures surface as MCP `isError` results rather than crashing the server.
- **Logging goes to stderr only** (never stdout, which carries the MCP JSON-RPC protocol), at
  the level set by `INVESTO_LOG_LEVEL` (default `WARNING`). Logs record tickers, provider
  selection and timings — **no API keys or personal data are ever logged.**
- Outbound calls are **rate-limited** per provider (min-interval + Alpha Vantage daily cap) to
  respect provider limits.

## Data source terms & accuracy

- The default source, Yahoo Finance, is accessed via `yfinance`, which uses Yahoo's **public but
  unofficial** endpoints. This is best-effort, may be rate-limited, and is subject to Yahoo's
  terms — see the README "Data sources & legal". For production or commercial use, configure a
  **licensed** provider key (Alpha Vantage / FMP / Finnhub); Investo will prefer it.
- Investo is for **research and education only — not investment advice.**

## Reporting a vulnerability

Please open a **private security advisory** on the GitHub repository
(`Security > Report a vulnerability`) or open an issue without sensitive details and ask for a
private channel. We aim to acknowledge within a few days.
