from __future__ import annotations

import logging
import threading
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


class _InFlight:
    def __init__(self, account_id: str, amount_cents: int):
        self.account_id = account_id
        self.amount_cents = amount_cents
        self.done = threading.Event()
        self.result: PaymentResult | None = None
        self.error: BaseException | None = None


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

    Concurrency design: one short-lived lock guards the key registry (``_results`` + in-flight
    attempts); it is never held during the gateway call. Funds are reserved with an atomic
    check-and-debit before charging and refunded if the gateway fails, so concurrent payments on the
    same account cannot overdraw it.
    """

    def __init__(self, gateway: Gateway, ledger: Ledger):
        self._gateway = gateway
        self._ledger = ledger
        self._results: dict[str, PaymentResult] = {}
        self._inflight: dict[str, _InFlight] = {}
        self._keys_lock = threading.Lock()

    def pay(self, account_id: str, amount_cents: int, idempotency_key: str) -> PaymentResult:
        if amount_cents <= 0:
            raise ValueError("amount must be positive")
        with self._keys_lock:
            existing = self._results.get(idempotency_key)
            if existing is not None:
                if (existing.account_id, existing.amount_cents) != (account_id, amount_cents):
                    raise IdempotencyConflict(idempotency_key)
                return existing
            attempt = self._inflight.get(idempotency_key)
            owner = attempt is None
            if owner:
                attempt = self._inflight[idempotency_key] = _InFlight(account_id, amount_cents)
            elif (attempt.account_id, attempt.amount_cents) != (account_id, amount_cents):
                raise IdempotencyConflict(idempotency_key)
        if not owner:
            attempt.done.wait()
            if attempt.error is not None:
                raise attempt.error
            assert attempt.result is not None
            return attempt.result
        try:
            result = self._execute(account_id, amount_cents, idempotency_key)
        except BaseException as e:
            attempt.error = e
            with self._keys_lock:
                del self._inflight[idempotency_key]
            attempt.done.set()
            raise
        attempt.result = result
        with self._keys_lock:
            self._results[idempotency_key] = result
            del self._inflight[idempotency_key]
        attempt.done.set()
        return result

    def _execute(self, account_id: str, amount_cents: int, idempotency_key: str) -> PaymentResult:
        debited, balance = self._ledger.debit_if_covered(account_id, amount_cents)
        if not debited:
            raise InsufficientFunds(account_id, amount_cents, balance)
        try:
            charge_id = self._gateway.charge(account_id, amount_cents, idempotency_key)
        except BaseException:
            self._ledger.credit(account_id, amount_cents)  # release the reservation
            raise
        log.info("paid key=%s account=%s amount=%d charge=%s", idempotency_key, account_id, amount_cents, charge_id)
        return PaymentResult(idempotency_key, account_id, amount_cents, charge_id)

    def result_for(self, idempotency_key: str) -> PaymentResult | None:
        with self._keys_lock:
            return self._results.get(idempotency_key)
