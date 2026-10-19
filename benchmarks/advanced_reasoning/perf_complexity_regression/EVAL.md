# EVAL — advanced_reasoning/perf_complexity_regression (v1.0.0)

<!-- AIBENCH-CANARY: 5d07ab93-perf-complexity-eval — never include this file in model inputs. -->

## What this benchmark measures

Diagnosing a performance regression **by measurement** and fixing it **without changing behaviour**.
Release 2.3.0 of `eventstats` made `summarize()` quadratic through two innocent-looking constructs:

1. `if key not in unique:` where `unique` is a **list** (dedupe loop) — O(n²);
2. `first_seen_users.index(u)` inside the sort keys (ranking and `user_order`) — O(n·u).

A red herring (`copy.deepcopy` per record in `parse_event`) costs only a constant factor. The intended
semantics are subtle (first-seen order, earliest copy wins with first-copy tie-break, ties ranked by
first appearance, generators accepted, repeated calls on mutated lists), so "fast" rewrites easily
change results.

Competencies: profiling/measuring before changing code, recognising complexity classes, knowing
language guarantees (dict insertion order, value replacement keeps position), preserving exact
semantics, writing a performance regression test that is reliable and fast.

## Checks and scoring

| Criterion | Weight | Metric | Evidence |
|---|---|---|---|
| results_identical | 25 | `hidden.equiv_all_passed` | **all** equivalence tests pass (the prompt demands identical results for every input) |
| equivalence_coverage | 10 | `hidden.equiv_pass_rate` | 7 tests: Hypothesis (500 inputs, derandomized) vs the frozen 2.3.0 code; realistic batches; tie/earliest-copy edge cases; generator input and re-call after mutation; inputs not mutated |
| scales_linearly | 30 | `hidden.perf_pass_rate` | CPU-time ratio for 4 000 → 32 000 events ≤ 20 (linear ≈ 7–11, 2.3.0 ≈ 50–70); 200 k events < 8 s CPU; 60 k events/50 k users < 4 s CPU |
| api_preserved | 5 | `hidden.pres_pass_rate` | signatures, dataclass fields, errors, empty input |
| public_suite_passes | 10 | `public.pass_rate` | original public tests |
| regression_test | 5 | `regression.quality` | agent's test fails/times out on 2.3.0 and passes on the final code |
| change_size | 5 | `scope.lines_changed` | linear ≤ 80 → 1, ≥ 300 → 0 |
| change_scope | 5 | `scope.out_of_scope_files` | only `eventstats/**`, `tests/**` |
| verified_after_last_edit | 3 | `process.tests_run_after_last_edit` | trace |
| structured_report | 2 | `report.report_json_valid` | JSON block |

**Pass** = score ≥ 75 and all equivalence and all performance tests and the original public suite pass
and no critical failure.

Timing uses `time.process_time()` (CPU time of the test process), medians of repeated runs and a
*ratio*, so results do not depend on machine speed or on other load on the host. Wall-clock alarms
(`SIGALRM`) only abort pathological runs.

### Critical failures

| Id | Condition | Effect |
|---|---|---|
| `false_test_claim` | claims tests ran, no `pytest` in trace | cap 40, fail |
| `protected_files_changed` | `ops/**` changed/deleted | cap 50, fail |
| `deleted_files` | any existing file deleted | cap 50, fail |

## Grader validation (selftests, observed v1.0.0, local sandbox)

| Case | Expected | Observed |
|---|---|---|
| reference (dict-ordered dedupe + first-appearance ranks, perf test, report) | pass, ≥ 90 | 100.0, pass |
| noop | fail, ≤ 60 | 60.0, fail (results identical by definition; all perf tests fail) |
| memo_decoy (fast, caches by `id(raw_events)`) | fail, ≤ 70 | 67.1, fail (stale after mutation; id reuse) |
| fast_wrong (fast; last copy wins ties; alphabetical tie-break) | fail, ≤ 70 | 61.2, fail |
| micro_opt (fixes `index()`, keeps list membership, local aliases) | fail, ≤ 70 | 65.0, fail (still quadratic) |
| false_claim | fail, ≤ 40, `false_test_claim` | 40.0, fail |

The noop's 60 points come from criteria that doing nothing trivially satisfies (identical results,
API, scope). The gates make it fail; read the verdict, not just the score.

## Limitations

- CPU-time ratios are robust to machine speed, but extremely noisy hosts (heavy hyper-threading
  contention) could still inflate a ratio; the threshold (20) leaves a ~2× margin over linear.
- An O(n log n) or O(n·√n) solution passes; the benchmark targets the quadratic/linear distinction,
  not micro-performance.
- A selftest of the no-op takes ~2 minutes (the quadratic code is genuinely slow; alarms cap it).
- Equivalence is checked against 2.3.0 on sampled inputs; a divergence on unsampled shapes is possible.

## Interpreting results

`scales_linearly` 1 with `results_identical` 0 → the agent optimised by changing semantics (or
memoised unsafely). The reverse → it found only part of the problem (e.g. the `index()` call) or
optimised the red herring. Missing `regression_test` → no protection against recurrence.
