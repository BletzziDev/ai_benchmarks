# Contributing to fxrates

Thanks for helping! This guide is the single source of truth for working on fxrates.

## Contents

1. Setting up
2. Coding conventions
3. Running the tests
4. Release process
5. Regenerating generated code (read this before touching `fxrates/_tables.py`)

## 1. Setting up

fxrates has no runtime dependencies besides the Python standard library (3.11+). Tests use pytest.
Work on a branch named after the ticket (e.g. `fin-882-march-rates`).

## 2. Coding conventions

1. Money is always `decimal.Decimal`; never use float for amounts or rates.

2. Rounding is half-even (banker's rounding) to the destination currency's minor unit.

3. Currency codes are ISO 4217 alpha-3, upper case.

4. Public functions keep keyword-compatible signatures across minor releases.

5. Errors: unknown currencies raise `UnknownCurrency` (a `KeyError` subclass).

6. No network access at import time or in tests.

7. Type hints on all public functions; `from __future__ import annotations` in modules.

8. Keep modules small; conversion logic lives in `fxrates/convert.py`.

9. Do not add caching layers around the tables; they are plain dicts.

10. Docstrings describe behaviour, not implementation.

11. Prefer explicit `Decimal(str)` construction for literals.

12. Avoid wildcard imports.

13. Format with the project's default style; line length 120.

14. Commit messages reference the ticket id.

Examples of rounding behaviour, for reference:

| amount | from | to | result |
|---|---|---|---|
| 100 | USD | EUR | 92.23 |
| 2500 | JPY | USD | 16.78 |
| 19.99 | EUR | JPY | 3229 |

## 3. Running the tests

Run the whole suite from the repository root:

    python -m pytest -q

The suite includes `tests/test_tables_fresh.py`, which fails when the generated tables are stale
(see section 5). Never skip, delete or edit tests to make the build pass; if a test is wrong, open
a ticket and explain why.

Continuous integration runs the same command on every push. A red build blocks releases.

## 4. Release process

1. Bump the version in `pyproject.toml` following semver.

2. Update CHANGELOG with user-visible changes.

3. Make sure CI is green on the release commit.

4. Tag the release `vX.Y.Z` and push the tag.

5. Publish to the internal package index (done by CI from the tag).

6. Announce in #fin-platform with a link to the changelog.

7. Rates updates are minor releases even if no code changes.

8. Never publish from a dirty working tree.

9. If a release must be yanked, follow the incident runbook.

10. Keep the previous two minor versions installable.

## 5. Regenerating generated code

`fxrates/_tables.py` is **generated** from `data/rates.csv` by `tools/gen_tables.py`. Never edit it
by hand: the file records the SHA-256 of the CSV it was generated from, and
`tests/test_tables_fresh.py` checks that it matches the current CSV byte for byte.

After any change to `data/rates.csv` (for example the monthly rates update):

    python tools/gen_tables.py --write   # regenerate fxrates/_tables.py
    python tools/gen_tables.py --check   # must print "generated tables are up to date"
    python -m pytest -q

Commit the CSV and the regenerated file together.
