# EVAL — concurrency/async_cancellation_leak (v1.0.0)

<!-- AIBENCH-CANARY: 91c4e6b3-async-cancellation-leak-eval — never include this file in model inputs. -->

## What this benchmark measures

Whether an agent understands **asyncio cancellation semantics** well enough to keep resources
balanced at every `await`, de-duplicate redelivered work, and implement a shutdown that really
stops tasks — rather than patching the visible symptom (resetting the pool) or fixing only the most
obvious site.

## Ground truth (hidden from the model)

| # | Root cause | Symptom |
|---|---|---|
| 1 | `_attempt` releases only in `except TimeoutError`/`except Exception`; `CancelledError` is a `BaseException` | pool drains after user cancellations/deploys |
| 2 | `ConnectionPool.acquire` takes the permit before the awaited handshake and does not undo it on cancellation | same drain, from cancellations during connect (survives fix #1) |
| 3 | `submit` de-duplicates only completed jobs | redelivered running/pending/retrying export runs twice |
| 4 | `shutdown` waits `grace` then returns without cancelling or awaiting stragglers | jobs keep writing after shutdown; connections still checked out |

Several correct designs exist (`try/finally`, `asyncio.TaskGroup`, futures registry, `shield`
only for cleanup, …); tests check behaviour only.

## How it is tested (and the limits)

- **Deterministic schedules**: handlers and the connection handshake block on `asyncio.Event`s, so
  cancellation happens at a known await point (in handler, in handshake, while queued on the pool,
  between retries). Redeliveries are submitted while the job is provably pending/running/retrying.
- **Seeded stress** (5 seeds × 150 submissions, random handler durations, 10 % handler errors,
  timeouts, 15 % random cancellations, duplicates, then a shutdown on a second wave), repeated
  twice. Invariants: `0 ≤ in_use ≤ size` throughout, pool whole once all jobs settle and after
  shutdown, never two concurrent attempts of a job id, no job completes twice.
- Every test runs under `asyncio.wait_for(..., 15–30 s)`; a hang becomes a `TimeoutError` failure.

Limits: asyncio is single-threaded, so these are logical races; all interleavings that matter are
at awaits, which the deterministic tests enumerate for the documented paths. Handlers that swallow
`CancelledError` are out of scope. Timing appears only in timeouts with wide margins
(attempt timeouts of 20–50 ms against handlers sleeping ≥1 s).

## Checks and scoring (fixed before any run)

| Criterion | Weight | Metric | Evidence |
|---|---|---|---|
| cancellation_safety | 25 | `hidden.cancel_pass_rate` | 5 tests: handler, handshake, queued on pool, mass cancellation at varied points, cancel between retries |
| no_duplicate_processing | 20 | `hidden.dup_pass_rate` | redelivery while running, while queued, during retry; failed/cancelled jobs resubmittable |
| graceful_shutdown | 15 | `hidden.shut_pass_rate` | stragglers cancelled and awaited (cleanup that awaits completes), bounded, rejects new jobs |
| stress_invariants | 15 | `stress.pass_rate` | 5 seeds × 2 repetitions |
| contract_preserved | 8 | `hidden.pres_pass_rate` | API, retry/failure semantics, results |
| public_suite_passes | 5 | `public.pass_rate` | original suite |
| regression_tests | 7 | `regression.quality` | discriminating new tests |
| change_scope | 3 | `scope.out_of_scope_files` | only `jobq/**`, `tests/**` |
| change_size | 2 | `scope.lines_changed` | ≤140 full, ≥400 none |

**Pass** = score ≥ 80 and all `cancel`, `dup`, `shut`, stress and public tests passing, no critical failure.

### Critical failures

| Id | Condition | Effect |
|---|---|---|
| `false_test_claim` | claims tests ran, no pytest in the trace | cap 40, fail |
| `protected_modified` | `docs/` modified/deleted | cap 50, fail |
| `deleted_files` | existing file deleted | cap 50, fail |

### Minor vs serious errors

- *Minor*: no regression tests, oversized diff.
- *Serious*: fixing only the handler path (handshake leak remains), shutdown that cancels without
  awaiting, rejecting duplicates instead of returning the running task.
- *Disqualifying*: resetting/recreating the pool to hide leaks (deterministic cancel tests fail),
  any duplicate execution.

## Selftests (observed, local sandbox, 3 runs, identical)

| Case | Expected | Observed |
|---|---|---|
| reference | pass, ≥ 90 | 100.0 |
| noop | fail, ≤ 35 | 33.0 |
| handler_finally_only (only fix #1) | fail, ≤ 50 | 43.0 |
| shutdown_no_wait (all but "await stragglers") | fail, `shut` gate 0 | 68.0 |
| reset_pool_on_shutdown (symptom patch) | fail, `cancel` gate 0 | 58.0 |
| false_claim | fail, cap 40, `false_test_claim` | 40.0 |

## Interpreting results

Partial cancellation scores usually mean only `_attempt` was fixed (the handshake leak is the
discriminating test). A high score that fails only `graceful_shutdown` means the agent cancels but
does not await tasks — the "Task was destroyed but it is pending" class of bug.
