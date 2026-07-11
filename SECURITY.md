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

- Investo performs **read-only** data retrieval and computation. Its tools do not write files,
  execute shell commands, or modify your system. All tools are annotated `readOnlyHint: true`.
- Tool inputs are used only as query/ticker parameters to the endpoints above (URL-encoded);
  there is no `eval`, no dynamic import of user input, and no code execution path from inputs.
- Every tool is wrapped so failures return a structured `{"error": ...}` instead of crashing.

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
