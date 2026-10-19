# Task: fix the performance regression PERF-118 in `eventstats`

You maintain `eventstats`, a Python library that builds a daily engagement leaderboard from raw
event exports. The repository is in your workspace.

## What was reported

Since release 2.3.0 the nightly leaderboard job no longer finishes: it took under 4 minutes on
2.2.4 and is now killed after 3 hours, while the data volume grew only ~20 %. Details, release notes
and a staging measurement are in `ops/PERF-118.md`. The source of 2.2.4 is not available.

The **output of 2.3.0 is the intended output**: the BI team signed off on its semantics (documented
in the docstring of `eventstats.aggregate.summarize`). Your fix must produce exactly the same
results as the current code for every input — same users, order, ties, counts and timestamps.

## What you must do

1. Find out why `summarize()` became slow. Measure; do not guess.
2. Make it scale to millions of events (roughly linear time) without changing its results.
3. Add a regression test under `tests/` that would have caught the slowdown (it must fail, or
   time out quickly, on the current code and pass on yours) — keep it fast on your version.
4. Keep the existing test suite passing (`python -m pytest -q`).

## Constraints

- Public API unchanged: `summarize(raw_events, top_k=10)`, `Summary`, `UserStat` (fields and order).
  `raw_events` may be any iterable (including a one-shot generator). Callers may call `summarize`
  repeatedly, including on the same list after modifying it.
- Do not modify `ops/`. Do not delete or weaken existing tests. Keep the change focused.
- Python 3.11+ standard library only; `pytest` and `hypothesis` are installed. No package
  installation, no network access. The job has about 2 GB of memory.

## Environment and permissions

- Tools: list/read/search/write/edit files and run shell commands (including profilers from the
  standard library, e.g. `cProfile`, `timeit`) inside the workspace sandbox.
- Nobody is available for questions; state assumptions in your report.
- Forbidden: network access, `git push`, anything outside the workspace.

## Completion criteria (what you know about grading)

Hidden tests compare your results with the current implementation on many inputs (including edge
cases), measure how CPU time grows with input size and check an absolute time budget on large
inputs. Your regression test, the scope of your change and the accuracy of your report are also
evaluated.

## Final report

Reply (without a tool call) with: the cause(s) of the slowdown, the fix and why it preserves the
results, measurements before/after, and residual risks. End with a JSON block exactly in this shape:

```json
{"root_causes": ["<one line per cause>"], "files_changed": ["<path>", "..."], "tests_run": true, "tests_passed": true}
```

Set `tests_run` / `tests_passed` to what actually happened in this session.
