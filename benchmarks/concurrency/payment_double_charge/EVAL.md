# EVAL — concurrency/payment_double_charge (v1.0.0)

<!-- AIBENCH-CANARY: 3e9b0d14-payment-double-charge-eval — never include this file in model inputs. -->

## What this benchmark measures

Whether an agent can diagnose and fix **race conditions with financial consequences** in threaded
Python code: a check-then-act race on idempotency keys (double charges under client retries), a
non-atomic balance check (overdraft) and an unsynchronised read-modify-write (lost debits) — and do
so **without** trading correctness for a global lock that serialises every account behind slow I/O.

Competencies: reasoning about interleavings, at-most-once semantics, waiter/in-flight patterns,
lock scope and lock-free-of-I/O critical sections, reservation/compensation, deterministic
concurrency testing, honest reporting.

## Ground truth (hidden from the model)

| # | Root cause | Symptom |
|---|---|---|
| 1 | `pay()` checks `_results`, calls the gateway, and stores the result only afterwards; an in-flight key is invisible | retry during a slow gateway call → second charge |
| 2 | balance checked before the gateway call, debited after it (two separate steps) | two orders on one account both succeed → negative balance |
| 3 | `Ledger.debit/credit` read-modify-write without a lock (a `log.debug` call widens the window) | reconciliation mismatch (lost debit) |

The specification is the `PaymentProcessor` docstring (visible to the model): at most one charge per
key; concurrent duplicates wait and share the outcome (result **or** exception); failures are not
remembered; conflicting reuse raises `IdempotencyConflict`; balances never negative and conserved;
different accounts never wait for each other.

Several designs are valid (in-flight registry + events/futures, per-key locks, per-account locks
for funds + reservation, a conditional atomic debit, …). Tests check behaviour only.

## How races are detected (and the limits)

CPython has no ThreadSanitizer and the GIL makes many races rare in practice, so a plain stress test
can pass on racy code. The benchmark therefore combines three techniques:

1. **Deterministic interleavings** (`test_dup_*`, `test_bal_*`, `test_prog_*`): a `ControlledGateway`
   blocks chosen calls on a `threading.Event`, forcing the exact schedule from the incident (first
   attempt parked inside the gateway while a retry / second order arrives). These verdicts do not
   depend on luck.
2. **High-contention stress** (`test_stress_*`, 6 seeds × 24 threads, `sys.setswitchinterval(1e-6)`,
   random gateway latency and 10 % declines), run 3 times; a test counts only if it passes every
   time (flaky tests are reported as `stress.flaky_tests`).
3. **Invariant checks** after every scenario: one successful charge per key and never a charge after
   success, money conservation per account, no negative balance, every thread terminates
   (`join(15)` on daemon threads → deadlocks become failures, never hangs).

Limits: stress tests can miss races whose window is not exercised (they are evidence of presence,
not proof of absence); deterministic tests only cover the schedules we designed. A creative wrong
implementation could pass both, e.g. one that is only wrong across processes. Timing thresholds are
generous (1–5 s waits) to avoid false failures on loaded machines; an extremely slow machine could
still produce a false "blocked" verdict in a `test_prog_*` test (none observed in repeated runs).

## Checks and scoring (fixed before any run)

| Criterion | Weight | Metric | Evidence |
|---|---|---|---|
| at_most_once_charging | 25 | `hidden.dup_pass_rate` | 4 deterministic tests: retry during gateway call, 12 concurrent duplicates, shared failure + later retry, conflict while in flight |
| balance_integrity | 20 | `hidden.bal_pass_rate` | forced overdraft schedule, refund on gateway failure, 16×1000 concurrent debits without loss |
| progress_and_parallelism | 15 | `hidden.prog_pass_rate` | another account / a completed-key replay must not wait for a held gateway call; same-account keys do not deadlock; each also asserts no duplicate charge |
| stress_invariants | 15 | `stress.pass_rate` | 6 seeded stress runs × 3 repetitions |
| contract_preserved | 8 | `hidden.pres_pass_rate` | sequential semantics, API, ledger methods |
| public_suite_passes | 5 | `public.pass_rate` | original suite (benchmark copy) |
| regression_tests | 7 | `regression.quality` | new tests fail on original code and pass on final code |
| change_scope | 3 | `scope.out_of_scope_files` | only processor/ledger/errors/`__init__`/tests |
| change_size | 2 | `scope.lines_changed` | ≤150 lines full credit, ≥450 none |

**Pass** = score ≥ 80 and all `dup`, `bal`, `prog`, stress and public tests passing, and no critical failure.

### Critical failures

| Id | Condition | Effect |
|---|---|---|
| `false_test_claim` | report claims tests ran but no pytest command was executed | cap 40, fail |
| `external_gateway_modified` | `payflow/gateway.py` (the external provider) or `docs/` changed | cap 50, fail |
| `deleted_files` | an existing file was deleted | cap 50, fail |

### Minor vs serious errors

- *Minor*: no regression tests, an oversized diff, touching files outside scope (≤ 10 points).
- *Serious*: global lock across I/O (fails parallelism gate), rejecting concurrent duplicates instead
  of sharing the outcome, refund missing on gateway failure.
- *Critical / disqualifying*: any remaining double charge or overdraft (fails the pass gate
  regardless of score), modifying the simulated external system, false claims.

## Selftests (observed, local sandbox, 3 consecutive runs, identical verdicts)

| Case | Expected | Observed |
|---|---|---|
| reference | pass, ≥ 90 | 99.7, pass |
| noop | fail, ≤ 35 | 24.7, fail |
| global_lock (correct but serialised) | fail, prog gate 0, bal/stress all pass | 76.8, fail |
| ledger_lock_only (thread-safe ledger, processor still racy) | fail, ≤ 60 | 31.3, fail |
| reject_duplicates (charges once, but duplicates get an "in progress" error) | fail, ≤ 90 | 58.0, fail |
| false_claim (reference code, claims tests ran without running them) | fail, cap 40, `false_test_claim` | 40.0, fail |

The reference loses 0.3 points on change size (≈ 160 changed lines incl. tests).

## Interpreting results

- High `balance_integrity` + low `at_most_once_charging`: the agent fixed data races but not the
  logical (check-then-act) race — the most common failure.
- High correctness + low `progress_and_parallelism`: correct but serialised (global lock across I/O).
- `stress.flaky_tests > 0` on a submission means the race is still there but rare; treat as failure.
