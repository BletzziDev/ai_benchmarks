# EVAL — code_quality/legacy_report_refactor (v1.0.0)

<!-- AIBENCH-CANARY: 9d41b6e3-legacy-report-refactor-eval — never include this file in model inputs. -->

## What this benchmark measures

Whether a model can improve the maintainability of real-looking legacy code **without changing a
single byte of behaviour**, and whether it does so proportionately (no rewrites into frameworks).
Competencies: reading code for implicit behaviour (float operation order, odd edge cases, error
ordering), safe incremental refactoring, verification discipline, design restraint.

## The fixture (hidden facts)

`ledgerly/reports.py` (418 lines): 7 public functions; max cyclomatic complexity 38, mean 17.9,
longest function 151 lines, nesting depth 6, 21% duplicated 30-token shingles, 67 magic numbers,
no type hints. Traps that a careless refactor breaks:

- float results depend on accumulation and operation order (`fees += amt*0.029 + 0.30`,
  `net -= amt + 15.0`, conversion `x / r` after summing in USD); "fixing" rounding to `Decimal`
  changes outputs on half-cent values;
- `summarize_by_category` creates empty entries for `fee` transactions; customers with only fees
  appear in the top-customer list as `(unknown)`/0.00;
- unknown transaction currencies raise only for transactions inside the filtered month/customer/range;
- `load_transactions` counts blank lines in line numbers, accepts short rows, upper-cases currency;
- payouts are clamped at 0 and `fee`/`chargeback` fees belong to the window of the transaction.

## Checks

| Check | What it does |
|---|---|
| `hidden` (`test_equiv_*`) | Hypothesis (derandomized, 150 examples × 5 properties) compares every public function with `tests/hidden/legacy_original.py` (frozen original): equal return values / byte-identical files / same exception type; plus CSV-loading edge cases, error cases and half-cent rounding cases (9 test functions, 20 test ids with parametrisation) |
| `hidden` (`test_api_*`) | parameter names/defaults/kinds identical; functions importable from `ledgerly` and `ledgerly.reports` |
| `public` | original public tests (benchmark copy) |
| `quality` | `tests/grader.py`: AST/tokenize metrics of `ledgerly/**` vs the original (formulas in the grader docstring) |
| `scope`, `process`, `report` | change scope, protected files, test runs in trace, final JSON report |

## Scoring (weights fixed before any run)

| Criterion | Weight | Metric → [0,1] |
|---|---|---|
| behaviour_preserved | 30 | `hidden.equiv_pass_rate` |
| public_api_preserved | 5 | `hidden.api_pass_rate` |
| public_suite_passes | 5 | `public.pass_rate` |
| complexity_reduced | 12 | `0.5·lin(max_cc: orig→10) + 0.5·lin(mean_cc: orig→3.5)` |
| functions_shorter | 8 | `lin(longest function: orig→40 lines)` |
| nesting_reduced | 7 | `lin(max nesting: orig→3)`, `elif` chains count as one level |
| duplication_removed | 10 | `lin(dup ratio: orig→0.03)` |
| constants_named | 5 | `lin(magic numbers in function bodies: orig→0)`; 0, 1, −1, 2, 100 allowed |
| type_hints | 6 | share of fully annotated public functions |
| proportionate_design | 12 | `min(lin(LOC ratio: 2.0→1.35), lin(new classes: 12→4), lin(new modules: 8→3))` |

**Pass** requires score ≥ 75, all equivalence and API tests passing, and
`proportionate_design ≥ 0.5`, with no critical failure.

### Critical failures

| Id | Condition | Effect |
|---|---|---|
| `behaviour_changed` | any equivalence test fails | cap 40 |
| `third_party_dependency` | a non-stdlib import added to the package | cap 50 |
| `tests_weakened` | `tests/test_reports.py` or `data/**` changed | cap 50 |
| `false_test_claim` | claims tests ran, none in trace | cap 40 |

## Validation of the grader (selftests, observed)

| Case | Expected | Observed | Static evidence |
|---|---|---|---|
| reference (constants, `to_usd`, `MonthlyTotals` + per-format renderers, helpers) | pass, ≥ 88 | 97.2, pass | max_cc 38→9, longest fn 151→25, nesting 6→3, dup 0.21→0.06, magic 67→12, LOC ×0.79 |
| noop | fail, ≤ 55 | 52.0, fail | unchanged |
| cosmetic (docstring, type hints, renames) | fail, ≤ 65 | 58.2, fail | only typing improves |
| behaviour_change (reference + half-up `Decimal` rounding) | fail, ≤ 40, `behaviour_changed` | 40.0 (92.7 before cap), fail | 3 equivalence tests fail |
| over_engineered (reference + interfaces/strategies/factories/services, 6 modules, +34 classes) | fail, ≤ 80 | 76.7, fail (gate: proportionate_design = 0) | dup 0.31, LOC ×1.63 |

The noop scores ~52 because behaviour/API/public criteria (40 points) and proportionate design (12)
are trivially satisfied; the pass threshold and gates exclude it. The over-engineered decoy is
stopped by the design gate, not by the score alone — intended, since its behaviour is correct.

## Limitations

- Static metrics are proxies. A model can game them (e.g. splitting functions mechanically) without
  making code clearer; a rubric (`RUBRIC`-style human/LLM review) would complement them and is not
  included in v1.0.0.
- Equivalence is sampled (≈750 generated cases + targeted edge cases), not proven. Exception
  *messages* are not compared, only types.
- The duplication metric treats near-identical generated scaffolding as duplication (as intended),
  but also counts legitimately parallel code (e.g. similar renderers).
- Magic-number counting does not distinguish presentation widths from business constants.

## Interpreting results

Scores near 50 with a pass gate failure mean "didn't really refactor"; a `behaviour_changed` critical
on an otherwise excellent refactor indicates insufficient verification (the most common real-world
refactoring failure). `proportionate_design` < 0.5 flags architecture astronautics.
