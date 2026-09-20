#!/usr/bin/env python
"""Keep the project version identical across every file that declares it.

The version is declared in four files and **five** places (``server.json`` carries it twice:
once for the server entry, once for the published pypi package). Nothing enforced that they
agree, so a release could ship a wheel, an MCP registry entry and a Claude Desktop bundle each
claiming a different version -- a silent packaging bug that no test caught.

    python scripts/sync_version.py            # show the current version at each site
    python scripts/sync_version.py --check    # exit 1 if they disagree (CI / pytest use this)
    python scripts/sync_version.py --set 2.0.0

``--check`` is duplicated by ``tests/test_version_sync.py`` so the guard runs in the normal
offline suite; this script is the ergonomic front-end and the only thing that can *write*.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (path, regex with a single capture group around the version, human label).
# Each pattern must match exactly once per expected occurrence.
SITES: list[tuple[str, str, str]] = [
    ("pyproject.toml", r'(?m)^version = "([^"]+)"$', "pyproject [project].version"),
    ("server.json", r'(?m)^  "version": "([^"]+)",$', "server.json server version"),
    ("server.json", r'(?m)^      "version": "([^"]+)",$', "server.json package version"),
    ("manifest.json", r'(?m)^  "version": "([^"]+)",$', "manifest.json version"),
    ("src/investo/__init__.py", r'(?m)^__version__ = "([^"]+)"$', "investo.__version__"),
]

SEMVER = re.compile(r"^\d+\.\d+\.\d+([-+][0-9A-Za-z.-]+)?$")


def read_sites() -> list[tuple[str, str]]:
    """Return [(label, version)] for every declaration site, in SITES order."""
    found: list[tuple[str, str]] = []
    for rel, pattern, label in SITES:
        text = (ROOT / rel).read_text(encoding="utf-8")
        matches = re.findall(pattern, text)
        if len(matches) != 1:
            raise SystemExit(
                f"{rel}: expected exactly 1 match for {label}, found {len(matches)}. "
                "The file's shape changed -- update SITES in scripts/sync_version.py."
            )
        found.append((label, matches[0][0] if isinstance(matches[0], tuple) else matches[0]))
    return found


def check() -> int:
    sites = read_sites()
    versions = {v for _, v in sites}
    for label, version in sites:
        print(f"  {version:<12} {label}")
    if len(versions) == 1:
        print(f"OK: all {len(sites)} sites agree on {sites[0][1]}")
        return 0
    print(f"\nMISMATCH: {len(versions)} distinct versions across {len(sites)} sites.", file=sys.stderr)
    return 1


def write(new: str) -> int:
    if not SEMVER.match(new):
        print(f"Not a semver version: {new!r}", file=sys.stderr)
        return 2
    for rel, pattern, label in SITES:
        path = ROOT / rel
        text = path.read_text(encoding="utf-8")
        # Substitute only the captured group, preserving the surrounding syntax.
        def _sub(m: re.Match[str]) -> str:
            return m.group(0).replace(m.group(1), new, 1)
        updated, n = re.subn(pattern, _sub, text)
        if n != 1:
            raise SystemExit(f"{rel}: expected 1 substitution for {label}, made {n}")
        path.write_text(updated, encoding="utf-8")
        print(f"  set {new:<12} {label}")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", help="exit non-zero if the sites disagree")
    g.add_argument("--set", metavar="VERSION", help="write this version to every site")
    args = ap.parse_args(argv[1:])

    if args.set:
        return write(args.set)
    return check()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
