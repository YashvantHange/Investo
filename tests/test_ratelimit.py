"""Rate-limiter tests (deterministic — clock/sleep are monkeypatched)."""

from investo.sources import ratelimit


def test_min_interval_schedules_gap(monkeypatch):
    lim = ratelimit.RateLimiter()
    now = {"t": 100.0}
    sleeps: list[float] = []
    monkeypatch.setattr(ratelimit, "_monotonic", lambda: now["t"])
    monkeypatch.setattr(ratelimit, "_sleep", lambda d: sleeps.append(d))

    lim.wait("k", 2.0)            # first call: no wait
    assert sleeps == []
    lim.wait("k", 2.0)            # second: must wait ~2s to honor the interval
    assert sleeps and abs(sleeps[-1] - 2.0) < 1e-9


def test_min_interval_zero_is_noop(monkeypatch):
    lim = ratelimit.RateLimiter()
    sleeps: list[float] = []
    monkeypatch.setattr(ratelimit, "_sleep", lambda d: sleeps.append(d))
    lim.wait("k", 0.0)
    assert sleeps == []


def test_daily_cap_blocks_after_limit(monkeypatch):
    lim = ratelimit.RateLimiter()
    monkeypatch.setattr(ratelimit, "_today", lambda: "2026-07-11")
    assert lim.allow_daily("av", 2) is True
    assert lim.allow_daily("av", 2) is True
    assert lim.allow_daily("av", 2) is False   # cap reached -> caller falls back


def test_daily_cap_resets_next_day(monkeypatch):
    lim = ratelimit.RateLimiter()
    day = {"d": "2026-07-11"}
    monkeypatch.setattr(ratelimit, "_today", lambda: day["d"])
    assert lim.allow_daily("av", 1) is True
    assert lim.allow_daily("av", 1) is False
    day["d"] = "2026-07-12"
    assert lim.allow_daily("av", 1) is True     # new day resets the counter


def test_daily_cap_zero_means_unlimited():
    lim = ratelimit.RateLimiter()
    assert all(lim.allow_daily("x", 0) for _ in range(50))
