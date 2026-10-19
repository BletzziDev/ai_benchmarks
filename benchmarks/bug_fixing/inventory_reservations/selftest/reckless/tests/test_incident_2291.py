"""Regression tests for INC-2291 (stale availability and overselling after hold expiry)."""

import pytest

from stockroom import InventoryService, ReservationExpired
from stockroom.clock import ManualClock


@pytest.fixture
def clock():
    return ManualClock()


def test_expired_hold_is_returned_to_availability_immediately(clock):
    svc = InventoryService(clock=clock)
    svc.restock("MUG-BLK", 5)
    svc.reserve("MUG-BLK", 5, hold_seconds=900)
    assert svc.available("MUG-BLK") == 0  # cached
    clock.advance(901)
    assert svc.expire_due() == 1
    assert svc.available("MUG-BLK") == 5
    svc.reserve("MUG-BLK", 2)  # must not raise InsufficientStock


def test_confirm_after_expiry_raises_and_does_not_oversell(clock):
    svc = InventoryService(clock=clock)
    svc.restock("MUG-BLK", 5)
    late = svc.reserve("MUG-BLK", 5, hold_seconds=900)
    clock.advance(901)
    other = svc.reserve("MUG-BLK", 2)
    with pytest.raises(ReservationExpired):
        svc.confirm(late.id)  # late payment webhook
    svc.confirm(other.id)
    assert svc.on_hand("MUG-BLK") == 3
    assert svc.available("MUG-BLK") == 3


def test_confirm_of_lapsed_hold_raises_even_before_sweep(clock):
    svc = InventoryService(clock=clock)
    svc.restock("MUG-BLK", 5)
    r = svc.reserve("MUG-BLK", 1, hold_seconds=60)
    clock.advance(61)
    with pytest.raises(ReservationExpired):
        svc.confirm(r.id)
    assert svc.on_hand("MUG-BLK") == 5


def test_restock_with_non_canonical_sku_invalidates_cache(clock):
    svc = InventoryService(clock=clock)
    assert svc.available("LAMP-01") == 0  # cached as 0
    svc.restock("lamp-01 ", 12)
    assert svc.available("LAMP-01") == 12
