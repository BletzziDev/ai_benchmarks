## Root causes (PAY-417)

1. **Check-then-act on the idempotency key.** `pay()` looked up `_results`, then called the
   gateway, and only stored the result afterwards. A client retry arriving while the first attempt
   was still inside the (slow) gateway call saw no result and charged again.
2. **Non-atomic balance check and debit.** The balance was checked before the gateway call and
   debited after it, so two concurrent payments on the same account both passed the check
   (6000 → -2000).
3. **Lost updates in `Ledger.debit/credit`.** Read-modify-write without synchronisation; under
   contention one debit overwrote another (reconciliation mismatch).

## Fix

- `PaymentProcessor` keeps an in-flight registry per key guarded by a short lock that is never held
  across the gateway call. Concurrent duplicates wait on the first attempt's event and get the same
  result or exception; failed attempts are removed so later retries work; conflicting reuse of an
  in-flight key raises `IdempotencyConflict`.
- Funds are reserved with `Ledger.debit_if_covered` (atomic check-and-debit) before charging and
  credited back if the gateway raises.
- `Ledger` methods are guarded by a lock.

Payments for different accounts never wait on each other; nothing blocking happens under a lock.

## Verification

`python -m pytest -q` (public suite + new `tests/test_pay_417.py`, which uses a gateway barrier to
force the failing interleavings deterministically) — all passing.

## Residual risks

- The registry is per process; multiple processor instances/hosts need a shared store (DB unique
  constraint on the key) for the same guarantee.
- A process crash during the gateway call leaves the outcome unknown; reconciliation against the
  gateway is still required.

```json
{"root_causes": ["idempotency check-then-act race", "non-atomic balance check/debit", "unsynchronised ledger read-modify-write"], "files_changed": ["payflow/processor.py", "payflow/ledger.py", "tests/test_pay_417.py"], "tests_run": true, "tests_passed": true}
```
