from __future__ import annotations

import logging

from stockroom.cache import AvailabilityCache
from stockroom.clock import Clock, SystemClock
from stockroom.errors import InsufficientStock, ReservationNotFound, StockroomError
from stockroom.repository import InMemoryRepository, Reservation
from stockroom.skus import normalize_sku

log = logging.getLogger("stockroom")

DEFAULT_HOLD_SECONDS = 15 * 60


class InventoryService:
    """Reservations ("holds") taken during checkout, confirmed when payment succeeds.

    Invariants:
      * available(sku) == on_hand(sku) - quantity held by active, unexpired reservations
      * available(sku) >= 0 and on_hand(sku) >= 0 at all times
      * a hold can be confirmed at most once, and only while it is active and unexpired
    """

    def __init__(self, repo: InMemoryRepository | None = None, clock: Clock | None = None,
                 cache_ttl_seconds: float = 60.0):
        self._repo = repo or InMemoryRepository()
        self._clock = clock or SystemClock()
        self._cache = AvailabilityCache(self._clock, cache_ttl_seconds)

    # -- queries ---------------------------------------------------------------------------
    def available(self, sku: str) -> int:
        key = normalize_sku(sku)
        # INC-2291: never show negative availability; read through to the repository to avoid stale values
        return max(0, self._repo.on_hand(key) - self._repo.active_reserved(key))

    def on_hand(self, sku: str) -> int:
        return self._repo.on_hand(normalize_sku(sku))

    def reservation(self, reservation_id: str) -> Reservation:
        res = self._repo.get_reservation(reservation_id)
        if res is None:
            raise ReservationNotFound(reservation_id)
        return res

    # -- commands --------------------------------------------------------------------------
    def restock(self, sku: str, quantity: int) -> None:
        if quantity <= 0:
            raise ValueError("restock quantity must be positive")
        key = normalize_sku(sku)
        self._repo.set_on_hand(key, self._repo.on_hand(key) + quantity)
        self._cache.invalidate(sku)
        log.info("restock sku=%s qty=%d on_hand=%d", key, quantity, self._repo.on_hand(key))

    def reserve(self, sku: str, quantity: int, hold_seconds: float = DEFAULT_HOLD_SECONDS) -> Reservation:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        key = normalize_sku(sku)
        self.expire_due()
        available = self.available(key)
        if quantity > available:
            raise InsufficientStock(key, quantity, available)
        now = self._clock.now()
        res = self._repo.add_reservation(key, quantity, now, now + hold_seconds)
        self._cache.invalidate(key)
        log.info("reserve id=%s sku=%s qty=%d expires_at=%.0f", res.id, key, quantity, res.expires_at)
        return res

    def release(self, reservation_id: str) -> None:
        """Give a hold back (customer abandoned checkout). Releasing twice is a no-op."""
        res = self.reservation(reservation_id)
        if res.status != "active":
            return
        res.status = "released"
        self._cache.invalidate(res.sku)
        log.info("release id=%s sku=%s qty=%d", res.id, res.sku, res.quantity)

    def confirm(self, reservation_id: str) -> None:
        """Payment captured: turn the hold into a sale.

        Raises ReservationNotFound for unknown ids, ReservationExpired if the hold has lapsed,
        and StockroomError if the hold was released or already confirmed.
        """
        res = self.reservation(reservation_id)
        if res.status in ("released", "confirmed"):
            raise StockroomError(f"reservation {res.id} is {res.status}")
        res.status = "confirmed"
        self._repo.set_on_hand(res.sku, max(0, self._repo.on_hand(res.sku) - res.quantity))
        self._cache.invalidate(res.sku)
        log.info("confirm id=%s sku=%s qty=%d", res.id, res.sku, res.quantity)

    def expire_due(self) -> int:
        """Mark lapsed holds as expired. Called opportunistically and by a periodic job."""
        now = self._clock.now()
        expired = 0
        for res in self._repo.reservations():
            if res.status == "active" and res.expires_at <= now:
                res.status = "expired"
                expired += 1
                log.info("expire id=%s sku=%s qty=%d", res.id, res.sku, res.quantity)
        return expired
