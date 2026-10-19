# AIBENCH-CANARY: 3e9b0d14-payment-double-charge-hidden — never show this file to evaluated models.
"""Hidden tests for concurrency/payment_double_charge.

Prefixes: test_dup_ (one charge per key, deterministic interleavings), test_bal_ (balances under
concurrency), test_prog_ (progress/parallelism/liveness), test_pres_ (sequential contract),
test_stress_ (randomised high-contention stress with invariant checks).
"""

import inspect
import random
import sys
import threading
import time

import pytest
from conftest import ControlledGateway, run_thread

from payflow import GatewayError, IdempotencyConflict, InsufficientFunds, PaymentProcessor, PaymentResult
from payflow.ledger import Ledger

JOIN = 15


def make(gw, accounts):
    ledger = Ledger()
    for a, bal in accounts.items():
        ledger.open_account(a, bal)
    return PaymentProcessor(gw, ledger), ledger


def finish(*threads):
    for t in threads:
        t.join(JOIN)
    assert not any(t.is_alive() for t in threads), "a payment thread is stuck (deadlock or missed wake-up)"


# ----------------------------------------------------------------------------- one charge per key

def test_dup_concurrent_retry_while_first_attempt_in_gateway(gw):
    proc, ledger = make(gw, {"acct-7731": 10_000})
    gw.hold(lambda a, m, k: True)
    t1, b1 = run_thread(proc.pay, "acct-7731", 4_900, "co-88412")
    assert gw.entered.wait(5)
    t2, b2 = run_thread(proc.pay, "acct-7731", 4_900, "co-88412")  # client retry
    time.sleep(0.3)
    gw.release()
    finish(t1, t2)
    assert "error" not in b1 and "error" not in b2, (b1, b2)
    assert len(gw.calls_for("co-88412")) == 1, "the same idempotency key was charged twice"
    assert b1["result"] == b2["result"]
    assert ledger.balance("acct-7731") == 5_100


def test_dup_many_concurrent_duplicates(gw):
    proc, ledger = make(gw, {"a": 100_000})
    gw.hold(lambda a, m, k: True)
    first, _ = run_thread(proc.pay, "a", 700, "k1")
    assert gw.entered.wait(5)
    others = [run_thread(proc.pay, "a", 700, "k1") for _ in range(12)]
    time.sleep(0.3)
    gw.release()
    finish(first, *[t for t, _ in others])
    assert len(gw.calls_for("k1")) == 1
    ids = {box["result"].charge_id for _, box in others}
    assert len(ids) == 1 and "error" not in _
    assert ledger.balance("a") == 100_000 - 700


def test_dup_waiter_gets_same_exception_and_key_can_retry_later(gw):
    proc, ledger = make(gw, {"a": 10_000})
    gw.fail_keys.add("k-fail")
    gw.hold(lambda a, m, k: True)
    t1, b1 = run_thread(proc.pay, "a", 1_000, "k-fail")
    assert gw.entered.wait(5)
    t2, b2 = run_thread(proc.pay, "a", 1_000, "k-fail")
    time.sleep(0.3)
    gw.release()
    finish(t1, t2)
    assert isinstance(b1.get("error"), GatewayError)
    assert isinstance(b2.get("error"), GatewayError), "a concurrent duplicate must share the failed outcome"
    assert len(gw.calls_for("k-fail")) == 1
    assert ledger.balance("a") == 10_000
    gw.fail_keys.clear()
    gw.hold(None)
    r = proc.pay("a", 1_000, "k-fail")  # failures are not remembered
    assert isinstance(r, PaymentResult)
    assert len(gw.calls_for("k-fail")) == 2
    assert ledger.balance("a") == 9_000


def test_dup_conflict_detected_while_in_flight(gw):
    proc, _ = make(gw, {"a": 10_000})
    gw.hold(lambda a, m, k: True)
    t1, b1 = run_thread(proc.pay, "a", 1_000, "k")
    assert gw.entered.wait(5)
    t2, b2 = run_thread(proc.pay, "a", 2_000, "k")
    t2.join(5)
    gw.release()
    finish(t1, t2)
    assert isinstance(b2.get("error"), IdempotencyConflict)
    assert len(gw.calls_for("k")) == 1


# ----------------------------------------------------------------------------- balances

