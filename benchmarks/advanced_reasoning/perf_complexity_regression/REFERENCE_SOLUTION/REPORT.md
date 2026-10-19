## Root cause

Release 2.3.0 introduced two hidden O(n²) operations in `eventstats/aggregate.py`:

1. Deduplication kept the first-seen order with a **list** of keys and tested `key not in unique`
   for every event — a linear scan per event.
2. The ranking/ordering sort keys called `first_seen_users.index(u)` — another linear scan over all
   unique events for every user.

With ~1.1 M events this is ~10¹² comparisons. (`copy.deepcopy` in `parse_event` costs a constant
factor only; I left it to keep the "never mutate caller records" guarantee untouched.)

## Fix

`best` is a `dict`, which preserves insertion order, so it already records keys in first-seen order
and gives O(1) membership; replacing a value keeps the key's position. `totals` is filled in that
order, so a user's first appearance is its insertion index (`first_rank`). Output is identical by
construction; complexity is O(n + u log u).

## Verification

Compared old and new implementations on random inputs (duplicates, equal timestamps, case/whitespace
variants, invalid records) — identical results. 50 k events: 41 s → 0.3 s; 200 k events ≈ 1.2 s.
Added `tests/test_perf_regression.py` (times out on 2.3.0, passes now). `python -m pytest -q`: all pass.

Residual risk: memory is O(unique events), as before.

```json
{"root_causes": ["list membership test in dedupe loop (O(n^2))", "list.index in sort keys (O(n*u))"], "files_changed": ["eventstats/aggregate.py", "tests/test_perf_regression.py"], "tests_run": true, "tests_passed": true}
```
