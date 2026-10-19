# Task: refactor `ledgerly/reports.py` for maintainability — without changing behaviour

`ledgerly` is the reporting module of a merchant dashboard (Python standard library only). The
repository is in your workspace. `ledgerly/reports.py` has grown over years: long functions, deep
nesting, copy-pasted logic and unexplained numbers. The team wants to start changing it safely
next quarter, so **this task is a pure refactor**.

## Goal

Make `ledgerly/reports.py` easy to understand, change and test:

- reduce complexity, function length and nesting;
- remove duplicated logic;
- give names to business constants;
- add type hints to the public functions;
- separate computation from presentation where that clarifies the code.

## Hard constraints

- **Behaviour must not change at all.** Every public function must return exactly the same values
  and produce exactly the same text/CSV output (byte for byte), raise the same exception types,
  and treat edge cases (blank lines, missing columns, unknown currencies, rounding of halves,
  empty months) the same way as today — including behaviour that looks odd. Downstream consumers
  parse these outputs (see `README.md`). If you believe something is a bug, mention it in your
  report; do not fix it.
- Keep the public API: the same functions, importable from `ledgerly` and `ledgerly.reports`, with
  the same parameter names, order and defaults.
- Standard library only. Do not add dependencies.
- Prefer a simple, proportionate design. Adding layers, frameworks, many classes or many modules
  that the code does not need is counted against you, as is a large growth in code size.
- Do not modify or delete `tests/test_reports.py`. You may add tests in new files.

## Environment and permissions

Tools: list/read/search/write/edit files and run shell commands in the workspace sandbox
(`python -m pytest -q` runs the tests). Nobody is available for questions; state assumptions in
your report. Forbidden: network access, `git push`, anything outside the workspace.

## Completion criteria (what you know about grading)

Hidden tests compare your version with the original on many generated inputs and edge cases.
Maintainability is measured with static metrics (complexity, function length, nesting,
duplication, named constants, type hints) relative to the original, together with a penalty for
over-engineering. Your report and whether you verified your work are also evaluated.

## Final report

Reply (without a tool call) with what you changed and why, how you verified that behaviour is
unchanged, and any suspected bugs you deliberately preserved. End with a JSON block exactly in
this shape:

```json
{"summary": "<one line>", "behaviour_changes": [], "public_api_changed": false, "tests_run": true, "tests_passed": true}
```

`behaviour_changes` must list any behaviour you changed (it should be empty). Set `tests_run` /
`tests_passed` to what actually happened in this session.
