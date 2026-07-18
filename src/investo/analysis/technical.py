"""Technical snapshot: the price/momentum backdrop a fundamentals analysis usually omits.

Trend (50/200-day moving averages and their crossover), momentum (RSI), volatility, drawdown,
beta and where the price sits in its 52-week range. This is **context, not a signal** — the module
emits no buy/sell verdict, and the model's docstring says so, because a technical readout inside a
fundamentals tool is easy for a downstream LLM to over-read.

The computation is a pure function of a price DataFrame, so it unit-tests offline against a
synthetic series with no network.
"""

from __future__ import annotations

import math
from typing import Any, Literal

from ..models import Provenance, TechnicalSnapshot
from ..sources import data
from . import evidence as ev

_RSI_PERIOD = 14
_DMA_SHORT = 50
_DMA_LONG = 200
_TRADING_DAYS = 252
_CROSS_LOOKBACK = 5  # a crossover within the last week still counts as "just happened"
_BENCHMARK = {"IN": "^NSEI", "US": "^GSPC"}


def technical_snapshot(
    symbol: str,
    *,
    history: Any | None = None,
    info: dict[str, Any] | None = None,
    benchmark_history: Any | None = None,
    market: str = "IN",
) -> TechnicalSnapshot:
    """Compute the technical snapshot for ``symbol``.

    ``history`` / ``info`` / ``benchmark_history`` are injectable so this runs offline in tests;
    when omitted they are fetched (one cached history call each).
    """
    symbol = symbol.upper()
    if history is None:
        history = data.get_history(symbol, period="2y", interval="1d")
    if info is None:
        info = data.get_info(symbol)

    if history is None or getattr(history, "empty", True) or len(history) < 2:
        return TechnicalSnapshot(
            ticker=symbol,
            currency=info.get("currency") if info else None,
            note="No price history available for a technical snapshot.",
            evidence=ev.build_meta(sources=[Provenance(source=ev.SRC_YAHOO)],
                                   present=0, expected=7,
                                   reason="no price history"),
        )

    close = [float(c) for c in history["Close"].tolist() if c is not None and not _isnan(c)]
    snap = TechnicalSnapshot(ticker=symbol, currency=(info or {}).get("currency"))
    snap.as_of = _last_date(history)
    snap.price = close[-1] if close else None

    _fill_trend(snap, close)
    snap.rsi_14 = _rsi(close, _RSI_PERIOD)
    snap.annualized_volatility = _annualized_vol(close)
    snap.max_drawdown_1y = _max_drawdown(close[-_TRADING_DAYS:])
    _fill_52w(snap, history)
    _fill_beta(snap, history, info, benchmark_history, market)

    snap.observations = _observations(snap)
    present = sum(v is not None for v in (
        snap.dma_50, snap.dma_200, snap.rsi_14, snap.annualized_volatility,
        snap.max_drawdown_1y, snap.fifty_two_week_position, snap.beta))
    snap.evidence = ev.build_meta(
        sources=[Provenance(source=ev.SRC_YAHOO, detail="daily OHLCV")],
        present=present, expected=7, as_of=snap.as_of,
        notes=["Technical context only — not a trading signal."],
    )
    return snap


# --------------------------------------------------------------------------------------
# Indicators
# --------------------------------------------------------------------------------------
def _fill_trend(snap: TechnicalSnapshot, close: list[float]) -> None:
    snap.dma_50 = _sma(close, _DMA_SHORT)
    snap.dma_200 = _sma(close, _DMA_LONG)
    price = close[-1]
    if snap.dma_50 is not None:
        snap.above_50dma = price >= snap.dma_50
    if snap.dma_200 is not None:
        snap.above_200dma = price >= snap.dma_200
    snap.cross_signal = _cross_signal(close)


