from __future__ import annotations

from typing import Callable

from stockroom.clock import Clock


class AvailabilityCache:
    """Read-through cache for availability numbers.

    Availability is read on every product page view, so it is cached for ``ttl_seconds``.
    Writers MUST invalidate the affected SKU; the TTL is only a safety net.
    """

    def __init__(self, clock: Clock, ttl_seconds: float = 60.0):
        self._clock = clock
        self._ttl = ttl_seconds
        self._entries: dict[str, tuple[float, int]] = {}
        self.computations = 0

    def get(self, key: str, compute: Callable[[], int]) -> int:
        hit = self._entries.get(key)
        now = self._clock.now()
        if hit is not None and now - hit[0] < self._ttl:
            return hit[1]
        value = compute()
        self.computations += 1
        self._entries[key] = (now, value)
        return value

    def invalidate(self, key: str) -> None:
        self._entries.pop(key, None)

    def clear(self) -> None:
        self._entries.clear()
