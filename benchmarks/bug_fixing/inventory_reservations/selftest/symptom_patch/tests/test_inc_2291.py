from stockroom import InventoryService
from stockroom.clock import ManualClock


def test_availability_never_negative():
    clock = ManualClock()
    svc = InventoryService(clock=clock)
    svc.restock("MUG-BLK", 5)
    r = svc.reserve("MUG-BLK", 5, hold_seconds=60)
    clock.advance(61)
    svc.reserve("MUG-BLK", 2)
    svc.confirm(r.id)
    assert svc.available("MUG-BLK") >= 0
