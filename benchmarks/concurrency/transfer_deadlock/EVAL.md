# EVAL — concurrency/transfer_deadlock (v1.0.0)

<!-- AIBENCH-CANARY: 5a7d2c90-transfer-deadlock-eval — never include this file in model inputs. -->

## What this benchmark measures

Whether an agent can eliminate **deadlocks and lock leaks** in a per-account locking scheme while
keeping its liveness and parallelism properties: consistent lock ordering across *all* multi-lock
operations, exception-safe acquisition with timeouts, rejecting self-transfers, and not "solving"
deadlock by serialising everything or by silently dropping work.

## Ground truth (hidden from the model)

| # | Root cause | Symptom (docs/INCIDENT.md) |
|---|---|---|
| 1 | `transfer()` locks `src` then `dst` (argument order) | workers hang on A→B / B→A |
| 2 | `total()` locks accounts in dict insertion order, different from any per-transfer order | monitoring endpoint hangs together with workers (survives a naive fix of #1) |
| 3 | when the second `acquire(timeout=…)` fails, the first lock is never released | account frozen forever after a `TransferTimeout` |
| 4 | `src == dst` acquires the same non-reentrant lock twice | self-transfer never returns (spec: `ValueError`) |

Valid fixes: a global order (e.g. by account id) used by `transfer` and `total`, try-lock with
back-off **that retries** (must still apply the transfer), a lock manager, etc. Tests check
behaviour only.

## How deadlocks are detected (and the limits)

- **Stress with bounded joins** (`test_dl_*`, `test_cons_*`): 8–15 daemon threads, up to 5000
  transfers each, `sys.setswitchinterval(1e-6)`; every join has a shared deadline (6–8 s). A stuck
  thread is a failure, never a hang. Measured on the original code: opposite-direction and 3-way
  cycle tests deadlock in 5/5 runs; the `total()`-vs-transfer test (3 rounds) in 3/3 runs.
- **Deterministic contention** (`test_to_*`, `test_par_*`, `test_cons_blocking_*`): a
  `BlockingJournal` parks a chosen transfer inside `record()` — i.e. while it holds its locks — so
  timeouts, waiting and parallelism are tested without relying on luck.
- **Invariants**: balances equal the replay of transfers that reported success, journal entries
  match exactly, every `total()` snapshot equals the constant sum, no negative balance.

Limits: stress detection is probabilistic. A wrong lock order that deadlocks only for an
interleaving the stress tests never hit can pass `test_dl_*` (it is then usually caught by the
consistent-snapshot assertions). Python has no ThreadSanitizer/lock-order checker; the GIL makes
some windows narrow, which is why the switch interval is lowered. Stress-based tests make the
**score** of some broken solutions vary slightly between runs (noop: 35.5–41.8 observed), while the
**verdict** has been stable.

## Checks and scoring (fixed before any run)

| Criterion | Weight | Metric | Evidence |
|---|---|---|---|
| deadlock_free | 25 | `hidden.dl_pass_rate` | opposite directions, 3-way cycle, `total()` during transfers (3 rounds), self-transfer |
| timeouts_safe | 15 | `hidden.to_pass_rate` | timeout on 2nd and 1st lock, nothing changed/journaled, accounts usable afterwards |
| conservation_atomicity | 20 | `hidden.cons_pass_rate` | 3 seeded random stress runs with replay check; a blocked transfer without timeout must wait and apply |
| parallelism_with_safety | 15 | `hidden.par_pass_rate` | disjoint transfer completes while the journal is parked, opposite transfer waits (no deadlock), account usable after a timeout; `total()` waits but completes |
| contract_preserved | 8 | `hidden.pres_pass_rate` | API, errors, journal semantics |
| public_suite_passes | 5 | `public.pass_rate` | original suite |
| regression_tests | 7 | `regression.quality` | new tests fail on the original and pass on the final code |
| change_scope | 3 | `scope.out_of_scope_files` | only `bankcore/bank.py`, `bankcore/__init__.py`, tests |
| change_size | 2 | `scope.lines_changed` | ≤130 full credit, ≥400 none |

**Pass** = score ≥ 80, all `dl`/`to`/`cons`/`par` and public tests passing, no critical failure.

### Critical failures

| Id | Condition | Effect |
|---|---|---|
| `false_test_claim` | report claims tests ran, no pytest in the trace | cap 40, fail |
| `protected_modified` | `bankcore/journal.py` or `docs/` changed | cap 50, fail |
| `deleted_files` | existing file deleted | cap 50, fail |

### Minor vs serious errors

- *Minor*: missing regression tests, larger diff, extra files touched.
- *Serious*: bank-wide lock (fails parallelism gate), fixing `transfer` but not `total`, timeout
  path still leaking.
- *Disqualifying*: dropping or double-applying transfers (conservation), any remaining deadlock.

## Selftests (observed, local sandbox, 3 runs)

| Case | Expected | Observed |
|---|---|---|
| reference (id order everywhere, try/finally, single deadline) | pass, ≥ 90 | 100.0 ×3 |
| noop | fail, ≤ 45 | 35.5 / 41.8 / 35.5 (stress variance) |
| global_lock | fail, `par` gate 0, `dl` all pass | 85.5 ×3 |
| trylock_drop (silently skips busy transfers) | fail, `cons` gate 0 | 55.5 ×3 |
| ordered_transfer_only (`total()` keeps insertion order) | fail, `dl` gate 0 | 71.8 ×3 |
| false_claim | fail, cap 40, `false_test_claim` | 40.0 ×3 |

## Interpreting results

`deadlock_free` high but `conservation_atomicity` low → the agent avoided deadlock by giving up on
work (try-lock and drop). High correctness, low `parallelism_with_safety` → global lock. Failing
only `test_dl_totals_during_transfers` → fixed the reported path but not every multi-lock operation.
