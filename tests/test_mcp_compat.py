"""Guard the ``mcp`` SDK major version.

mcp 2.0 removed ``mcp.server.fastmcp`` entirely -- the module is now a stub that raises
``ModuleNotFoundError`` pointing at the migration guide -- because ``FastMCP`` was renamed to
``MCPServer``. ``investo.server`` imports ``FastMCP`` at module scope, so with mcp 2.x installed
the server does not merely misbehave: it fails to import, and every entry point dies at startup.

The dependency was declared ``mcp[cli]>=1.2.0``, which happily resolves to 2.x, so a *fresh*
install was broken while a developer with an older resolved environment saw nothing wrong. That
is the failure mode this test exists to make loud: it fails offline, in the normal suite, the
moment the pin is widened -- before a release can ship a package that cannot start.

Remove this test as part of the mcp 2.x migration (see docs/mcp-2-migration.md), not before.
"""

from __future__ import annotations

import importlib.metadata

import pytest


def _mcp_major() -> int:
    return int(importlib.metadata.version("mcp").split(".")[0])


def test_mcp_major_version_is_pinned_below_2():
    major = _mcp_major()
    assert major < 2, (
        f"mcp {importlib.metadata.version('mcp')} is installed, but investo.server imports "
        "mcp.server.fastmcp, which mcp 2.x removed. Either restore the '<2' pin in "
        "pyproject.toml or complete the migration in docs/mcp-2-migration.md."
    )


def test_the_import_the_pin_protects_actually_works():
    # The symptom, not the proxy: this is the exact import that dies under mcp 2.x.
    from mcp.server.fastmcp import Context, FastMCP

    assert FastMCP is not None
    assert Context is not None


def test_server_module_imports():
    # investo.server binds FastMCP at module scope, so a bad mcp breaks import, not just calls.
    server = pytest.importorskip("investo.server")
    assert server.mcp is not None
