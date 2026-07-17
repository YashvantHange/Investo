"""Technical-snapshot tests (no network — synthetic price frames only)."""

import numpy as np
import pandas as pd

from investo.analysis.technical import (
    _annualized_vol,
    _cross_signal,
    _max_drawdown,
    _rsi,
    technical_snapshot,
)


def _frame(values: list[float], start: str = "2025-01-01") -> pd.DataFrame:
    idx = pd.date_range(start, periods=len(values), freq="D")
    return pd.DataFrame({"Close": [float(v) for v in values]}, index=idx)


# --------------------------------------------------------------------------------------
# RSI — Wilder's smoothing, not a simple mean
# --------------------------------------------------------------------------------------
def test_rsi_of_a_pure_rally_is_100():
    # No losses in the window -> the divide-by-zero guard returns 100, the correct reading.
    assert _rsi([float(i) for i in range(1, 40)], 14) == 100.0


def test_rsi_of_a_pure_selloff_is_zero():
    assert _rsi([float(i) for i in range(40, 1, -1)], 14) == 0.0


def test_rsi_matches_a_hand_computed_wilder_value():
    # A known 15-point series; the expected value is Wilder's RSI, which differs from a
    # simple-moving-average RSI — this pins the smoothing, not just "some RSI".
    prices = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42,
              45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28]
    rsi = _rsi(prices, 14)
    assert rsi is not None
    assert abs(rsi - 70.53) < 0.5  # canonical Wilder worked example


def test_rsi_needs_enough_points():
    assert _rsi([1.0, 2.0, 3.0], 14) is None


# --------------------------------------------------------------------------------------
# Moving-average crossover
# --------------------------------------------------------------------------------------
def test_golden_cross_detected_when_recent():
    # Long decline (50-DMA below 200-DMA) then a sharp late spike that yanks it above.
    vals = list(np.linspace(160, 80, 250)) + [800.0, 800.0, 800.0]
    assert _cross_signal(vals) == "golden"


def test_death_cross_detected_when_recent():
    vals = list(np.linspace(80, 160, 250)) + [5.0] * 12
    assert _cross_signal(vals) == "death"


def test_no_recent_cross_reads_none():
    # A steady uptrend: the 50-DMA has been above the 200-DMA for a long time, no recent cross.
    assert _cross_signal([float(i) for i in range(1, 320)]) == "none"


def test_cross_needs_enough_history():
    assert _cross_signal([100.0] * 50) == "none"


# --------------------------------------------------------------------------------------
# Volatility & drawdown
# --------------------------------------------------------------------------------------
def test_annualized_vol_of_a_flat_series_is_zero():
    assert _annualized_vol([100.0] * 30) == 0.0


def test_max_drawdown_of_a_v_shape():
    # 100 -> 50 -> 120: worst drawdown is -50%.
    dd = _max_drawdown([100, 80, 50, 70, 120])
    assert abs(dd - (-0.5)) < 1e-9


def test_max_drawdown_of_a_monotonic_rally_is_zero():
    assert _max_drawdown([10, 20, 30, 40]) == 0.0


# --------------------------------------------------------------------------------------
# The whole snapshot
# --------------------------------------------------------------------------------------
def test_snapshot_from_a_synthetic_uptrend():
    vals = list(np.linspace(60, 140, 300))
    bench = _frame(list(np.linspace(100, 130, 300)))
    snap = technical_snapshot("TEST.NS", history=_frame(vals),
                              info={"currency": "INR"}, benchmark_history=bench, market="IN")
    assert snap.above_50dma is True and snap.above_200dma is True
    assert snap.fifty_two_week_position == 1.0  # ends at the high
    assert snap.rsi_14 == 100.0  # unbroken rally
    assert snap.beta is not None and snap.beta_benchmark == "^NSEI"
    assert snap.evidence.confidence is not None
    assert any("moving average" in o for o in snap.observations)


def test_52_week_position_at_the_low_is_zero():
    vals = list(np.linspace(200, 100, 300))  # ends at the low
    snap = technical_snapshot("TEST.NS", history=_frame(vals), info={"currency": "INR"},
                              benchmark_history=_frame([100.0] * 300))
    assert snap.fifty_two_week_position == 0.0


def test_beta_falls_back_to_yahoo_stored_when_no_benchmark():
    vals = list(np.linspace(100, 120, 60))
    snap = technical_snapshot("TEST.NS", history=_frame(vals),
                              info={"currency": "INR", "beta": 1.35},
                              benchmark_history=_frame([]))  # empty -> can't compute
    assert snap.beta == 1.35
    assert snap.beta_benchmark == "Yahoo (stored)"


def test_no_history_returns_a_note_not_a_crash():
    snap = technical_snapshot("TEST.NS", history=None, info={"currency": "INR"},
                              benchmark_history=_frame([]))
    assert snap.note is not None
    assert snap.rsi_14 is None
    assert snap.evidence is not None


def test_snapshot_carries_the_context_not_a_signal_caveat():
    vals = list(np.linspace(60, 140, 300))
    snap = technical_snapshot("TEST.NS", history=_frame(vals), info={"currency": "INR"},
                              benchmark_history=_frame([100.0] * 300))
    assert any("not a trading signal" in n for n in snap.evidence.notes)
