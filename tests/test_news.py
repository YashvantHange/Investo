"""News categorization tests (no network)."""

import pytest

from investo.sources.news import _categorize


@pytest.mark.parametrize("title,expected", [
    ("Infosys Q3 results beat estimates, revenue up 8%", "earnings"),
    ("Reliance to acquire stake in retail startup", "m&a"),
    ("TCS appoints new CEO effective next quarter", "management"),
    ("SEBI issues notice to company over disclosure lapse", "legal-regulatory"),
    ("Company unveils new AI product for enterprises", "product-ai"),
    ("Stock rises on broad market rally", "general"),
])
def test_categorize(title, expected):
    assert _categorize(title) == expected


def test_categorize_is_case_insensitive():
    assert _categorize("QUARTERLY PROFIT SURGES") == "earnings"
