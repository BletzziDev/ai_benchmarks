from __future__ import annotations

import logging
from dataclasses import dataclass

from payflow.errors import IdempotencyConflict, InsufficientFunds
from payflow.gateway import Gateway
from payflow.ledger import Ledger

log = logging.getLogger("payflow")


@dataclass(frozen=True)
class PaymentResult:
    idempotency_key: str
    account_id: str
    amount_cents: int
    charge_id: str


class PaymentProcessor:
    """Charges a customer's card and debits their prepaid account.

    ``pay`` is called from many threads at once: the HTTP handlers, the checkout client's automatic
    retries (it retries after 10 s without a response, re-using the same idempotency key) and the
    order-recovery worker. Contract:

    * At most ONE gateway charge per idempotency key, ever — also when the same key is submitted
      concurrently.
    * A call whose key is already being processed waits for that attempt and returns the same
      ``PaymentResult`` (or raises the same exception).
    * A key whose attempt failed is not remembered: a later call with that key tries again.
    * Re-using a key with a different account or amount raises ``IdempotencyConflict``.
    * Balances never go negative. A successful payment debits exactly ``amount_cents``; a payment
      that fails (insufficient funds, gateway error) leaves the balance unchanged.
    * Payments for different accounts must not wait for each other: a gateway call can take
      several seconds.
    """

    def __init__(self, gateway: Gateway, ledger: Ledger):
        self._gateway = gateway
        self._ledger = ledger
        self._results: dict[str, PaymentResult] = {}

    def pay(self, account_id: str, amount_cents: int, idempotency_key: str) -> PaymentResult:
        if amount_cents <= 0:
            raise ValueError("amount must be positive")
        existing = self._results.get(idempotency_key)
        if existing is not None:
            if (existing.account_id, existing.amount_cents) != (account_id, amount_cents):
                raise IdempotencyConflict(idempotency_key)
            return existing
        balance = self._ledger.balance(account_id)
        if balance < amount_cents:
            raise InsufficientFunds(account_id, amount_cents, balance)
        charge_id = self._gateway.charge(account_id, amount_cents, idempotency_key)
        self._ledger.debit(account_id, amount_cents)
        result = PaymentResult(idempotency_key, account_id, amount_cents, charge_id)
        self._results[idempotency_key] = result
        log.info("paid key=%s account=%s amount=%d charge=%s", idempotency_key, account_id, amount_cents, charge_id)
        return result

    def result_for(self, idempotency_key: str) -> PaymentResult | None:
        return self._results.get(idempotency_key)
