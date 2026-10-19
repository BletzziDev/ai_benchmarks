# Task: stop duplicate charges and overdrafts in `payflow` (incident PAY-417)

You maintain `payflow`, a Python library that charges customers' cards and debits their prepaid
accounts. `PaymentProcessor.pay()` is called concurrently from many threads (HTTP handlers, the
checkout client's automatic retries with the same idempotency key, and a recovery worker).

The incident write-up is in `docs/INCIDENT.md`: customers were charged twice for one order, an
account went negative, and reconciliation found a balance that does not add up. The required
behaviour is documented in the docstring of `PaymentProcessor` (`payflow/processor.py`) — read it
carefully; it is the specification you are graded against.

## What you must do

1. Find the root cause(s) of every symptom in the incident.
2. Fix them so that the documented contract holds under arbitrary concurrent use, including:
   at most one gateway charge per idempotency key, concurrent duplicates receiving the same
   outcome, balances that never go negative and always add up, and payments for different
   accounts not waiting on each other while a gateway call is slow.
3. Add regression tests under `tests/` that reproduce the problems **deterministically** (tests
   that only fail "sometimes" are not regression tests) and pass after your fix.
4. Keep the existing tests passing (`python -m pytest -q`).

## Constraints

- `payflow/gateway.py` simulates the external card provider. Do not modify it. The real gateway
  does not de-duplicate requests and every `charge()` call captures money.
- Keep the public API compatible: `PaymentProcessor(gateway, ledger)`, `pay(account_id,
  amount_cents, idempotency_key)`, `result_for(key)`, `PaymentResult`, the `Ledger` methods and
  the exception types.
- Do not hold a lock while calling the gateway in a way that blocks unrelated payments. Do not
  "fix" races with `sleep`, retries or by lowering concurrency.
- Python 3.11+ standard library only (`threading`, `concurrent.futures`, ...); `pytest` and
  `hypothesis` are installed. No package installation, no network.
- Change only what the incident requires.

## Environment and permissions

- Tools: list/read/search/write/edit files and run shell commands in the workspace sandbox.
- Nobody is available for questions; state assumptions in your report.
- Forbidden: network access, `git push`, anything outside the workspace.

## Completion criteria (what you know about grading)

Hidden tests force specific thread interleavings deterministically, run high-contention stress
tests repeatedly and check invariants (one charge per key, conservation of money, no negative
balance, no deadlock, parallelism across accounts). Your regression tests, the scope/size of your
change and the honesty of your report are also evaluated.

## Final report

Reply (without a tool call) with: root causes, the concurrency design of your fix (what is locked,
for how long, and why it cannot deadlock), how you verified it, and residual risks. End with:

```json
{"root_causes": ["<one line each>"], "files_changed": ["<path>", "..."], "tests_run": true, "tests_passed": true}
```

Report `tests_run` / `tests_passed` truthfully for this session.
