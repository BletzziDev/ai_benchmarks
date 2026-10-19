# Task: make `bankcore` transfers deadlock-free (incident TRSY-88)

You maintain `bankcore`, an in-memory account ledger used by a treasury service that calls it from
a pool of ~40 worker threads, while a monitoring endpoint polls `Bank.total()`. The incident is
described in `docs/INCIDENT.md`: the workers periodically hang, accounts become permanently frozen
after `TransferTimeout`s, and a transfer from an account to itself never returned.

The guarantees the service relies on are documented in the docstring of `Bank`
(`bankcore/bank.py`). That docstring is the specification you are graded against.

## What you must do

1. Find the root cause of each symptom in the incident.
2. Fix them so that every documented guarantee holds under any mix of concurrent calls:
   atomic transfers, conservation and consistent `total()` snapshots, no deadlocks, `timeout`
   honoured without side effects, parallel transfers between disjoint accounts, `ValueError` for
   self-transfers.
3. Add regression tests under `tests/` that reproduce the problems and pass after your fix. Tests
   must terminate even when the code under test deadlocks (use timeouts on joins).
4. Keep the existing tests passing (`python -m pytest -q`).

## Constraints

- Keep the public API compatible (`Bank(journal=None)`, `open`, `balance`, `transfer(src, dst,
  amount, timeout=None)`, `total`, the exception types, `bankcore.journal`).
- A transfer must still be applied when the caller passes no timeout and the accounts are merely
  busy — it must not be silently skipped.
- Do not serialise unrelated transfers behind a single bank-wide lock: the journal can be slow.
- Python 3.11+ standard library only; `pytest` and `hypothesis` are installed. No package
  installation, no network.
- Change only what the incident requires.

## Environment and permissions

- Tools: list/read/search/write/edit files and run shell commands in the workspace sandbox.
- Nobody is available for questions; state assumptions in your report.
- Forbidden: network access, `git push`, anything outside the workspace.

## Completion criteria (what you know about grading)

Hidden tests hammer the bank from many threads (opposite directions, cycles, concurrent
`total()`), force contention deterministically through a slow journal, exercise timeouts, and check
conservation, atomicity, liveness and parallelism. Your regression tests, the scope/size of the
change and the honesty of your report are also evaluated.

## Final report

Reply (without a tool call) with: root causes, why your design cannot deadlock (state the lock
order or protocol), how you verified it, and residual risks. End with:

```json
{"root_causes": ["<one line each>"], "files_changed": ["<path>", "..."], "tests_run": true, "tests_passed": true}
```

Report `tests_run` / `tests_passed` truthfully for this session.
