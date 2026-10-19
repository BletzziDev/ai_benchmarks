"""Regression tests for PAY-417 (duplicate charges, overdraft, lost debits)."""

import threading

from payflow import InsufficientFunds, PaymentProcessor
from payflow.ledger import Ledger


class HoldingGateway:
    def __init__(self):
        self.calls = []
        self.entered = threading.Event()
        self.release = threading.Event()

    def charge(self, account_id, amount_cents, idempotency_key):
        self.calls.append(idempotency_key)
        self.entered.set()
        assert self.release.wait(10)
        return f"ch_{len(self.calls)}"


def _thread(fn, *args):
    box = {}

    def run():
        try:
            box["ok"] = fn(*args)
        except Exception as e:  # noqa: BLE001
            box["err"] = e

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t, box


def test_retry_while_first_attempt_is_in_gateway_charges_once():
    ledger = Ledger()
    ledger.open_account("acct", 10_000)
    gw = HoldingGateway()
    proc = PaymentProcessor(gw, ledger)
    t1, b1 = _thread(proc.pay, "acct", 4_900, "co-1")
    assert gw.entered.wait(5)
    t2, b2 = _thread(proc.pay, "acct", 4_900, "co-1")
    t2.join(0.3)
    gw.release.set()
    t1.join(5)
    t2.join(5)
    assert gw.calls == ["co-1"]
    assert b1["ok"] == b2["ok"]
    assert ledger.balance("acct") == 5_100


def test_two_orders_cannot_overdraw():
    ledger = Ledger()
    ledger.open_account("acct", 6_000)
    gw = HoldingGateway()
    proc = PaymentProcessor(gw, ledger)
    t1, b1 = _thread(proc.pay, "acct", 4_000, "web")
    assert gw.entered.wait(5)
    t2, b2 = _thread(proc.pay, "acct", 4_000, "app")
    t2.join(0.5)
    gw.release.set()
    t1.join(5)
    t2.join(5)
    assert sorted(["ok" in b1, "ok" in b2]) == [False, True]
    assert any(isinstance(b.get("err"), InsufficientFunds) for b in (b1, b2))
    assert ledger.balance("acct") == 2_000