def test_bal_concurrent_payments_cannot_overdraw(gw):
    proc, ledger = make(gw, {"acct-1290": 6_000})
    gw.hold(lambda a, m, k: k == "web")
    t1, b1 = run_thread(proc.pay, "acct-1290", 4_000, "web")
    assert gw.entered.wait(5)
    t2, b2 = run_thread(proc.pay, "acct-1290", 4_000, "app")
    t2.join(1.0)  # may block (per-account serialisation) or finish (reservation) — both fine
    gw.release()
    finish(t1, t2)
    outcomes = sorted("ok" if "result" in b else type(b["error"]).__name__ for b in (b1, b2))
    assert outcomes == ["InsufficientFunds", "ok"], outcomes
    assert ledger.balance("acct-1290") == 2_000
    assert len(gw.calls) == 1


def test_bal_failed_gateway_restores_balance_under_concurrency(gw):
    proc, ledger = make(gw, {"a": 5_000})
    gw.fail_keys.add("bad")
    gw.hold(lambda a, m, k: k == "bad")
    t1, b1 = run_thread(proc.pay, "a", 3_000, "bad")
    assert gw.entered.wait(5)
    gw.release()
    finish(t1)
    assert isinstance(b1.get("error"), GatewayError)
    assert ledger.balance("a") == 5_000
    assert proc.pay("a", 5_000, "good").amount_cents == 5_000
    assert ledger.balance("a") == 0


def test_bal_no_lost_debits_under_contention():
    from payflow.gateway import FakeGateway

    old = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        for rnd in range(3):
            ledger = Ledger()
            ledger.open_account("a", 1_000_000)
            proc = PaymentProcessor(FakeGateway(), ledger)
            n_threads, per = 16, 1000
            barrier = threading.Barrier(n_threads)

            def worker(i):
                barrier.wait()
                for j in range(per):
                    proc.pay("a", 1, f"r{rnd}-t{i}-{j}")

            ts = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(n_threads)]
            for t in ts:
                t.start()
            finish(*ts)
            assert ledger.balance("a") == 1_000_000 - n_threads * per, f"lost debits in round {rnd}"
    finally:
        sys.setswitchinterval(old)


# ----------------------------------------------------------------------------- progress
# Each progress test also checks safety in the same schedule (an in-flight duplicate must not be
# charged again): progress is only credited together with correctness.

def test_prog_other_accounts_not_blocked_by_slow_gateway(gw):
    proc, _ = make(gw, {"slow": 10_000, "fast": 10_000})
    gw.hold(lambda a, m, k: a == "slow")
    t1, b1 = run_thread(proc.pay, "slow", 100, "k-slow")
    assert gw.entered.wait(5)
    t_dup, b_dup = run_thread(proc.pay, "slow", 100, "k-slow")  # retry of the slow payment
    t2, b2 = run_thread(proc.pay, "fast", 100, "k-fast")
    t2.join(5)
    blocked = t2.is_alive()
    gw.release()
    finish(t1, t2, t_dup)
    assert not blocked, "a payment for another account waited for an unrelated slow gateway call"
    assert "result" in b2
    assert len(gw.calls_for("k-slow")) == 1
    assert b_dup.get("result") == b1.get("result") is not None


def test_prog_other_keys_same_account_not_deadlocked(gw):
    proc, ledger = make(gw, {"a": 10_000})
    gw.hold(lambda a, m, k: k == "k1")
    t1, b1 = run_thread(proc.pay, "a", 100, "k1")
    assert gw.entered.wait(5)
    t_dup, b_dup = run_thread(proc.pay, "a", 100, "k1")
    t2, b2 = run_thread(proc.pay, "a", 100, "k2")
    t2.join(1.0)
    gw.release()
    finish(t1, t2, t_dup)
    assert "result" in b2 and "result" in b1
    assert len(gw.calls_for("k1")) == 1
    assert b_dup.get("result") == b1["result"]
    assert ledger.balance("a") == 9_800


def test_prog_replay_of_completed_key_is_fast_while_other_key_in_flight(gw):
    proc, _ = make(gw, {"a": 10_000})
    done = proc.pay("a", 100, "old")
    gw.hold(lambda a, m, k: k == "new")
    t1, b1 = run_thread(proc.pay, "a", 100, "new")
    assert gw.entered.wait(5)
    t_dup, b_dup = run_thread(proc.pay, "a", 100, "new")
    t2, b2 = run_thread(proc.pay, "a", 100, "old")
    t2.join(5)
    blocked = t2.is_alive()
    gw.release()
    finish(t1, t2, t_dup)
    assert not blocked, "replaying a completed key waited for an unrelated in-flight payment"
    assert b2["result"] == done
    assert len(gw.calls_for("new")) == 1
    assert len(gw.calls_for("old")) == 1


# ----------------------------------------------------------------------------- sequential contract

