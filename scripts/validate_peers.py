#!/usr/bin/env python
"""Check every ticker in ``data/peers.yaml`` actually resolves at the data provider.

A dead ticker in a curated group fails *silently and badly*: the company simply drops out of
its own peer table, which is indistinguishable from "no peer data" — the exact symptom curated
groups exist to prevent. This is not catchable offline, so it cannot live in the pytest suite
(which is deliberately network-free); run it by hand after editing peers.yaml.

    python scripts/validate_peers.py            # all groups
    python scripts/validate_peers.py auto_erd   # one group

Exits non-zero if any ticker is unresolvable, so it can gate a data change in CI if wanted.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from investo.data import peer_groups  # noqa: E402
from investo.sources import data  # noqa: E402


def main(argv: list[str]) -> int:
    only = set(argv[1:])
    groups = peer_groups()
    if only:
        groups = {k: v for k, v in groups.items() if k in only}
        if not groups:
            print(f"No such group(s): {', '.join(sorted(only))}", file=sys.stderr)
            return 2

    dead: list[tuple[str, str]] = []
    for key, group in groups.items():
        print(f"\n{group.get('label', key)}  ({key}, updated {group.get('updated_at', '?')})")
        for ticker in group.get("members", []):
            info = data.get_info(ticker)
            name = info.get("longName") or info.get("shortName")
            if name:
                print(f"  ok    {ticker:16} {name[:44]}")
            else:
                print(f"  DEAD  {ticker:16} unresolvable at the provider")
                dead.append((key, ticker))

    print()
    if dead:
        print(f"{len(dead)} dead ticker(s) — a company missing from its own peer table:")
        for key, ticker in dead:
            print(f"  {key}: {ticker}")
        return 1
    print("All tickers resolve.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
