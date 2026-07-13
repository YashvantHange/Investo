"""Curated reference data (peer groups, industry notes) loaded from bundled YAML."""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any

import yaml

_DATA_DIR = Path(__file__).resolve().parent


@cache
def _load_yaml(filename: str) -> dict[str, Any]:
    path = _DATA_DIR / filename
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def peer_groups() -> dict[str, Any]:
    return _load_yaml("peers.yaml").get("groups", {})


def industry_notes() -> dict[str, Any]:
    return _load_yaml("industry.yaml").get("sectors", {})


def growth_engines() -> dict[str, Any]:
    """Curated 5-year growth engines: ``{'by_ticker': {...}, 'by_sector': {...}}``."""
    data = _load_yaml("growth.yaml")
    return {"by_ticker": data.get("by_ticker", {}), "by_sector": data.get("by_sector", {})}
