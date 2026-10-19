# ACC-731 — splitting `users.name` into `first_name` / `last_name` without downtime

## Approach: expand → migrate → contract with application dual writes

Rolling deploys mean two app versions share the database for ~15 minutes, so every intermediate state
must be readable and writable by *both* the old and the new version. I use three phases:

1. **Expand (s1–s2):** add `first_name`, `last_name` as nullable columns (metadata-only in PG 15, no
   table rewrite, no long lock).
2. **Migrate (s3–s5):** release **v2** that still *reads* `name` but *writes* `name` and the split
   columns. During the v1/v2 rollout the split columns are incomplete, but nobody reads them. Once
   only v2 runs, backfill the split columns from `name` in batches of 5 000 rows (resumable, keyed by
   id ranges, throttled on replica lag), then verify: no NULL `first_name`, and a 10 k-row sample
   where re-joining the parts equals the normalised `name`.
3. **Switch + contract (s6–s11):** drop `NOT NULL` on `name` (metadata-only) and install a trigger that
   derives `name` from the split columns, then release **v3**, which reads and writes only the new
   columns. The trigger keeps `name` correct so that v2 — and, through v2, v1 — remain valid rollback
   targets. After v3 has been stable (24 h, error rate/latency/consistency dashboards), drop the trigger
   (**point of no return**: from here `name` stops being maintained) and drop the column.

Only two of the three available releases are used; the third is held in reserve for a fix-forward.

## Alternatives considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Dual writes in the app (chosen for expand) | explicit, testable in code review, no DB logic | needs an extra release; app must write both consistently | chosen |
| Trigger `name → split` during expand | backfill could start before any release | trigger logic duplicates app parsing rules; ~3k trigger executions/s on the primary | not needed: v2 covers it |
| Trigger `split → name` during contract | keeps rollback to v1/v2 possible while v3 stops writing `name` | short-lived DB logic; must be dropped before the column | chosen, scoped to the contract phase |
| Generated column / view | no data duplication | cannot express "user-corrected" names; generated columns cannot be written | rejected |
| Big-bang migration in a maintenance window | simplest | violates the no-downtime SLO; one big UPDATE on 40 M rows would lock and lag replicas | rejected |

Triggers in both directions at once are avoided (recursion and lock-ordering risk). If we had only one
release available, a trigger-based expand would be required; with a maintenance window the whole thing
would collapse to two steps.

## Name-splitting rules

- Normalise whitespace (trim, collapse runs of spaces).
- Last space-separated token → `last_name`; the rest → `first_name` (`Ada Lovelace` → Ada / Lovelace).
  This is wrong for compound family names (`Gabriel García Márquez` → "Gabriel García" / "Márquez");
  such rows are flagged by heuristics (particles, known compound surnames) for user correction.
- Single token (`Prince`) → `first_name = 'Prince'`, `last_name = ''` (empty string, not NULL, so
  `last_name` can later become NOT NULL via a validated CHECK constraint).
- No-space scripts (`李小龙`): stored entirely in `first_name`, flagged; family-name-first cultures cannot
  be split reliably without user input, so the product will ask users to confirm on next login.
- Reconstruction for rollback (trigger `split → name`): `trim(first_name || ' ' || last_name)`. Split →
  join is lossy for whitespace and for user-corrected order; this only affects display during a
  rollback and is accepted.

## Failure handling and rollback

- Backfill is idempotent (`WHERE first_name IS NULL`), resumable by id range, with `lock_timeout = 1s`
  and a pause when replica lag > 5 s. A failed batch is retried; nothing is irreversible before s10.
- Rollback: before s10, redeploy v2 then v1 (newest first). Schema additions stay. After s10 the only
  recovery is fix-forward with the reserve release.
- Gates before s10: 0 NULL `first_name`, sample consistency 100 %, v3 error budget unchanged for 24 h.
