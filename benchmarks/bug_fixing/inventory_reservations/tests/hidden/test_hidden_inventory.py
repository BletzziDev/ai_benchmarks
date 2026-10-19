# AIBENCH-CANARY: 7f3c1a52-inventory-reservations-hidden — this file must never be shown to evaluated models.
"""Hidden evaluation tests for bug_fixing/inventory_reservations.

Groups (selected by name prefix in benchmark.yaml):
  test_root_*  - each root cause of INC-2291
  test_inv_*   - model-based property test of the documented invariants
  test_pres_*  - preservation of existing behaviour and public API
"""

import inspect

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from stockroom import InsufficientStock, InventoryService, ReservationExpired, ReservationNotFound, StockroomError
from stockroom.clock import ManualClock


@pytest.fixture
def clock():
    return ManualClock()


# ----------------------------------------------------------------------------- root causes

def test_root_restock_non_canonical_sku_invalidates(clock):
    svc = InventoryService(clock=clock)
    assert svc.available("LAMP-01") == 0
    svc.restock(" lamp-01", 12)
    assert svc.available("LAMP-01") == 12
    svc.restock("lamp--01", 3)
    assert svc.available("lamp-01") == 15


def test_root_expire_due_frees_units_immediately(clock):
    svc = InventoryService(clock=clock, cache_ttl_seconds=3600)
    svc.restock("MUG-BLK", 5)
    svc.reserve("MUG-BLK", 5, hold_seconds=900)
    assert svc.available("MUG-BLK") == 0
    clock.advance(900)
    svc.expire_due()
    assert svc.available("MUG-BLK") == 5


def test_root_reserve_after_expiry_succeeds_within_cache_ttl(clock):
    svc = InventoryService(clock=clock, cache_ttl_seconds=3600)
    svc.restock("MUG-BLK", 5)
    svc.reserve("MUG-BLK", 5, hold_seconds=900)
    assert svc.available("MUG-BLK") == 0
    clock.advance(901)
    r = svc.reserve("MUG-BLK", 2)
    assert r.quantity == 2


def test_root_confirm_expired_raises(clock):
    svc = InventoryService(clock=clock)
    svc.restock("MUG-BLK", 5)
    late = svc.reserve("MUG-BLK", 5, hold_seconds=900)
    clock.advance(901)
    svc.expire_due()
    with pytest.raises(ReservationExpired):
        svc.confirm(late.id)
    assert svc.on_hand("MUG-BLK") == 5


def test_root_confirm_lapsed_unswept_raises(clock):
    svc = InventoryService(clock=clock)
    svc.restock("MUG-BLK", 5)
    r = svc.reserve("MUG-BLK", 1, hold_seconds=60)
    clock.advance(60)
    with pytest.raises(ReservationExpired):
        svc.confirm(r.id)
    assert svc.on_hand("MUG-BLK") == 5


def test_root_incident_replay_never_oversells(clock):
    svc = InventoryService(clock=clock)
    svc.restock("MUG-BLK", 5)
    r1 = svc.reserve("MUG-BLK", 5, hold_seconds=900)
    clock.advance(901)
    r3 = svc.reserve("MUG-BLK", 2)
    with pytest.raises(ReservationExpired):
        svc.confirm(r1.id)
    assert svc.available("MUG-BLK") == 3
    svc.confirm(r3.id)
    assert svc.on_hand("MUG-BLK") == 3
    assert svc.available("MUG-BLK") == 3


# ----------------------------------------------------------------------------- invariants (model-based)

SKUS = ["MUG-BLK", "LAMP-01"]
SPELLINGS = {"MUG-BLK": ["MUG-BLK", "mug-blk", " Mug-Blk "], "LAMP-01": ["LAMP-01", "lamp-01", "lamp--01 "]}

op = st.one_of(
    st.tuples(st.just("restock"), st.sampled_from(SKUS), st.integers(1, 6), st.integers(0, 2)),
    st.tuples(st.just("reserve"), st.sampled_from(SKUS), st.integers(1, 6), st.sampled_from([30, 120, 900])),
    st.tuples(st.just("release"), st.integers(0, 20)),
    st.tuples(st.just("confirm"), st.integers(0, 20)),
    st.tuples(st.just("advance"), st.sampled_from([1, 29, 31, 60, 119, 600, 901])),
    st.tuples(st.just("expire_due"),),
    st.tuples(st.just("read"), st.sampled_from(SKUS), st.integers(0, 2)),
)


@settings(max_examples=250, deadline=None, derandomize=True, database=None,
          suppress_health_check=[HealthCheck.too_slow])
