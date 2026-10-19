# bug_fixing/date_range_billing

Medium, single-cause bug-fixing benchmark (Python, `zoneinfo`). Plan-change proration loses a day for
billing periods that contain a spring-forward DST transition. The agent must find the cause from a
support ticket, fix it generally (both hemispheres, both transition directions) and prove it with
regression tests.

```bash
benchmark run bug_fixing/date_range_billing --model <label> --attempts 3
benchmark selftest date_range_billing
```

Requires Python ≥ 3.11 with a system tz database, `pytest`, `hypothesis`. No network.

| Path | Role |
|---|---|
| `PROMPT.md` | exact task prompt |
| `EVAL.md` | scoring, critical failures, observed selftests, limitations |
| `benchmark.yaml` | configuration |
| `fixtures/workspace/` | the `billing` repository + `support/TICKET-5120.md` |
| `tests/hidden/` | hidden tests (root / invariants / preservation) |
| `tests/public/` | benchmark copy of the original public tests |
| `REFERENCE_SOLUTION/` | reference fix, regression tests, report |
| `selftest/` | decoys: ceil patch, special-casing, false claim |

Manual reproduction: copy `fixtures/workspace` somewhere, overlay `REFERENCE_SOLUTION/files`, copy
`tests/hidden/test_hidden_billing.py` next to it and run `python -m pytest -q`.
