## Root causes (OPS-2207)

1. **Permit leak on cancellation in `_attempt`.** Releases happened in `except TimeoutError` /
   `except Exception`; `asyncio.CancelledError` is a `BaseException`, so a cancelled job (user
   closing the dialog, deploy shutdown) never returned its connection.
2. **Permit leak in `ConnectionPool.acquire`.** The semaphore was taken and `in_use` incremented
   *before* the awaited handshake; cancellation during the handshake leaked the permit.
3. **No de-duplication of in-flight jobs.** `submit` only checked completed results, so a queue
   redelivery of a running/pending job started a second, concurrent run → double export.
4. **Unsafe shutdown.** `shutdown` waited `grace` seconds and returned, leaving unfinished tasks
   running (writing after "shutdown") and their connections checked out.

## Fix

- `_attempt` releases in `finally`; `acquire` releases the permit if the handshake is interrupted.
- `submit` keeps an id → task map of in-flight jobs and returns the existing task; the entry is
  removed when that task finishes, so failed/cancelled jobs can be resubmitted.
- `shutdown` cancels stragglers after the grace period and awaits them (`gather(...,
  return_exceptions=True)`) so their cleanup runs before it returns.

## Verification

`python -m pytest -q` — public tests plus `tests/test_ops_2207.py` (deterministic: events gate the
handler/handshake, cancellation at a known await point) all pass.

## Residual risks

- De-duplication is per process; redeliveries to another worker still need an idempotent sink.
- A handler that swallows `CancelledError` can still delay shutdown indefinitely.

```json
{"root_causes": ["CancelledError bypasses release in _attempt", "acquire leaks permit when cancelled during connect", "submit does not de-duplicate in-flight jobs", "shutdown neither cancels nor awaits stragglers"], "files_changed": ["jobq/runner.py", "jobq/pool.py", "tests/test_ops_2207.py"], "tests_run": true, "tests_passed": true}
```
