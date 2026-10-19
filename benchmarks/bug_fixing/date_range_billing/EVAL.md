# EVAL — bug_fixing/date_range_billing (v1.0.0)

<!-- AIBENCH-CANARY: 3b91d0e4-date-range-billing-eval — never include this file in model inputs. -->

## What this benchmark measures

A medium-difficulty, **single-cause** bug whose symptoms look like a business/pricing problem
("March invoices are wrong for some customers") but whose cause is a time-arithmetic error:
`days_between()` converts local midnights to UTC and floor-divides elapsed seconds by 86 400,
so any interval containing a 23-hour spring-forward day loses one day (23.5-hour days in
`Australia/Lord_Howe` too). Fall-back (25-hour) days floor correctly, which is why November is fine.

Competencies: reproducing from tabular evidence, generalising from 2 examples (two zones, one month)
to the real condition (any DST-observing zone, either hemisphere, any interval containing a
spring-forward day), resisting special-casing, choosing a fix that is correct in *both* transition
directions, and writing discriminating regression tests.

Valid fixes include `(end - start).days`, comparing naive local datetimes, or rounding elapsed days to
the nearest integer. `math.ceil` is a plausible but wrong fix (breaks 25-hour days).

## Checks and scoring

| Criterion | Weight | Metric | Evidence |
|---|---|---|---|
| root_cause_fixed | 35 | `hidden.root_pass_rate` | 14 tests: spring-forward months in 6 zones (N/S hemispheres, 30-min shift), fall-back months, intervals over transitions, ticket replay, change on the transition day |
| invariants_hold | 15 | `hidden.inv_pass_rate` | Hypothesis (derandomized): day counts equal calendar days and are additive; a full period costs exactly the full price, across 8 zones and 2020–2030 |
| behaviour_preserved | 10 | `hidden.pres_pass_rate` | half-even rounding, exclusive ends, clipping, validation, local-date conversion, API |
| public_suite_passes | 10 | `public.pass_rate` | original public tests (benchmark copy) |
| regression_tests | 15 | `regression.quality` | new tests fail on original and pass on final code |
| change_size | 5 | `scope.lines_changed` | linear: ≤ 50 → 1, ≥ 200 → 0 |
| change_scope | 5 | `scope.out_of_scope_files` | only `billing/**`, `tests/**` |
| verified_after_last_edit | 3 | `process.tests_run_after_last_edit` | trace |
| structured_report | 2 | `report.report_json_valid` | final JSON block |

**Pass** = score ≥ 75 and all root tests pass and all invariant tests pass and the original public suite
passes and no critical failure.

### Critical failures

| Id | Condition | Effect |
|---|---|---|
| `false_test_claim` | claims `tests_run: true` with no `pytest` in the trace | cap 40, fail |
| `protected_files_changed` | `support/**` modified/deleted | cap 50, fail |
| `deleted_files` | any existing file deleted | cap 50, fail |

## Grader validation (selftests, observed v1.0.0, local sandbox)

| Case | Expected | Observed |
|---|---|---|
| reference (date-based count + tests + honest report) | pass, ≥ 90 | 100.0, pass |
| noop | fail, ≤ 45 | 40.0, fail (4/14 root tests — fall-back months — already pass) |
| ceil_patch (round elapsed days up) | fail, ≤ 75 | 72.5, fail (breaks fall-back months and invariants) |
| special_case (patches March for NY/Berlin) | fail, ≤ 60 | 55.0, fail |
| false_claim (correct code, no test run, claims it) | fail, ≤ 40, `false_test_claim` | 40.0, fail |

`ceil_patch` scores fairly high because it is *almost* right; the pass gates (all root and invariant
tests) are what make it fail. This is intentional: the score shows closeness, the verdict shows
correctness.

## Limitations

- Correctness depends on the tz database of the sandbox interpreter; future tzdata changes for
  2026–2030 rules could alter expected values for the property test (it only compares against
  `(end - start).days`, so it is robust to rule changes; the parametrized cases use 2024–2026).
- Docker images without tzdata will fail the benchmark for every model (environment issue, visible
  as `ZoneInfoNotFoundError` in `hidden.pytest.txt`).
- `lines_changed` includes tests; very large test additions lose up to 5 points.

## Interpreting results

High `root_cause_fixed` with low `invariants_hold` means a fix that works for the listed months but not
in general (e.g. ceil, or zone-specific code). Low `regression_tests` means the agent did not prove the
bug. Read critical failures before the score.
