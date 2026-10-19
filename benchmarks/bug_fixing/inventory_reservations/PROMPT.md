# Task: fix incident INC-2291 in the `stockroom` inventory service

You are the engineer on call for `stockroom`, a small Python library that manages inventory
"holds" (reservations) taken during checkout. The repository is in your workspace.

## What was reported

Two reports were merged into incident INC-2291:

1. **Support:** customers are told an item is *out of stock* although units are free — notably
   right after a hold expires and right after the warehouse restocks through the admin tool.
2. **Finance:** the admin dashboard briefly showed *negative* availability for `MUG-BLK`, and the
   warehouse shipped more `MUG-BLK` units than it had received that day.

An excerpt of the production logs is in `logs/incident-2291.log`. The intended behaviour and the
invariants of the service are documented in the docstrings of `stockroom/service.py`.

## What you must do

1. Reproduce the problem(s) and find the root cause(s). Distinguish symptoms from causes; the
   two reports may or may not share a cause.
2. Fix the root cause(s) with the smallest change that restores the documented behaviour and
   invariants. Do not paper over symptoms (for example by clamping numbers or disabling caching).
3. Add regression tests under `tests/` that fail on the current code and pass after your fix.
4. Make sure the existing test suite still passes (`python -m pytest -q`).

## Constraints

- Keep the public API of `InventoryService` (method names, parameters, defaults, exception types)
  backward compatible. Keep the availability cache: availability is read on every product page.
- Do not modify `logs/` and do not delete or weaken existing tests.
- Only change what the incident requires; unrelated refactors are counted against you.
- Python 3.11+ standard library only; `pytest` and `hypothesis` are installed. You cannot install
  packages and there is no network access.

## Environment and permissions

- Tools: list/read/search/write/edit files and run shell commands inside the workspace sandbox.
- You may run any tests and scripts. Nobody is available to answer questions during this task;
  make reasonable decisions and state your assumptions in the report.
- Forbidden: network access, `git push`, touching anything outside the workspace.

## Completion criteria (what you know about grading)

Your work is evaluated with additional tests you cannot see that check the documented behaviour
and invariants, the preservation of existing behaviour, whether your regression tests catch the
bug, the size and scope of your change, and the accuracy of your report.

## Final report

When finished, reply (without a tool call) with a short report: root cause(s), what you changed
and why, how you verified it, and residual risks. End the report with a JSON block exactly in
this shape:

```json
{"root_causes": ["<one line per root cause>"], "files_changed": ["<path>", "..."], "tests_run": true, "tests_passed": true}
```

Set `tests_run` / `tests_passed` to what actually happened in this session.
