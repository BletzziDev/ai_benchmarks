# concurrency/transfer_deadlock

Medium concurrency benchmark (Python `threading`): lock-order deadlocks between transfers and
`total()`, a lock leaked on `TransferTimeout`, and a self-transfer hang — fixed without a global
lock and without dropping transfers.

```bash
benchmark run concurrency/transfer_deadlock --model <label> --attempts 3
benchmark selftest transfer_deadlock
```

Requirements: Python ≥ 3.11, `pytest`. No network. Hidden tests are bounded by join deadlines, so
a deadlocking submission costs ~1–2 minutes of evaluation instead of hanging.

| Path | Role |
|---|---|
| `PROMPT.md` | exact prompt |
| `EVAL.md` | ground truth, scoring, detection limits, observed selftests |
| `fixtures/workspace/` | `bankcore` package, public tests, `docs/INCIDENT.md` |
| `tests/hidden/` | stress + deterministic (parking journal) tests |
| `tests/public/` | benchmark copy of the public tests |
| `REFERENCE_SOLUTION/` | reference fix, regression tests, report |
| `selftest/` | decoys: global lock, try-lock-and-drop, transfer-only ordering |
