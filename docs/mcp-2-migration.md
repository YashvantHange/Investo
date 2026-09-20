# Migrating to the mcp 2.x SDK

Investo pins `mcp[cli]>=1.2.0,<2`. This note records why, and what a migration costs, so the
decision is revisited deliberately rather than by an unpinned resolver.

## Why the pin exists

The dependency was originally declared `mcp[cli]>=1.2.0`, which resolves to whatever is newest.
When mcp 2.0 shipped, that became a **broken install**: mcp 2.x removed `mcp.server.fastmcp`
(the module is now a stub that raises `ModuleNotFoundError` naming the migration guide), and
`investo/server.py` imports `FastMCP` and `Context` from it at module scope.

The failure is total and silent-until-startup — `import investo.server` raises, so `investo-mcp`,
`python -m investo.server` and the `uvx --from git+…` install in the README all die immediately.
A developer with an already-resolved older environment saw nothing wrong; only a fresh install or
CI did. `tests/test_mcp_compat.py` now fails offline if the pin is widened.

## What the migration requires

| Area | mcp 1.x (current) | mcp 2.x |
|---|---|---|
| Server class | `from mcp.server.fastmcp import FastMCP` | `from mcp.server.mcpserver import MCPServer` |
| Request context | `from mcp.server.fastmcp import Context` | moved with the rename |
| `ToolAnnotations` fields | `readOnlyHint=`, `openWorldHint=`, … | `read_only_hint=`, `open_world_hint=`, … |

One nuance worth recording, because it changes how urgent each half is: the camelCase
`ToolAnnotations` names are still **accepted at runtime** in 2.x — they survive as pydantic
aliases, and the model sets `populate_by_name`. Only `mypy` objects, since it checks field names
rather than aliases. So the annotation change is a type-check concern; the module rename is the
real breakage.

Upstream guide: <https://py.sdk.modelcontextprotocol.io/v2/migration/>

## Scope when we do it

`src/investo/server.py` is the only affected module — the import at the top, and the `_READ` /
`_WRITE` `ToolAnnotations` constants. `tests/test_server_tools.py` reads `readOnlyHint` off the
registered tools and will need the snake_case attribute. Delete `tests/test_mcp_compat.py` and
this note as part of that change.

Worth doing rather than pinning forever: the 1.x line stops receiving protocol updates, and the
MCP registry entry in `server.json` advertises a package that will drift from current clients.
