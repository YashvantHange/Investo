# Publishing Investo

Three distribution channels, all driven from this repo.

## 1. PyPI (enables `uvx investo-mcp`)

Publishing is automated by [`.github/workflows/publish.yml`](.github/workflows/publish.yml) on a
GitHub Release, using **PyPI Trusted Publishing** (no API token stored).

One-time setup: on PyPI, add a Trusted Publisher for project `investo` →
`YashvantHange/Investo`, workflow `publish.yml`, environment `pypi`.

Then:

```bash
# bump version in pyproject.toml + server.json + manifest.json, update CHANGELOG.md
git tag v0.1.0 && git push --tags
# create a GitHub Release for the tag -> workflow builds & publishes
```

Manual build/check:

```bash
python -m build            # -> dist/investo-*.whl (includes data/*.yaml, py.typed)
twine check dist/*
```

After it's live: `uvx --from investo investo-mcp` runs the server with no clone.

## 2. Claude Desktop bundle (`.mcpb`)

```bash
scripts/build_mcpb.sh          # or scripts\build_mcpb.ps1 on Windows  (needs Node.js)
```

This validates `manifest.json` and packs `investo.mcpb`. Users double-click / drag it into
**Claude Desktop → Settings → Extensions**; the bundle prompts for optional API keys. The
release workflow also attaches `investo.mcpb` to each GitHub Release.

## 3. Official MCP registry

[`server.json`](server.json) is the registry manifest. Publish with the official CLI:

```bash
# install mcp-publisher (see modelcontextprotocol/registry), then:
mcp-publisher login github
mcp-publisher publish        # validates server.json and lists io.github.YashvantHange/investo
```

Keep `version` in sync across `pyproject.toml`, `server.json`, and `manifest.json`.

## Cursor

Cursor reads MCP servers from `.cursor/mcp.json` (project) or the global config — see
`examples/cursor_mcp.json`. Once on PyPI you can use `uvx --from investo investo-mcp` there too.