@given(st.lists(op, max_size=40))
def test_inv_model_based(ops):
    clock = ManualClock()
    svc = InventoryService(clock=clock, cache_ttl_seconds=60)
    on_hand = {s: 0 for s in SKUS}
    holds = []  # dicts: id, sku, qty, expires, status

    def held(sku):
        now = clock.now()
        return sum(h["qty"] for h in holds if h["sku"] == sku and h["status"] == "active" and h["expires"] > now)

    for o in ops:
        kind = o[0]
        now = clock.now()
        for h in holds:
            if h["status"] == "active" and h["expires"] <= now:
                h["status"] = "expired"
        if kind == "restock":
            _, sku, qty, sp = o
            svc.restock(SPELLINGS[sku][sp], qty)
            on_hand[sku] += qty
        elif kind == "reserve":
            _, sku, qty, hold = o
            avail = on_hand[sku] - held(sku)
            if qty > avail:
                with pytest.raises(InsufficientStock):
                    svc.reserve(sku, qty, hold_seconds=hold)
            else:
                r = svc.reserve(sku, qty, hold_seconds=hold)
                holds.append({"id": r.id, "sku": sku, "qty": qty, "expires": now + hold, "status": "active"})
        elif kind in ("release", "confirm"):
            if not holds:
                continue
            h = holds[o[1] % len(holds)]
            if kind == "release":
                svc.release(h["id"])
                if h["status"] == "active":
                    h["status"] = "released"
            else:
                if h["status"] == "active":
                    svc.confirm(h["id"])
                    h["status"] = "confirmed"
                    on_hand[h["sku"]] -= h["qty"]
                elif h["status"] == "expired":
                    with pytest.raises(ReservationExpired):
                        svc.confirm(h["id"])
                else:
                    with pytest.raises(StockroomError):
                        svc.confirm(h["id"])
        elif kind == "advance":
            clock.advance(o[1])
        elif kind == "expire_due":
            svc.expire_due()
        elif kind == "read":
            _, sku, sp = o
            assert svc.available(SPELLINGS[sku][sp]) == on_hand[sku] - held(sku)
        for sku in SKUS:
            expected = on_hand[sku] - held(sku)
            assert svc.on_hand(sku) == on_hand[sku] >= 0
            assert svc.available(sku) == expected >= 0


# ----------------------------------------------------------------------------- preservation

def _params(name):
    return [(p.name, p.default) for p in inspect.signature(getattr(InventoryService, name)).parameters.values()]


def test_pres_public_api_signatures():
    E = inspect.Parameter.empty
    assert _params("reserve") == [("self", E), ("sku", E), ("quantity", E), ("hold_seconds", 900)]
    assert _params("confirm") == [("self", E), ("reservation_id", E)]
    assert _params("release") == [("self", E), ("reservation_id", E)]
    assert _params("restock") == [("self", E), ("sku", E), ("quantity", E)]
    assert _params("available") == [("self", E), ("sku", E)]
    assert _params("expire_due") == [("self", E)]
    names = [n for n, _ in _params("__init__")]
    assert names[:4] == ["self", "repo", "clock", "cache_ttl_seconds"]


def test_pres_cache_still_serves_repeated_reads(clock):
    svc = InventoryService(clock=clock)
    svc.restock("MUG-BLK", 5)
    svc.reserve("MUG-BLK", 1)
    svc.available("MUG-BLK")
    before = svc._cache.computations
    for _ in range(20):
        svc.available("MUG-BLK")
    assert svc._cache.computations == before, "availability cache no longer serves repeated reads"


def test_pres_release_idempotent_and_unknown_ids(clock):
    svc = InventoryService(clock=clock)
    svc.restock("MUG-BLK", 3)
    r = svc.reserve("MUG-BLK", 3)
    svc.release(r.id)
    svc.release(r.id)
    assert svc.available("MUG-BLK") == 3
    with pytest.raises(ReservationNotFound):
        svc.release("R999999")
    with pytest.raises(ReservationNotFound):
        svc.confirm("R999999")


def test_pres_confirm_twice_and_released_raise_stockroom_error(clock):
    svc = InventoryService(clock=clock)
    svc.restock("MUG-BLK", 3)
    a = svc.reserve("MUG-BLK", 1)
    b = svc.reserve("MUG-BLK", 1)
    svc.confirm(a.id)
    with pytest.raises(StockroomError):
        svc.confirm(a.id)
    svc.release(b.id)
    with pytest.raises(StockroomError):
        svc.confirm(b.id)
    assert not isinstance(StockroomError("x"), ReservationExpired)


def test_pres_validation_errors(clock):
    svc = InventoryService(clock=clock)
    with pytest.raises(ValueError):
        svc.restock("MUG-BLK", 0)
    with pytest.raises(ValueError):
        svc.reserve("MUG-BLK", 0)
    with pytest.raises(ValueError):
        svc.available("not a sku!")


def test_pres_insufficient_stock_details(clock):
    svc = InventoryService(clock=clock)
    svc.restock("mug-blk", 2)
    with pytest.raises(InsufficientStock) as ei:
        svc.reserve("MUG-BLK", 3)
    assert (ei.value.sku, ei.value.requested, ei.value.available) == ("MUG-BLK", 3, 2)
