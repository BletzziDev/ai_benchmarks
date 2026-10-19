"""Regression tests for TRSY-88 (deadlocks, frozen accounts after timeouts, self-transfer hang)."""

import threading

import pytest

from bankcore import Bank, TransferTimeout


class ParkingJournal:
    """Parks one transfer inside record() (while it holds its locks) until released."""

    def __init__(self, src, dst):
        self.key = (src, dst)
        self.entered = threading.Event()
        self.go = threading.Event()

    def record(self, src, dst, amount):
        if (src, dst) == self.key:
            self.entered.set()
            assert self.go.wait(10)


def _bank(journal=None):
    bank = Bank(journal=journal)
    for name in ("zeta", "alpha", "mike"):
        bank.open(name, 100)
    return bank


def _run(fn, *args, **kw):
    box = {}

    def target():
        try:
            fn(*args, **kw)
            box["ok"] = True
        except Exception as e:  # noqa: BLE001
            box["err"] = e

    t = threading.Thread(target=target, daemon=True)
    t.start()
    return t, box


def test_self_transfer_is_rejected_instead_of_hanging():
    bank = _bank()
    t, box = _run(bank.transfer, "alpha", "alpha", 1)
    t.join(2)
    assert not t.is_alive()
    assert isinstance(box["err"], ValueError)


def test_timeout_does_not_leave_the_first_account_locked():
    j = ParkingJournal("alpha", "zeta")
    bank = _bank(j)
    t1, _ = _run(bank.transfer, "alpha", "zeta", 1)
    assert j.entered.wait(5)
    with pytest.raises(TransferTimeout):
        bank.transfer("mike", "zeta", 1, timeout=0.2)
    j.go.set()
    t1.join(5)
    t2, box = _run(bank.transfer, "mike", "alpha", 1)
    t2.join(2)
    assert not t2.is_alive(), "mike stayed locked after the timeout"
    assert box.get("ok")


def test_opposite_transfers_do_not_deadlock():
    bank = _bank()
    bank.transfer("zeta", "alpha", 50)

    def work(src, dst):
        for _ in range(2000):
            bank.transfer(src, dst, 1)
            bank.transfer(dst, src, 1)

    ts = [threading.Thread(target=work, args=p, daemon=True) for p in [("zeta", "alpha"), ("alpha", "zeta")] * 3]
    for t in ts:
        t.start()
    for t in ts:
        t.join(10)
    assert not any(t.is_alive() for t in ts)
    assert bank.total() == 300