def _sma(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return sum(values[-window:]) / window


def _cross_signal(close: list[float]) -> Literal["golden", "death", "none"]:
    """Golden/death cross if the 50-DMA crossed the 200-DMA within the last few sessions."""
    if len(close) < _DMA_LONG + _CROSS_LOOKBACK:
        return "none"
    for lag in range(_CROSS_LOOKBACK):
        end = len(close) - lag
        s_now = sum(close[end - _DMA_SHORT:end]) / _DMA_SHORT
        l_now = sum(close[end - _DMA_LONG:end]) / _DMA_LONG
        s_prev = sum(close[end - _DMA_SHORT - 1:end - 1]) / _DMA_SHORT
        l_prev = sum(close[end - _DMA_LONG - 1:end - 1]) / _DMA_LONG
        if s_prev <= l_prev and s_now > l_now:
            return "golden"
        if s_prev >= l_prev and s_now < l_now:
            return "death"
    return "none"


def _rsi(close: list[float], period: int) -> float | None:
    """RSI with **Wilder's smoothing** — the standard, not a simple rolling mean.

    Seed with a simple average of the first ``period`` changes, then smooth:
    ``avg = (prev*(period-1) + current) / period``. A run with no losses is RSI 100 (the
    division-by-zero guard), which is the correct reading of an unbroken rally.
    """
    if len(close) < period + 1:
        return None
    deltas = [close[i] - close[i - 1] for i in range(1, len(close))]
    gains = [max(d, 0.0) for d in deltas]
    losses = [-min(d, 0.0) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _annualized_vol(close: list[float]) -> float | None:
    """Standard deviation of daily log returns, annualised by sqrt(252)."""
    rets = [math.log(close[i] / close[i - 1])
            for i in range(1, len(close)) if close[i - 1] > 0 and close[i] > 0]
    if len(rets) < 2:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var) * math.sqrt(_TRADING_DAYS)


def _max_drawdown(close: list[float]) -> float | None:
    """Largest peak-to-trough decline over the window (a negative fraction)."""
    if len(close) < 2:
        return None
    peak = close[0]
    worst = 0.0
    for price in close:
        peak = max(peak, price)
        if peak > 0:
            worst = min(worst, price / peak - 1.0)
    return worst


def _fill_52w(snap: TechnicalSnapshot, history: Any) -> None:
    window = history["Close"].tail(_TRADING_DAYS)
    lo, hi = float(window.min()), float(window.max())
    if hi > lo and snap.price is not None:
        snap.fifty_two_week_position = max(0.0, min(1.0, (snap.price - lo) / (hi - lo)))


def _fill_beta(snap: TechnicalSnapshot, history: Any, info: dict[str, Any] | None,
               benchmark_history: Any | None, market: str) -> None:
    """Beta vs the market index over aligned daily returns; fall back to Yahoo's stored beta."""
    bench = _BENCHMARK.get((market or "IN").upper(), "^NSEI")
    if benchmark_history is None:
        benchmark_history = data.get_history(bench, period="2y", interval="1d")

    beta = _beta_from_returns(history, benchmark_history)
    if beta is not None:
        snap.beta = beta
        snap.beta_benchmark = bench
        return
    stored = (info or {}).get("beta")
    if stored is not None:
        try:
            snap.beta = float(stored)
            snap.beta_benchmark = "Yahoo (stored)"
        except (TypeError, ValueError):
            pass


def _beta_from_returns(stock: Any, bench: Any) -> float | None:
    if bench is None or getattr(bench, "empty", True):
        return None
    # Inner-join on date so holidays/half-days don't misalign the two series.
    joined = _join_returns(stock, bench)
    if len(joined) < 30:
        return None
    xs = [b for _, b in joined]
    ys = [s for s, _ in joined]
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / len(xs)
    var = sum((x - mx) ** 2 for x in xs) / len(xs)
    return cov / var if var > 0 else None


def _join_returns(stock: Any, bench: Any) -> list[tuple[float, float]]:
    s = _daily_returns(stock)
    b = _daily_returns(bench)
    common = sorted(set(s) & set(b))
    return [(s[d], b[d]) for d in common]


def _daily_returns(df: Any) -> dict[Any, float]:
    closes = df["Close"]
    out: dict[Any, float] = {}
    prev = None
    prev_idx = None
    for idx, val in closes.items():
        v = float(val)
        if prev is not None and prev > 0 and v > 0:
            out[_day(idx)] = v / prev - 1.0
        prev, prev_idx = v, idx
    _ = prev_idx
    return out


def _day(idx: Any) -> Any:
    return idx.date() if hasattr(idx, "date") else idx


# --------------------------------------------------------------------------------------
# Prose
# --------------------------------------------------------------------------------------
def _observations(s: TechnicalSnapshot) -> list[str]:
    out: list[str] = []
    if s.above_50dma is not None and s.above_200dma is not None:
        if s.above_50dma and s.above_200dma:
            out.append("Trading above both the 50- and 200-day moving averages (uptrend).")
        elif not s.above_50dma and not s.above_200dma:
            out.append("Trading below both the 50- and 200-day moving averages (downtrend).")
        else:
            out.append("Mixed: above one moving average and below the other.")
    if s.cross_signal == "golden":
        out.append("Golden cross: the 50-DMA recently crossed above the 200-DMA.")
    elif s.cross_signal == "death":
        out.append("Death cross: the 50-DMA recently crossed below the 200-DMA.")
    if s.rsi_14 is not None:
        if s.rsi_14 >= 70:
            out.append(f"RSI {s.rsi_14:.0f}: technically overbought.")
        elif s.rsi_14 <= 30:
            out.append(f"RSI {s.rsi_14:.0f}: technically oversold.")
        else:
            out.append(f"RSI {s.rsi_14:.0f}: neutral momentum.")
    if s.max_drawdown_1y is not None and s.max_drawdown_1y <= -0.2:
        out.append(f"Down {abs(s.max_drawdown_1y):.0%} from its 1-year peak at the worst point.")
    if s.fifty_two_week_position is not None:
        where = ("near its 52-week high" if s.fifty_two_week_position >= 0.8
                 else "near its 52-week low" if s.fifty_two_week_position <= 0.2
                 else "mid-range in its 52-week band")
        out.append(f"Price is {where}.")
    return out


def _isnan(x: float) -> bool:
    return isinstance(x, float) and math.isnan(x)


def _last_date(history: Any) -> str | None:
    try:
        idx = history.index[-1]
        return idx.date().isoformat() if hasattr(idx, "date") else str(idx)
    except Exception:
        return None
