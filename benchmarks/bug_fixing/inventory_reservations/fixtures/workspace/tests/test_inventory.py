import pytest

from stockroom import InsufficientStock, InventoryService, StockroomError
from stockroom.clock import ManualClock


@pytest.fixture
def clock():
    return ManualClock()


@pytest.fixture
def svc(clock):
    s = InventoryService(clock=clock)
    s.restock("TSHIRT-RED-M", 10)
    return s


def test_reserve_reduces_availability(svc):
    svc.reserve("TSHIRT-RED-M", 3)
    assert svc.available("TSHIRT-RED-M") == 7
    assert svc.on_hand("TSHIRT-RED-M") == 10


def test_insufficient_stock(svc):
    with pytest.raises(InsufficientStock):
        svc.reserve("TSHIRT-RED-M", 11)


def test_release_returns_stock(svc):
    r = svc.reserve("TSHIRT-RED-M", 4)
    svc.release(r.id)
    assert svc.available("TSHIRT-RED-M") == 10
    svc.release(r.id)  # idempotent
    assert svc.available("TSHIRT-RED-M") == 10


def test_confirm_deducts_on_hand(svc):
    r = svc.reserve("TSHIRT-RED-M", 2)
    svc.confirm(r.id)
    assert svc.on_hand("TSHIRT-RED-M") == 8
    assert svc.available("TSHIRT-RED-M") == 8


def test_cannot_confirm_twice(svc):
    r = svc.reserve("TSHIRT-RED-M", 2)
    svc.confirm(r.id)
    with pytest.raises(StockroomError):
        svc.confirm(r.id)


def test_sku_normalization_on_reads(svc):
    assert svc.available(" tshirt-red-m ") == 10
