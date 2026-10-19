# Task: fix leaked connections, duplicate exports and unsafe shutdown in `jobq` (OPS-2207)

You maintain `jobq`, a small asyncio job runner used by the export service: each job attempt
checks out a connection from a bounded `ConnectionPool`, runs a handler under a per-attempt
timeout, and retries timed-out attempts. The incident is described in `docs/INCIDENT.md`: the pool
drains over time (especially after cancellations and deploys), some exports run twice, and jobs
keep running after `shutdown()` returned.

The contract the service relies on is the docstring of `JobRunner` (`jobq/runner.py`) together
with the docstring of `ConnectionPool` (`jobq/pool.py`). That is the specification you are graded
against.

## What you must do

1. Find the root cause of every symptom in the incident.
2. Fix them so the documented contract holds for any interleaving of submissions, redeliveries,
   timeouts, cancellations (at any await point) and shutdowns.
3. Add regression tests under `tests/` that reproduce the problems deterministically (control the
   schedule with events rather than sleeps where you can) and pass after your fix. Tests must not
   hang if the code under test is broken.
4. Keep the existing tests passing (`python -m pytest -q`).

## Constraints

- Keep the public API compatible: `ConnectionPool(size, connect=None)`, `acquire`, `release`,
  `available`, `in_use`, `size`; `JobRunner(pool, handler, *, max_attempts=3,
  attempt_timeout=5.0)`, `submit(job) -> asyncio.Task` (a regular method), `result(job_id)`,
  `async shutdown(grace) -> ShutdownSummary`; `Job`, `JobFailed`, `RunnerClosed`.
- Do not hide leaks by resetting or recreating the pool, and do not suppress cancellation.
- Python 3.11+ standard library only; `pytest` and `hypothesis` are installed (no `pytest-asyncio`;
  use `asyncio.run` in tests). No package installation, no network.
- Change only what the incident requires.

## Environment and permissions

- Tools: list/read/search/write/edit files and run shell commands in the workspace sandbox.
- Nobody is available for questions; state assumptions in your report.
- Forbidden: network access, `git push`, anything outside the workspace.

## Completion criteria (what you know about grading)

Hidden tests cancel jobs at specific await points (handler, connection handshake, pool queue,
between retries), redeliver jobs while they are pending/running/retrying, shut down with
stragglers, and run seeded randomised mixes, checking connection accounting, single execution per
job and shutdown guarantees. Your regression tests, the scope/size of the change and the honesty of
your report are also evaluated.

## Final report

Reply (without a tool call) with: root causes, your fix and why it is safe at every await point,
how you verified it, and residual risks. End with:

```json
{"root_causes": ["<one line each>"], "files_changed": ["<path>", "..."], "tests_run": true, "tests_passed": true}
```

Report `tests_run` / `tests_passed` truthfully for this session.
