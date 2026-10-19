# concurrency/payment_double_charge

Hard concurrency benchmark (Python `threading`). The agent fixes duplicate charges, overdrafts and
lost debits in a payment processor with idempotency keys, under a documented contract that also
requires unrelated accounts not to be serialised behind slow gateway calls.

```bash
benchmark run concurrency/payment_double_charge --model <label> --attempts 3
benchmark selftest payment_double_charge
```

Requirements: Python ≥ 3.11, `pytest`, `hypothesis`. No network. The hidden tests start up to ~25
threads at once; the sandbox raises `max_processes` because RLIMIT_NPROC counts threads per uid
across concurrently running sandboxes.

| Path | Role |
|---|---|
| `PROMPT.md` | exact prompt |
| `EVAL.md` | ground truth, scoring, detection limits |
| `fixtures/workspace/` | `payflow` package, public tests, `docs/INCIDENT.md` |
| `tests/hidden/` | deterministic-interleaving, progress, stress and contract tests (+ `conftest.py` with the barrier gateway) |
| `tests/public/` | benchmark copy of the public tests |
| `REFERENCE_SOLUTION/` | reference fix, regression tests, report |
| `selftest/` | decoys: global lock, ledger-only lock, reject-duplicates |

Manual reproduction: copy `fixtures/workspace` and `REFERENCE_SOLUTION/files/*` into a temp dir, add
`tests/hidden/` as `h/` and run `python -m pytest -q h`.
