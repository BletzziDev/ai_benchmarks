# AIBENCH-CANARY: 5a7d2c90-transfer-deadlock-hidden — never show this file to evaluated models.
"""Hidden tests for concurrency/transfer_deadlock.

Prefixes: test_dl_ (no deadlock), test_to_ (timeouts leave the bank usable), test_cons_ (atomicity and
conservation), test_par_ (parallelism, checked together with safety), test_pres_ (contract).
Accounts are opened in an order that differs from their sort order on purpose.
"""

import inspect
import random
import sys
import threading
import time

import pytest
from conftest import BlockingJournal, join_all, run_thread

from bankcore import Bank, InsufficientFunds, TransferTimeout, UnknownAccount
from bankcore.journal import MemoryJournal

NAMES = ["zeta", "alpha", "mike", "bravo", "yankee", "charlie"]


def make(journal=None, initial=1_000_000, names=NAMES):
    b = Bank(journal=journal) if journal is not None else Bank()
    for n in names:
        b.open(n, initial)
    return b


@pytest.fixture(autouse=True)
def fast_switching():
    old = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    yield
    sys.setswitchinterval(old)


def hammer(bank, pairs, per_thread, budget=8.0, with_totals=0, seed=0):
    """Run transfers concurrently; return (stuck_threads, successful_transfers, totals_seen)."""
    done = []
    dlock = threading.Lock()
    totals = []
    stop = threading.Event()

    def worker(i, src, dst):
        r = random.Random(seed * 1000 + i)
        mine = []
        for _ in range(per_thread):
            amt = r.randint(1, 3)
            try:
                bank.transfer(src, dst, amt)
                mine.append((src, dst, amt))
            except InsufficientFunds:
                pass
        with dlock:
            done.extend(mine)

    def monitor():
        while not stop.is_set():
            totals.append(bank.total())

    ts = [threading.Thread(target=worker, args=(i, s, d), daemon=True) for i, (s, d) in enumerate(pairs)]
    ms = [threading.Thread(target=monitor, daemon=True) for _ in range(with_totals)]
    for t in ts + ms:
        t.start()
    stuck = join_all(ts, budget)
    stop.set()
    stuck += join_all(ms, 3.0)
    return stuck, done, totals


# ----------------------------------------------------------------------------- deadlock freedom

def test_dl_opposite_directions():
    bank = make()
    pairs = [("zeta", "alpha"), ("alpha", "zeta")] * 4
    stuck, _, _ = hammer(bank, pairs, 3000)
    assert stuck == 0, f"{stuck} threads deadlocked on opposite-direction transfers"


def test_dl_three_way_cycle():
    bank = make()
    pairs = [("zeta", "alpha"), ("alpha", "mike"), ("mike", "zeta")] * 5
    stuck, _, _ = hammer(bank, pairs, 5000)
    assert stuck == 0, "deadlock in a three-account cycle"


def test_dl_totals_during_transfers():
    # total() must use a lock order compatible with transfer(); accounts are opened out of sort order.
    for rnd in range(3):
        bank = make()
        pairs = [("zeta", "alpha"), ("alpha", "zeta"), ("mike", "bravo"), ("bravo", "zeta")] * 2
        stuck, _, totals = hammer(bank, pairs, 3000, budget=6.0, with_totals=4, seed=rnd)
        assert stuck == 0, f"round {rnd}: total() deadlocks with concurrent transfers"
        assert totals and all(t == 6_000_000 for t in totals), "total() returned an inconsistent snapshot"


def test_dl_self_transfer_rejected_without_hanging():
    bank = make()
    t, box = run_thread(bank.transfer, "alpha", "alpha", 5)
    t.join(3)
    assert not t.is_alive(), "transfer from an account to itself hangs forever"
    assert isinstance(box.get("error"), ValueError)
    assert bank.balance("alpha") == 1_000_000
    bank.transfer("alpha", "zeta", 1)  # account still usable


# ----------------------------------------------------------------------------- timeouts

