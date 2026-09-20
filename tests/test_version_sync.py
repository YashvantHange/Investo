"""The project version must be identical everywhere it is declared.

Four files declare it, five times (``server.json`` twice). Before this guard existed nothing
checked that they agreed, so a release could ship a wheel, an MCP registry entry and a Claude
Desktop bundle each claiming a different version. ``scripts/sync_version.py`` is the writer;
this is the same check running in the normal offline suite.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load_sync_version():
    spec = importlib.util.spec_from_file_location(
        "investo_sync_version", ROOT / "scripts" / "sync_version.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_every_declaration_site_agrees():
    sites = _load_sync_version().read_sites()
    versions = {v for _, v in sites}
    assert len(versions) == 1, f"version mismatch across declaration sites: {sites}"


def test_all_five_sites_are_found():
    # A silently-skipped site is the failure mode this guard exists to prevent: if a file's
    # shape changes so its pattern stops matching, read_sites() raises rather than passing.
    assert len(_load_sync_version().read_sites()) == 5


def test_declared_version_matches_the_installed_package():
    import investo

    sites = dict(_load_sync_version().read_sites())
    assert investo.__version__ == sites["investo.__version__"]


@pytest.mark.parametrize("bad", ["1.0", "v1.0.0", "1.0.0.0", ""])
def test_set_rejects_non_semver(bad):
    assert _load_sync_version().write(bad) == 2
