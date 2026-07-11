"""Input-validation tests (offline)."""

import asyncio

import pytest

from investo.server import _clean, mcp


def test_clean_strips_and_returns():
    assert _clean("  Infosys  ") == "Infosys"


def test_clean_rejects_empty():
    with pytest.raises(ValueError):
        _clean("   ")


def test_clean_rejects_too_long():
    with pytest.raises(ValueError):
        _clean("x" * 200)


def _schema(tool_name: str) -> dict:
    async def run():
        tools = await mcp.list_tools()
        return next(t for t in tools if t.name == tool_name).inputSchema
    return asyncio.run(run())


def test_market_enum_in_schema():
    market = _schema("search_company")["properties"]["market"]
    assert "IN" in str(market) and "US" in str(market)


def test_period_enum_in_schema():
    period = _schema("get_financials")["properties"]["period"]
    assert set(period.get("enum", [])) == {"annual", "quarterly"}


def test_news_limit_bounds_in_schema():
    limit = _schema("get_news")["properties"]["limit"]
    assert limit.get("minimum") == 1 and limit.get("maximum") == 50
