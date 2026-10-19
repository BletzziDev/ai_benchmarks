# EVAL — architecture/zero_downtime_migration (v1.0.0)

<!-- AIBENCH-CANARY: e2a6c4d9-zero-downtime-eval — never include this file in model inputs. -->

## What this benchmark measures

Architectural planning under real operational constraints, graded **objectively** where possible.
The model must design an expand/migrate/contract sequence that splits `users.name` while two app
versions overlap during every rolling deploy, writes never stop, long locks and unbatched updates
are forbidden, only 3 releases are available, and rollback to v1 must stay possible until a declared
point of no return. Then it must explain the design (trade-offs, failure handling, name semantics).

No single answer is correct. The simulator accepts any plan that satisfies the stated rules; the
selftests include two structurally different valid plans (application dual writes with a
trigger-backed contract, and trigger-based expand with three releases).

The world rules are stated in full in the prompt, so failures reflect planning, not hidden rules.
Typical traps the rules encode: reading the new columns before the backfill; backfilling while some
running version does not maintain the target; stopping writes to `name` while `name` is still
`NOT NULL`; triggers in both directions; dropping `name` while it is the only correct copy; losing the
ability to roll back long before the declared point of no return (e.g. a release that stops writing
`name` without a reverse trigger).

## Checks and scoring

| Criterion | Weight | Metric | Evidence |
|---|---|---|---|
| plan_valid | 5 | `sim.plan_parsed` | DSL parses |
| compatibility | 25 | `sim.compat_score` | 1 − 0.25 per violation (stale/missing reads, writes to missing columns, failing inserts, ineffective backfills, invalid steps), checked in every state incl. mixed windows |
| no_downtime | 10 | `sim.no_downtime` | no unbatched/oversized backfill, no `set_not_null: direct` |
| end_state | 15 | `sim.final_state_ok` | `name` dropped, split correct, single version reads/writes only split, no triggers |
| rollback | 15 | `sim.rollback_score` | 0.5 × (rollback succeeds after every step before the declared PONR) + 0.5 × (rollback remains possible through every deploy) |
| release_budget | 3 | `sim.within_deploy_budget` | 1–3 deploys |
| design_doc_present | 2 | `sim.design_present` | DESIGN.md ≥ 800 characters |
| design_tradeoffs | 7 | `design.tradeoffs` | rubric (LLM judge or human), optional |
| design_failure_handling | 6 | `design.failure_handling` | rubric, optional |
| design_data_semantics | 7 | `design.data_semantics` | rubric, optional |
| structured_report | 5 | `report.report_json_valid` | JSON block with `point_of_no_return` |

Without a judge or human grades the rubric criteria are excluded and the score is **provisional**
(renormalised over 80 points); record human grades with `benchmark grade`.

**Pass** = score ≥ 75 and the plan parses, has zero violations, reaches the end state and its rollback
claim is valid, and no critical failure.

### Critical failures

| Id | Condition | Effect |
|---|---|---|
| `data_loss` | a column is dropped while its data is not correct in the other representation | score 0, fail |
| `false_check_claim` | `plan_checked: true` but `tools/check_plan.py` never ran | cap 40, fail |
| `protected_files_changed` | `context/**` or `tools/**` modified/deleted | cap 50, fail |

## Grader validation (selftests, observed v1.0.0, local sandbox, no judge → provisional)

| Case | Expected | Observed |
|---|---|---|
| reference (dual writes, reverse trigger in contract, 2 releases) | pass, ≥ 95 | 100.0, pass |
| alt_triggers (trigger expand, 3 releases) | pass, ≥ 90 | 100.0, pass |
| noop | fail, ≤ 10 | 0.0, fail |
| big_bang | fail, ≤ 5, `data_loss` + `false_check_claim` | 0.0, fail |
| drop_before_backfill | fail, ≤ 5, `data_loss` | 0.0, fail |
| stale_reads (reads split before backfill) | fail, ≤ 75 | 63.1, fail |
| no_rollback (stops maintaining `name` before the declared PONR) | fail, ≤ 85 | 78.8, fail |

## Limitations

- The DSL abstracts PostgreSQL: lock behaviour is reduced to two rules (batch size, direct SET NOT
  NULL); replication lag, vacuum and index builds are not simulated. Realism of these aspects is left
  to the DESIGN.md rubric.
- "Correctness" of a representation is binary (fresh/stale); partial staleness and the exact
  name-splitting function are not simulated.
- Rollback is modelled as re-deploying previous versions newest-first on the current schema; schema
  reversal is not required (matching the stated policy).
- `tools/check_plan.py` needs PyYAML in the sandbox interpreter (present on the default local
  backend; add it to custom Docker images).
- The rubric depends on a judge model or human graders; see docs on judge bias and agreement.

## Interpreting results

High `compatibility` with low `rollback` → the model understands mixed-version compatibility but not
reversibility (common). Low `compatibility` → it does not reason about the mixed window. A critical
`data_loss` means the plan is dangerous regardless of the other scores.
