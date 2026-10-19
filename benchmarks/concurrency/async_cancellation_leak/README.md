# concurrency/async_cancellation_leak

Hard asyncio benchmark: connection-permit leaks under cancellation (handler and handshake),
duplicate processing of redelivered jobs, and a shutdown that neither cancels nor awaits stragglers.

```bash
benchmark run concurrency/async_cancellation_leak --model <label> --attempts 3
benchmark selftest async_cancellation_leak
```

Requirements: Python ≥ 3.11 (`asyncio.timeout`), `pytest`. No network, no `pytest-asyncio`.

| Path | Role |
|---|---|
| `PROMPT.md` | exact prompt |
| `EVAL.md` | ground truth, scoring, limits, observed selftests |
| `fixtures/workspace/` | `jobq` package, public tests, `docs/INCIDENT.md` |
| `tests/hidden/` | deterministic cancellation/duplicate/shutdown tests + seeded stress |
| `tests/public/` | benchmark copy of the public tests |
| `REFERENCE_SOLUTION/` | reference fix, regression tests, report |
| `selftest/` | decoys: handler-only fix, shutdown without await, pool reset symptom patch |
