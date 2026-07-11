"""Yahoo Finance data source (primary).

Wraps ``yfinance`` for profile / financial statements / holders / news / ESG, and the
Yahoo search endpoint for name -> ticker resolution. Every function is defensive: public
data is flaky, so we catch failures and return partial data (or None) rather than raising.
"""

from __future__ import annotations

import logging
import math
import time
from typing import Any

import httpx

try:  # yfinance is a hard dependency, but keep import failures from crashing the module
    import yfinance as yf
except Exception:  # pragma: no cover
    yf = None  # type: ignore

# yfinance is chatty on stderr for delisted / missing symbols (which we probe on purpose
# when recovering NSE/BSE listings). Silence its loggers so tool output stays clean.
for _name in ("yfinance", "yfinance.data", "yfinance.utils", "peewee"):
    logging.getLogger(_name).setLevel(logging.CRITICAL)
# httpx/httpcore log every request at INFO; keep only warnings and above.
for _name in ("httpx", "httpcore"):
    logging.getLogger(_name).setLevel(logging.WARNING)

from ..models import CompanyProfile, FinancialPeriod, Financials, TickerCandidate  # noqa: E402

_YAHOO_SEARCH_URL = "https://query2.finance.yahoo.com/v1/finance/search"
_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# In-process TTL caches (so a long-running server doesn't serve stale data, and repeated
# calls within one analysis don't re-hit the network).
_CACHE_TTL = 900.0  # 15 minutes for company info
_FX_TTL = 3600.0  # 1 hour for FX rates
_MISSING = object()
_INFO_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _cache_get(cache: dict[str, tuple[float, Any]], key: str, ttl: float) -> Any:
    entry = cache.get(key)
    if entry is None:
        return _MISSING
    stamped, value = entry
    if time.monotonic() - stamped > ttl:
        cache.pop(key, None)
        return _MISSING
    return value


def _cache_set(cache: dict[str, tuple[float, Any]], key: str, value: Any) -> None:
    cache[key] = (time.monotonic(), value)


# --------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------
def _to_float(val: Any) -> float | None:
    """Coerce a value (possibly numpy / NaN / None) to a plain float or None."""
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _to_int(val: Any) -> int | None:
    f = _to_float(val)
    return int(f) if f is not None else None


def market_of_symbol(symbol: str, exchange: str | None = None) -> str:
    """Classify a symbol/exchange into a coarse market: 'IN' or 'US' or 'OTHER'."""
    s = (symbol or "").upper()
    ex = (exchange or "").upper()
    if s.endswith(".NS") or s.endswith(".BO") or ex in {"NSI", "BSE", "NSE"}:
        return "IN"
    if "." not in s or ex in {"NMS", "NYQ", "NGM", "PCX", "ASE", "NCM", "BATS"}:
        return "US"
    return "OTHER"


