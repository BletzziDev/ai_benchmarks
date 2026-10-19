import pytest

from payflow import GatewayError, IdempotencyConflict, InsufficientFunds, PaymentProcessor
from payflow.gateway import FakeGateway
from payflow.ledger import Ledger


@pytest.fixture
def env():
    ledger = Ledger()
    ledger.open_account("acct-1", 10_000)
    gw = FakeGateway()
    return PaymentProcessor(gw, ledger), gw, ledger


def test_pay_debits_and_charges(env):
    proc, gw, ledger = env
    r = proc.pay("acct-1", 2_500, "order-1")
    assert r.amount_cents == 2_500 and r.charge_id.startswith("ch_")
    assert ledger.balance("acct-1") == 7_500
    assert len(gw.charges) == 1


def test_replay_returns_same_result(env):
    proc, gw, ledger = env
    a = proc.pay("acct-1", 1_000, "order-2")
    b = proc.pay("acct-1", 1_000, "order-2")
    assert a == b
    assert len(gw.charges) == 1
    assert ledger.balance("acct-1") == 9_000


def test_conflicting_reuse_of_key(env):
    proc, _, _ = env
    proc.pay("acct-1", 1_000, "order-3")
    with pytest.raises(IdempotencyConflict):
        proc.pay("acct-1", 2_000, "order-3")


def test_insufficient_funds(env):
    proc, gw, ledger = env
    with pytest.raises(InsufficientFunds):
        proc.pay("acct-1", 10_001, "order-4")
    assert ledger.balance("acct-1") == 10_000
    assert gw.charges == []


def test_gateway_failure_leaves_balance(env):
    proc, _, ledger = env

    class Declining:
        def charge(self, account_id, amount_cents, idempotency_key):
            raise GatewayError("card declined")

    proc._gateway = Declining()
    with pytest.raises(GatewayError):
        proc.pay("acct-1", 1_000, "order-5")
    assert ledger.balance("acct-1") == 10_000
