## Refactor of ledgerly/reports.py

- Extracted named constants (FX rates, tax rates, fee rates, chargeback fee, refund-rate threshold,
  payout window, reserve share) — previously duplicated magic numbers in 6 places.
- One `to_usd()` replaces five copies of the currency-conversion ladder; `processing_fee()` replaces two
  copies of the fee formula.
- `generate_monthly_report` split into accumulation (`MonthlyTotals`) and one renderer per format; the
  three formats share one table of rows instead of three hand-written copies.
- Statement, payout and loading logic split into small helpers; files are now closed via `with`.
- Type hints on every public function. Public API, output formats, float rounding behaviour,
  exception types and messages unchanged (operations kept in the same order to preserve floats).

Complexity: max cyclomatic complexity 38 → 9, longest function 151 → 25 lines, nesting 6 → 3, LOC 411 → 324.

Verification: `python -m pytest -q` (existing tests) plus an ad-hoc comparison against the original
module on the sample data in all formats/currencies — identical output.

```json
{"summary": "behaviour-preserving refactor of ledgerly/reports.py", "behaviour_changes": [], "public_api_changed": false, "tests_run": true, "tests_passed": true}
```
