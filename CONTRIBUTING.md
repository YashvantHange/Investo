# Contributing to Investo

Thanks for your interest! Investo is an MCP server that analyzes companies (India-first
NSE/BSE + global) from public data.

## Development setup

```bash
git clone https://github.com/YashvantHange/Investo
cd Investo
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"   # macOS/Linux: .venv/bin/pip install -e ".[dev]"
```

## Checks (all must pass — CI runs them on 3.10–3.12, Linux + Windows)

```bash
ruff check .        # lint + import order  (ruff check --fix to auto-fix)
mypy                # type check
pytest -q           # offline unit tests (no network)
```

**Tests must stay offline**: mock/monkeypatch data sources rather than hitting the network, so
CI is deterministic. See `tests/test_data_facade.py` for the monkeypatch pattern.

## Where things live

- `src/investo/sources/` — data providers (`data` facade, `yahoo`, `news`, `sec_edgar`, `keyed`).
  Analysis code calls the **`data` facade**, never `yahoo` directly.
- `src/investo/analysis/` — `ratios`, `dcf`, `scoring` (the 0-100 model + `WEIGHTS`), `peers`,
  `moat`, `risk`, `industry`, `management`, `report` (the `analyze_company` orchestrator).
- `src/investo/data/*.yaml` — curated peer groups and industry notes; **PRs to broaden coverage
  here are especially welcome**.
- `src/investo/server.py` — MCP tools (typed returns + read-only annotations).

## Guidelines

- Keep public data best-effort and defensive: return partial data with a `warning` rather than
  raising. Never invent numbers.
- Add/adjust tests for any behavior change. Add a `CHANGELOG.md` entry.
- Investo is **research/education only, not investment advice** — keep that framing in user-facing text.

## Reporting bugs / security

Open an issue for bugs. For security, see [`SECURITY.md`](SECURITY.md).
