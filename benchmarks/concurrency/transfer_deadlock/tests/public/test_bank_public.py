import threading

import pytest

from bankcore import Bank, InsufficientFunds, UnknownAccount


@pytest.fixture
def bank():
    b = Bank()
    b.open("alice", 100)
    b.open("bob", 50)
    return b


def test_transfer_moves_money(bank):
    bank.transfer("alice", "bob", 30)
    assert bank.balance("alice") == 70
    assert bank.balance("bob") == 80
    assert bank.total() == 150


def test_insufficient_funds_changes_nothing(bank):
    with pytest.raises(InsufficientFunds):
        bank.transfer("bob", "alice", 51)
    assert (bank.balance("alice"), bank.balance("bob")) == (100, 50)


def test_unknown_account(bank):
    with pytest.raises(UnknownAccount):
        bank.transfer("alice", "carol", 1)


def test_concurrent_one_direction():
    bank = Bank()
    bank.open("alice", 1_000)
    bank.open("bob", 0)

    def work():
        for _ in range(100):
            bank.transfer("alice", "bob", 1)

    ts = [threading.Thread(target=work) for _ in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert bank.balance("alice") == 600
    assert bank.balance("bob") == 400
    assert bank.total() == 1_000