# --------------------------------------------------------------------------------------
# Search (name -> ticker)
# --------------------------------------------------------------------------------------
def search(query: str, limit: int = 10) -> list[TickerCandidate]:
    """Query the Yahoo search endpoint and return ranked ticker candidates."""
    params: dict[str, Any] = {"q": query, "quotesCount": limit, "newsCount": 0, "listsCount": 0}
    try:
        with httpx.Client(timeout=10.0, headers=_HTTP_HEADERS) as client:
            resp = client.get(_YAHOO_SEARCH_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return []

    out: list[TickerCandidate] = []
    for q in data.get("quotes", []):
        symbol = q.get("symbol")
        if not symbol:
            continue
        exchange = q.get("exchange") or q.get("exchDisp")
        out.append(
            TickerCandidate(
                symbol=symbol,
                name=q.get("shortname") or q.get("longname"),
                exchange=q.get("exchDisp") or exchange,
                market=market_of_symbol(symbol, exchange),
                quote_type=q.get("quoteType"),
                score=_to_float(q.get("score")),
            )
        )
    return out


# --------------------------------------------------------------------------------------
# yfinance access
# --------------------------------------------------------------------------------------
def _ticker(symbol: str):
    if yf is None:  # pragma: no cover
        raise RuntimeError("yfinance is not available")
    return yf.Ticker(symbol)


def get_info(symbol: str) -> dict[str, Any]:
    """Fetch (and cache) the yfinance ``.info`` dict for a symbol. Never raises."""
    key = symbol.upper()
    cached = _cache_get(_INFO_CACHE, key, _CACHE_TTL)
    if cached is not _MISSING:
        return cached
    info: dict[str, Any] = {}
    try:
        t = _ticker(symbol)
        raw = None
        try:
            raw = t.get_info()
        except Exception:
            raw = getattr(t, "info", None)
        if isinstance(raw, dict):
            info = dict(raw)
    except Exception:
        info = {}
    # Fill price/market cap from fast_info if missing -- but only for symbols that clearly
    # exist (have company metadata). Skip empty/delisted probes to avoid noisy downloads.
    looks_real = bool(info.get("longName") or info.get("shortName") or info.get("sector"))
    if looks_real and (not info.get("currentPrice") or not info.get("marketCap")):
        try:
            fi = _ticker(symbol).fast_info
            info.setdefault("currentPrice", getattr(fi, "last_price", None))
            info.setdefault("marketCap", getattr(fi, "market_cap", None))
            info.setdefault("currency", getattr(fi, "currency", None))
        except Exception:
            pass
    _cache_set(_INFO_CACHE, key, info)
    return info


def get_profile(symbol: str) -> CompanyProfile:
    return profile_from_info(symbol, get_info(symbol))


def profile_from_info(symbol: str, info: dict[str, Any]) -> CompanyProfile:
    return CompanyProfile(
        ticker=symbol.upper(),
        name=info.get("longName") or info.get("shortName"),
        exchange=info.get("fullExchangeName") or info.get("exchange"),
        market=market_of_symbol(symbol, info.get("exchange")),
        country=info.get("country"),
        # Trading currency (what price/market cap are in). Statements may differ (see Financials).
        currency=info.get("currency") or info.get("financialCurrency"),
        sector=info.get("sector"),
        industry=info.get("industry"),
        website=info.get("website"),
        business_summary=info.get("longBusinessSummary"),
        employees=_to_int(info.get("fullTimeEmployees")),
        market_cap=_to_float(info.get("marketCap")),
        current_price=_to_float(info.get("currentPrice") or info.get("regularMarketPrice")),
        fifty_two_week_high=_to_float(info.get("fiftyTwoWeekHigh")),
        fifty_two_week_low=_to_float(info.get("fiftyTwoWeekLow")),
        key_executives=_officers(info),
    )


def _officers(info: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for o in info.get("companyOfficers", []) or []:
        if not isinstance(o, dict):
            continue
        out.append(
            {
                "name": o.get("name"),
                "title": o.get("title"),
                "age": o.get("age"),
                "total_pay": _to_float(o.get("totalPay")),
            }
        )
    return out


def _df_to_periods(df, max_periods: int = 4) -> list[FinancialPeriod]:
    periods: list[FinancialPeriod] = []
    if df is None or getattr(df, "empty", True):
        return periods
    try:
        cols = list(df.columns)[:max_periods]
    except Exception:
        return periods
    for col in cols:
        try:
            label = col.date().isoformat() if hasattr(col, "date") else str(col)
        except Exception:
            label = str(col)
        values: dict[str, float | None] = {}
        for idx in df.index:
            try:
                values[str(idx)] = _to_float(df.at[idx, col])
            except Exception:
                values[str(idx)] = None
        periods.append(FinancialPeriod(period=label, values=values))
    return periods


def get_financials(symbol: str, period: str = "annual") -> Financials:
    info = get_info(symbol)
    currency = info.get("financialCurrency") or info.get("currency")
    inc = bal = cf = None
    try:
        t = _ticker(symbol)
        if period == "quarterly":
            inc = t.quarterly_income_stmt
            bal = t.quarterly_balance_sheet
            cf = t.quarterly_cashflow
        else:
            inc = t.income_stmt
            bal = t.balance_sheet
            cf = t.cashflow
    except Exception:
        pass
    return Financials(
        ticker=symbol.upper(),
        currency=currency,
        period_type="quarterly" if period == "quarterly" else "annual",
        income_statement=_df_to_periods(inc),
        balance_sheet=_df_to_periods(bal),
        cash_flow=_df_to_periods(cf),
    )


def get_news_raw(symbol: str) -> list[dict[str, Any]]:
    """Return yfinance's raw news list for a symbol (may be empty)."""
    try:
        news = _ticker(symbol).news
        return news if isinstance(news, list) else []
    except Exception:
        return []


def get_holders(symbol: str) -> dict[str, Any]:
    """Best-effort holder breakdown. Far more complete for US than for NSE/BSE."""
    result: dict[str, Any] = {}
    try:
        t = _ticker(symbol)
        mh = t.major_holders
        if mh is not None and not getattr(mh, "empty", True):
            # yfinance returns a small frame; expose it as a dict of label -> value.
            try:
                result["major_holders"] = {
                    str(k): _to_float(v) if _to_float(v) is not None else str(v)
                    for k, v in mh.iloc[:, 0].items()
                }
            except Exception:
                result["major_holders"] = mh.to_dict()
    except Exception:
        pass
    try:
        ih = _ticker(symbol).institutional_holders
        if ih is not None and not getattr(ih, "empty", True):
            result["institutional_top"] = ih.head(5).to_dict(orient="records")
    except Exception:
        pass
    return result


_FX_CACHE: dict[str, tuple[float, float | None]] = {}


def fx_rate(from_ccy: str | None, to_ccy: str | None) -> float | None:
    """Return how many units of *to_ccy* equal one unit of *from_ccy* (e.g. USD->INR ~ 83).

    Returns 1.0 when currencies match or are missing, None if the rate can't be fetched.
    """
    if not from_ccy or not to_ccy or from_ccy.upper() == to_ccy.upper():
        return 1.0
    pair = f"{from_ccy.upper()}{to_ccy.upper()}=X"
    cached = _cache_get(_FX_CACHE, pair, _FX_TTL)
    if cached is not _MISSING:
        return cached
    rate: float | None = None
    try:
        fi = _ticker(pair).fast_info
        rate = _to_float(getattr(fi, "last_price", None))
    except Exception:
        rate = None
    _cache_set(_FX_CACHE, pair, rate)
    return rate


def get_esg_score(symbol: str) -> float | None:
    """Return the total ESG (sustainability) score if available, else None."""
    try:
        sus = _ticker(symbol).sustainability
        if sus is None or getattr(sus, "empty", True):
            return None
        for key in ("totalEsg", "esgScore"):
            if key in sus.index:
                return _to_float(sus.loc[key].iloc[0])
    except Exception:
        return None
    return None
