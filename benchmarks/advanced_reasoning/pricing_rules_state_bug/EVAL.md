# EVAL — advanced_reasoning/pricing_rules_state_bug (v1.0.0)

<!-- AIBENCH-CANARY: c84e2f17-pricing-rules-eval — never include this file in model inputs. -->

## What this benchmark measures

Reasoning from a written specification to defects that appear **only in specific combinations of
state**. The engine runs its rules in the documented order, so a quick read looks correct; each defect
is a rule that measures the wrong quantity:

| # | Defect (file) | Violates | Appears only when | Reported? |
|---|---|---|---|---|
| A | free-shipping threshold uses `T` (after membership) instead of `M − B − Dc` (`rules/shipping.py`) | step 5, I2 | member **and** merchandise just above 50.00 | yes (ticket 4471) |
| B | coupon `min_spend` checked after membership instead of on `R − B` (+S) (`rules/coupons.py`) | step 3, I2 | member **and** coupon with min_spend **and** base near the minimum | **no** — implied by I2 |
| C | sale lines with a bundle tag join bundles (`rules/bundles.py`) | step 1, I3 | bundle group containing a sale unit | yes (order 7731) |

Competencies: building a mental (or executable) model of a spec, generalising from two examples,
discovering an unreported defect from a stated invariant, separating a cause from a coincidence
(both reports involve thresholds/promotions but have different causes), avoiding special-casing and
"reordering" hacks that break other rules.

## Checks and scoring

| Criterion | Weight | Metric | Evidence |
|---|---|---|---|
| defects_fixed | 30 | `hidden.root_pass_rate` | 10 targeted tests across A/B/C and their combinations |
| matches_specification | 25 | `hidden.inv_pass_rate` | 3 Hypothesis tests × 400 carts (derandomized): equality with an independent oracle of RULES.md (all receipt components), I2 monotonicity, I1/I3 |
| behaviour_preserved | 10 | `hidden.pres_pass_rate` | rule order, tax on T half-up, multiple bundle groups, coupon cap, shipping fee, API |
| public_suite_passes | 10 | `public.pass_rate` | original public tests |
| regression_tests | 10 | `regression.quality` | new tests fail on original, pass on final |
| change_size | 5 | `scope.lines_changed` | linear ≤ 80 → 1, ≥ 300 → 0 |
| change_scope | 5 | `scope.out_of_scope_files` | only `checkout/**`, `tests/**` |
| verified_after_last_edit | 3 | `process.tests_run_after_last_edit` | trace |
| structured_report | 2 | `report.report_json_valid` | JSON block |

**Pass** = score ≥ 75 and all root tests and all specification/invariant tests pass and the original
public suite passes and no critical failure. Fixing only the two reported defects (A and C) scores
≈ 80 but **fails** — finding B is the point of the benchmark.

### Critical failures

| Id | Condition | Effect |
|---|---|---|
| `specification_modified` | `docs/RULES.md` changed or deleted | score 0, fail |
| `false_test_claim` | claims tests ran, no `pytest` in trace | cap 40, fail |
| `deleted_files` | any existing file deleted | cap 50, fail |

## Grader validation (selftests, observed v1.0.0, local sandbox)

| Case | Expected | Observed |
|---|---|---|
| reference (A+B+C fixed, tests, honest report) | pass, ≥ 90 | 100.0, pass |
| noop | fail, ≤ 35 | 30.0, fail |
| special_case (gold-only shipping, "cheapest sale unit" bundle hack) | fail, ≤ 65 | 57.0, fail |
| reorder_hack (membership applied last) | fail, ≤ 55 | 44.9, fail (tax base and percent-coupon base wrong) |
| reported_only (A and C correct, B missed) | fail, ≤ 80 | 79.7, fail (gates) |
| false_claim | fail, ≤ 40, `false_test_claim` | 40.0, fail |

## Limitations

- The oracle is a second implementation written by the benchmark author from RULES.md; an error
  shared by spec reading and oracle would go unnoticed. Mitigation: invariant I2 was additionally
  property-checked on the oracle itself (20 000 derandomized carts) during authoring.
- Random carts use prices up to 60.00 and ≤ 7 lines; very large carts are not sampled.
- The benchmark rewards finding B, which requires reading the invariant section; a model that
  considers only the tickets will (correctly, by design) not pass.

## Interpreting results

`defects_fixed` high and `matches_specification` low → special-casing. Both medium with
`behaviour_preserved` low → structural hack (reordering). `reported_only`-like profiles (≈ 80, fail)
indicate the model did not reason from the specification beyond the tickets.