def test_to_timeout_on_second_lock_leaves_accounts_usable(journal):
    bank = make(journal, 1_000)
    journal.hold(lambda s, d, a: (s, d) == ("alpha", "zeta"))
    t1, b1 = run_thread(bank.transfer, "alpha", "zeta", 10)
    assert journal.entered.wait(5)
    # mike is free, zeta is held by t1: whichever order the implementation locks in, this times out
    t2, b2 = run_thread(bank.transfer, "mike", "zeta", 7, timeout=0.3)
    t2.join(5)
    assert not t2.is_alive(), "transfer with timeout did not honour its timeout"
    assert isinstance(b2.get("error"), TransferTimeout)
    assert b2["elapsed"] < 2.5
    journal.release()
    assert join_all([t1], 5) == 0
    # nothing may stay locked after a timeout
    t3, b3 = run_thread(bank.transfer, "mike", "bravo", 3)
    t4, b4 = run_thread(bank.transfer, "zeta", "mike", 2)
    assert join_all([t3, t4], 5) == 0, "an account stayed locked after a TransferTimeout"
    assert "error" not in b3 and "error" not in b4
    assert bank.balance("mike") == 1_000 - 3 + 2
    assert bank.balance("zeta") == 1_000 + 10 - 2
    assert bank.total() == 6_000


def test_to_timeout_on_first_lock(journal):
    bank = make(journal, 1_000)
    journal.hold(lambda s, d, a: (s, d) == ("bravo", "charlie"))
    t1, _ = run_thread(bank.transfer, "bravo", "charlie", 1)
    assert journal.entered.wait(5)
    t2, b2 = run_thread(bank.transfer, "charlie", "yankee", 5, timeout=0.2)
    t3, b3 = run_thread(bank.transfer, "alpha", "bravo", 5, timeout=0.2)
    assert join_all([t2, t3], 5) == 0
    assert isinstance(b2.get("error"), TransferTimeout) and isinstance(b3.get("error"), TransferTimeout)
    journal.release()
    assert join_all([t1], 5) == 0
    t4, b4 = run_thread(bank.transfer, "yankee", "alpha", 4)
    assert join_all([t4], 5) == 0 and "error" not in b4
    assert bank.total() == 6_000
    assert (bank.balance("charlie"), bank.balance("yankee"), bank.balance("alpha")) == (1_001, 996, 1_004)


def test_to_timeout_changes_nothing_and_is_not_journaled(journal):
    bank = make(journal, 500)
    journal.hold(lambda s, d, a: s == "zeta")
    t1, _ = run_thread(bank.transfer, "zeta", "alpha", 1)
    assert journal.entered.wait(5)
    with pytest.raises(TransferTimeout):
        bank.transfer("alpha", "mike", 50, timeout=0.1)
    journal.release()
    assert join_all([t1], 5) == 0
    assert bank.balance("mike") == 500
    assert ("alpha", "mike", 50) not in journal.entries


# ----------------------------------------------------------------------------- atomicity & conservation

@pytest.mark.parametrize("seed", range(3))
def test_cons_random_concurrent_transfers(seed):
    rng = random.Random(seed)
    journal = MemoryJournal()
    bank = make(journal, 2_000)
    pairs = [tuple(rng.sample(NAMES, 2)) for _ in range(12)]
    stuck, done, totals = hammer(bank, pairs, 400, with_totals=2, seed=seed)
    assert stuck == 0
    expected = {n: 2_000 for n in NAMES}
    for s, d, a in done:
        expected[s] -= a
        expected[d] += a
    actual = {n: bank.balance(n) for n in NAMES}
    assert actual == expected, "balances do not match the transfers that reported success"
    assert all(v >= 0 for v in actual.values())
    assert all(t == 12_000 for t in totals), "total() returned an inconsistent snapshot"
    assert sorted(journal.entries) == sorted(done), "journal and balances disagree"


