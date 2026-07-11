"""A tiny thread-safe rate limiter for outbound API calls.

Two mechanisms, keyed per provider:
- ``wait(key, min_interval)`` schedules calls at least ``min_interval`` seconds apart (short,
  fair waits — the lock is released before sleeping).
- ``allow_daily(key, cap)`` enforces an in-memory per-day cap (e.g. Alpha Vantage's free 25/day)
  and returns ``False`` once exhausted, so the caller can skip and fall back rather than error.

Clock/sleep are module-level indirections so tests can drive them deterministically.
"""

from __future__ import annotations

import threading
import time
from datetime import date

# Indirections for tests (monkeypatch these).
_monotonic = time.monotonic
_sleep = time.sleep


def _today() -> str:
    return date.today().isoformat()


class RateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next: dict[str, float] = {}          # key -> earliest next start time
        self._daily: dict[str, tuple[str, int]] = {}  # key -> (day, count)

    def wait(self, key: str, min_interval: float) -> None:
        """Block just long enough to keep >= min_interval between calls with the same key."""
        if min_interval <= 0:
            return
        with self._lock:
            now = _monotonic()
            start = max(now, self._next.get(key, 0.0))
            self._next[key] = start + min_interval
        delay = start - _monotonic()
        if delay > 0:
            _sleep(delay)

    def allow_daily(self, key: str, cap: int) -> bool:
        """Increment today's counter for *key*; return False once *cap* is reached (0 = unlimited)."""
        if cap <= 0:
            return True
        today = _today()
        with self._lock:
            day, count = self._daily.get(key, (today, 0))
            if day != today:
                count = 0
            if count >= cap:
                self._daily[key] = (today, count)
                return False
            self._daily[key] = (today, count + 1)
            return True

    def reset(self) -> None:
        """Clear all state (used by tests)."""
        with self._lock:
            self._next.clear()
            self._daily.clear()


# Process-wide singleton + convenience wrappers.
LIMITER = RateLimiter()


def wait(key: str, min_interval: float) -> None:
    LIMITER.wait(key, min_interval)


def allow_daily(key: str, cap: int) -> bool:
    return LIMITER.allow_daily(key, cap)
