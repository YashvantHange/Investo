"""Company news from Google News RSS (primary) and Yahoo Finance, lightly categorized."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import feedparser
import httpx

from ..models import NewsFeed, NewsItem
from . import yahoo

_GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"

_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("earnings", ("earnings", "profit", "revenue", "results", "quarter", "q1", "q2", "q3", "q4",
                  "guidance", "beats", "misses", "margin", "ebitda")),
    ("m&a", ("acquire", "acquisition", "merger", "merges", "stake", "takeover", "buyout", "demerger")),
    ("management", ("ceo", "cfo", "chairman", "resign", "steps down", "appoint", "board", "director",
                    "promoter", "md &")),
    ("legal-regulatory", ("sebi", "lawsuit", "court", "fine", "penalty", "probe", "investigation",
                          "regulator", "rbi", "usfda", "fda", "tax", "raid", "ban", "notice")),
    ("product-ai", ("launch", "unveil", " ai ", "artificial intelligence", "product", "partnership",
                    "contract", "expansion", "plant", "capacity", "order", "deal")),
]


def _categorize(title: str) -> str:
    t = f" {title.lower()} "
    for category, words in _KEYWORDS:
        if any(w in t for w in words):
            return category
    return "general"


def _from_google(query: str, limit: int) -> list[NewsItem]:
    params = {"q": query, "hl": "en-IN", "gl": "IN", "ceid": "IN:en"}
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(_GOOGLE_NEWS_RSS, params=params)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
    except Exception:
        return []
    items: list[NewsItem] = []
    for entry in feed.entries[:limit]:
        title = getattr(entry, "title", "") or ""
        if not title:
            continue
        published = None
        if getattr(entry, "published_parsed", None):
            try:
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).date().isoformat()
            except Exception:
                published = None
        publisher = None
        src = getattr(entry, "source", None)
        if src is not None:
            publisher = getattr(src, "title", None)
        items.append(NewsItem(
            title=title,
            publisher=publisher,
            link=getattr(entry, "link", None),
            published=published,
            category=_categorize(title),
        ))
    return items


def _from_yahoo(symbol: str, limit: int) -> list[NewsItem]:
    items: list[NewsItem] = []
    for raw in yahoo.get_news_raw(symbol)[:limit]:
        # yfinance schema varies: newer nests under 'content'.
        content = raw.get("content") if isinstance(raw, dict) else None
        if isinstance(content, dict):
            title = content.get("title")
            link = (content.get("canonicalUrl") or {}).get("url") if isinstance(content.get("canonicalUrl"), dict) else None
            publisher = (content.get("provider") or {}).get("displayName") if isinstance(content.get("provider"), dict) else None
            published = content.get("pubDate")
            if published:
                published = str(published)[:10]
        else:
            title = raw.get("title")
            link = raw.get("link")
            publisher = raw.get("publisher")
            ts = raw.get("providerPublishTime")
            published = (
                datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat() if ts else None
            )
        if not title:
            continue
        items.append(NewsItem(
            title=title, publisher=publisher, link=link, published=published,
            category=_categorize(title),
        ))
    return items


def get_news(symbol: str, company_name: Optional[str] = None, limit: int = 15) -> NewsFeed:
    """Fetch and merge news for a company, de-duplicated by title."""
    query = company_name or symbol
    items = _from_google(f"{query} stock", limit) + _from_yahoo(symbol, limit)

    seen: set[str] = set()
    deduped: list[NewsItem] = []
    for it in items:
        key = it.title.strip().lower()[:80]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(it)

    note = None if deduped else "No recent news found from public feeds."
    return NewsFeed(ticker=symbol.upper(), items=deduped[:limit], note=note)