def test_pres_sequential_contract():
    from payflow.gateway import FakeGateway

    gw = FakeGateway()
    proc, ledger = make(gw, {"a": 5_000})
    r = proc.pay("a", 1_000, "x")
    assert proc.pay("a", 1_000, "x") == r
    assert proc.result_for("x") == r
    assert proc.result_for("missing") is None
    with pytest.raises(IdempotencyConflict):
        proc.pay("b-other", 1_000, "x")
    with pytest.raises(InsufficientFunds) as ei:
        proc.pay("a", 4_001, "y")
    assert (ei.value.account_id, ei.value.requested, ei.value.balance) == ("a", 4_001, 4_000)
    with pytest.raises(ValueError):
        proc.pay("a", 0, "z")
    assert ledger.balance("a") == 4_000
    assert len(gw.charges) == 1


def test_pres_api():
    names = [p.name for p in inspect.signature(PaymentProcessor.pay).parameters.values()]
    assert names == ["self", "account_id", "amount_cents", "idempotency_key"]
    init = [p.name for p in inspect.signature(PaymentProcessor.__init__).parameters.values()]
    assert init[:3] == ["self", "gateway", "ledger"]
    for m in ("open_account", "balance", "debit", "credit"):
        assert callable(getattr(Ledger, m))


def test_pres_ledger_debit_credit_still_work():
    led = Ledger()
    led.open_account("a", 10)
    assert led.debit("a", 3) == 7
    assert led.credit("a", 5) == 12
    with pytest.raises(ValueError):
        led.open_account("a", 1)


# ----------------------------------------------------------------------------- stress + invariants

class JitterGateway:
    def __init__(self, seed):
        self.rng = random.Random(seed)
        self.calls = []
        self.lock = threading.Lock()

    def charge(self, account_id, amount_cents, key):
        with self.lock:
            self.calls.append((account_id, amount_cents, key))
            n = len(self.calls)
            fail = self.rng.random() < 0.1
            delay = self.rng.random() * 0.002
        time.sleep(delay)
        if fail:
            raise GatewayError("random decline")
        return f"ch_{n}"


@pytest.mark.parametrize("seed", range(6))
def test_stress_invariants(seed):
    old = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        rng = random.Random(seed)
        accounts = {f"acct-{i}": rng.randint(2_000, 6_000) for i in range(4)}
        gw = JitterGateway(seed)
        proc, ledger = make(gw, dict(accounts))
        keys = [(f"key-{i}", rng.choice(list(accounts)), rng.randint(100, 1_500)) for i in range(60)]
        outcomes = {}
        olock = threading.Lock()
        barrier = threading.Barrier(24)

        def worker(w):
            r = random.Random(seed * 100 + w)
            barrier.wait()
            for _ in range(25):
                key, acct, amt = r.choice(keys)
                try:
                    res = proc.pay(acct, amt, key)
                    with olock:
                        outcomes.setdefault(key, set()).add(res.charge_id)
                except (InsufficientFunds, GatewayError):
                    pass

        ts = [threading.Thread(target=worker, args=(w,), daemon=True) for w in range(24)]
        for t in ts:
            t.start()
        finish(*ts)
        for key, ids in outcomes.items():
            assert len(ids) == 1, f"{key} returned different charges {ids}"
        successful = {}
        for key, acct, amt in keys:
            r = proc.result_for(key)
            if r is not None:
                successful[key] = r
        # at most one successful gateway charge per key
        ok_charges = {}
        for (acct, amt, key) in gw.calls:
            ok_charges.setdefault(key, 0)
        for key, r in successful.items():
            assert r.charge_id in {f"ch_{i + 1}" for i, c in enumerate(gw.calls) if c[2] == key}
        per_key_calls = {}
        for c in gw.calls:
            per_key_calls[c[2]] = per_key_calls.get(c[2], 0) + 1
        for key, r in successful.items():
            # a key may be retried after a failed attempt, but never charged again after success
            idx = [i for i, c in enumerate(gw.calls) if c[2] == key]
            ok_idx = int(r.charge_id.split("_")[1]) - 1
            assert ok_idx == idx[-1], f"{key} was charged again after it had succeeded"
        for acct, initial in accounts.items():
            spent = sum(r.amount_cents for r in successful.values() if r.account_id == acct)
            bal = ledger.balance(acct)
            assert bal >= 0, f"{acct} went negative"
            assert bal == initial - spent, f"{acct}: balance {bal} != {initial} - {spent} (money not conserved)"
    finally:
        sys.setswitchinterval(old)
