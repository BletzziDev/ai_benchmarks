from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Iterator


@dataclass
class Reservation:
    id: str
    sku: str  # canonical SKU
    quantity: int
    created_at: float
    expires_at: float
    status: str = "active"  # active | released | expired | confirmed


class InMemoryRepository:
    """Storage for on-hand quantities and reservations. Keys are canonical SKUs."""

    def __init__(self) -> None:
        self._on_hand: dict[str, int] = {}
        self._reservations: dict[str, Reservation] = {}
        self._ids = itertools.count(1)

    def on_hand(self, sku: str) -> int:
        return self._on_hand.get(sku, 0)

    def set_on_hand(self, sku: str, quantity: int) -> None:
        if quantity < 0:
            raise ValueError("on-hand quantity cannot be negative")
        self._on_hand[sku] = quantity

    def add_reservation(self, sku: str, quantity: int, created_at: float, expires_at: float) -> Reservation:
        res = Reservation(f"R{next(self._ids):06d}", sku, quantity, created_at, expires_at)
        self._reservations[res.id] = res
        return res

    def get_reservation(self, reservation_id: str) -> Reservation | None:
        return self._reservations.get(reservation_id)

    def reservations(self) -> Iterator[Reservation]:
        return iter(list(self._reservations.values()))

    def active_reserved(self, sku: str) -> int:
        return sum(r.quantity for r in self._reservations.values() if r.sku == sku and r.status == "active")
