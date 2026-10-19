## Root causes (TRSY-88)

1. **Lock-order deadlock.** `transfer()` locked `src` then `dst`; concurrent A→B and B→A
   transfers each held one lock and waited for the other forever.
2. **`total()` used a different lock order** (dict insertion order), so it could deadlock with
   transfers even if transfers were ordered consistently; this froze the monitoring endpoint.
3. **Lock leak on timeout.** When the second `acquire(timeout=...)` failed, `TransferTimeout` was
   raised without releasing the first lock, freezing that account permanently.
4. **Self-transfer** acquired the same non-reentrant lock twice and hung (spec: `ValueError`).

## Fix

- One global lock order (account id) used by `transfer()` and `total()`.
- The second acquisition happens inside `try/finally` that releases the first lock; a single
  deadline covers both acquisitions, so `timeout` bounds the total wait.
- `src == dst` raises `ValueError` before touching locks.
- Locks are still per account, so transfers between disjoint accounts run in parallel even while a
  journal write is slow.

## Verification

`python -m pytest -q`: public tests plus `tests/test_trsy_88.py` (self-transfer, forced timeout with a
parking journal, opposite-direction hammering) — all passing.

## Residual risks

- Lock ordering by id assumes ids are totally ordered strings (they are).
- `total()` locks every account; with many accounts it briefly pauses transfers (acceptable for
  monitoring every few seconds; a versioned snapshot would avoid it).
- A journal that blocks forever still blocks the two accounts involved (callers with `timeout`
  get `TransferTimeout`).

```json
{"root_causes": ["inconsistent lock order in transfer", "total() lock order differs from transfer", "first lock leaked on TransferTimeout", "self-transfer re-acquires non-reentrant lock"], "files_changed": ["bankcore/bank.py", "tests/test_trsy_88.py"], "tests_run": true, "tests_passed": true}
```
