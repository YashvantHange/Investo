#!/usr/bin/env python
"""Portable launcher for the Investo MCP server.

The committed ``.mcp.json`` runs ``python scripts/mcp_launcher.py`` so it needs **no
machine-specific paths**. This script (standard library only) locates the project's
virtual environment and re-executes the server inside it, working the same on Windows,
macOS and Linux.

Resolution order:
  1. If ``investo`` already imports in the current interpreter, run it directly.
  2. Otherwise re-exec into the project ``.venv`` (``.venv/Scripts/python.exe`` on Windows,
     ``.venv/bin/python`` elsewhere).
  3. If no venv exists, print a one-line setup hint to stderr and exit.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _venv_python(root: Path) -> Path | None:
    for rel in ("Scripts/python.exe", "bin/python"):
        candidate = root / ".venv" / rel
        if candidate.exists():
            return candidate
    return None


def _same_interpreter(path: Path) -> bool:
    try:
        return os.path.samefile(str(path), sys.executable)
    except OSError:
        return path.resolve() == Path(sys.executable).resolve()


def main() -> None:
    venv_py = _venv_python(ROOT)

    # If a project venv exists and we're not already in it, run the server there as a child
    # process that inherits our stdio pipes (works reliably on Windows, where os.execv would
    # break the MCP stdio handshake). We block and forward the child's exit code.
    if venv_py is not None and not _same_interpreter(venv_py):
        completed = subprocess.run(
            [str(venv_py), "-m", "investo.server"], cwd=str(ROOT)
        )
        sys.exit(completed.returncode)

    # Running inside the venv (or a global install): start the server directly.
    src = ROOT / "src"
    if src.is_dir():
        sys.path.insert(0, str(src))
    try:
        from investo.server import main as run_server
    except ModuleNotFoundError:
        sys.stderr.write(
            "Investo MCP: package not installed and no .venv found.\n"
            "Set up once:  python -m venv .venv && "
            ".venv/Scripts/pip install -e .   (use .venv/bin/pip on macOS/Linux)\n"
        )
        sys.exit(1)
    run_server()


if __name__ == "__main__":
    main()
