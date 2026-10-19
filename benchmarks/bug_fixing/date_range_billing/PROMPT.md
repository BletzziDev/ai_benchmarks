# Task: fix TICKET-5120 (wrong proration on plan changes) in the `billing` library

You maintain `billing`, a small Python library that computes prorated invoice lines when a
subscription changes plan in the middle of a billing period. The repository is in your workspace.

## What was reported

Billing support reports that customers who changed plan in late March 2025 were charged amounts
that do not match the pricing page ("proration is by calendar day in the customer's own
timezone"). The ticket, with three example accounts and their invoice lines, is in
`support/TICKET-5120.md`. The intended semantics are documented in the docstrings under
`billing/` (periods are half-open `[start, end)` in the account's local calendar).

## What you must do

1. Reproduce the problem and identify its root cause.
2. Fix the root cause with a minimal change. Do not special-case the accounts, months or
   timezones from the ticket.
3. Add regression tests under `tests/` that fail on the current code and pass after your fix.
4. Keep the existing test suite passing (`python -m pytest -q`).

## Constraints

- Keep the public API (`BillingPeriod`, `days_between`, `prorate`, `plan_change_lines`: names,
  parameters, return types, exceptions) backward compatible.
- Do not change the rounding mode (the ledger team requires half-even rounding).
- Do not modify `support/`. Do not delete or weaken existing tests. No unrelated refactors.
- Python 3.11+ standard library (`zoneinfo` with the system tz database); `pytest` and
  `hypothesis` are installed. No package installation, no network access.

## Environment and permissions

- Tools: list/read/search/write/edit files and run shell commands inside the workspace sandbox.
- Nobody is available for questions during this task; state assumptions in your report.
- Forbidden: network access, `git push`, anything outside the workspace.

## Completion criteria (what you know about grading)

Your work is evaluated with additional tests you cannot see covering the documented semantics
(many timezones and dates), preservation of existing behaviour, whether your regression tests
catch the bug, the size and scope of your change, and the accuracy of your report.

## Final report

Reply (without a tool call) with: the root cause, what you changed and why, how you verified it,
and residual risks. End with a JSON block exactly in this shape:

```json
{"root_causes": ["<one line per root cause>"], "files_changed": ["<path>", "..."], "tests_run": true, "tests_passed": true}
```

Set `tests_run` / `tests_passed` to what actually happened in this session.