def test_cons_blocking_transfer_waits_and_is_applied(journal):
    bank = make(journal, 100)
    journal.hold(lambda s, d, a: (s, d) == ("alpha", "zeta"))
    t1, _ = run_thread(bank.transfer, "alpha", "zeta", 10)
    assert journal.entered.wait(5)
    t2, b2 = run_thread(bank.transfer, "mike", "zeta", 20)  # no timeout: must wait, then apply
    t3, b3 = run_thread(bank.transfer, "zeta", "alpha", 30)
    time.sleep(0.3)
    journal.release()
    assert join_all([t1, t2, t3], 10) == 0
    assert "error" not in b2 and "error" not in b3
    assert (bank.balance("alpha"), bank.balance("zeta"), bank.balance("mike")) == (120, 100, 80)
    assert len(journal.entries) == 3


# ----------------------------------------------------------------------------- parallelism (+ safety)

def test_par_disjoint_transfers_not_blocked_by_slow_journal(journal):
    bank = make(journal, 1_000)
    journal.hold(lambda s, d, a: (s, d) == ("alpha", "zeta"))
    t1, _ = run_thread(bank.transfer, "alpha", "zeta", 1)
    assert journal.entered.wait(5)
    t_opp, b_opp = run_thread(bank.transfer, "zeta", "alpha", 2)  # must wait, not deadlock
    t2, b2 = run_thread(bank.transfer, "mike", "bravo", 5)
    t2.join(5)
    blocked = t2.is_alive()
    t3, b3 = run_thread(bank.transfer, "charlie", "zeta", 5, timeout=0.2)  # times out ...
    t3.join(5)
    t4, b4 = run_thread(bank.transfer, "charlie", "yankee", 5)  # ... and charlie must still be usable
    t4.join(5)
    blocked_after_timeout = t4.is_alive()
    journal.release()
    assert join_all([t1, t_opp, t2, t3, t4], 10) == 0
    assert not blocked, "a transfer between unrelated accounts waited for a slow journal write"
    assert isinstance(b3.get("error"), TransferTimeout)
    assert not blocked_after_timeout, "an account stayed locked after a TransferTimeout"
    assert "error" not in b_opp and "error" not in b2 and "error" not in b4
    assert bank.total() == 6_000


def test_par_total_waits_but_completes(journal):
    bank = make(journal, 1_000)
    journal.hold(lambda s, d, a: (s, d) == ("mike", "alpha"))
    t1, _ = run_thread(bank.transfer, "mike", "alpha", 100)
    assert journal.entered.wait(5)
    t2, b2 = run_thread(bank.total)
    t3, b3 = run_thread(bank.transfer, "alpha", "mike", 1)
    time.sleep(0.2)
    journal.release()
    assert join_all([t1, t2, t3], 10) == 0
    assert b2["result"] == 6_000


# ----------------------------------------------------------------------------- contract

def test_pres_api_and_errors():
    params = [p.name for p in inspect.signature(Bank.transfer).parameters.values()]
    assert params == ["self", "src", "dst", "amount", "timeout"]
    assert inspect.signature(Bank.transfer).parameters["timeout"].default is None
    bank = make(None, 10, ["b", "a"])
    with pytest.raises(InsufficientFunds):
        bank.transfer("a", "b", 11)
    with pytest.raises(UnknownAccount):
        bank.transfer("a", "nope", 1)
    with pytest.raises(ValueError):
        bank.transfer("a", "b", 0)
    with pytest.raises(ValueError):
        bank.open("a", 1)
    assert (bank.balance("a"), bank.balance("b"), bank.total()) == (10, 10, 20)


def test_pres_journal_records_each_transfer_once():
    j = MemoryJournal()
    bank = make(j, 50, ["y", "x"])
    bank.transfer("x", "y", 5)
    bank.transfer("y", "x", 7)
    with pytest.raises(InsufficientFunds):
        bank.transfer("x", "y", 999)
    assert j.entries == [("x", "y", 5), ("y", "x", 7)]


def test_pres_default_journal_and_open_order_independent():
    bank = Bank()
    for n in ["c", "a", "b"]:
        bank.open(n, 3)
    bank.transfer("c", "a", 1)
    bank.transfer("a", "b", 2)
    assert [bank.balance(n) for n in "abc"] == [2, 5, 2]
