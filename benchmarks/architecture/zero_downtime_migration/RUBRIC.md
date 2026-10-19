# RUBRIC — DESIGN.md for the zero-downtime `users.name` split (ACC-731)

Grade only what DESIGN.md says. Plans themselves are graded by a simulator; this rubric covers the
reasoning a reviewer needs. Use the lowest level when the evidence is missing.

## tradeoffs (1–5)
- 1: no alternatives or trade-offs discussed.
- 2: names one alternative without comparing it.
- 3: compares at least two approaches (e.g. application dual writes vs. database triggers vs. a
  view/generated column) on at least two dimensions (complexity, failure modes, rollback, load).
- 4: as 3, and justifies the chosen approach with the specific constraints given (rolling deploys with
  mixed versions, 3 releases, 3k writes/s, replicas, rollback policy).
- 5: as 4, and states what would change the decision (e.g. more releases, a maintenance window,
  logical replication) and the cost of the chosen approach (extra writes, trigger overhead, complexity).

## failure_handling (1–5)
- 1: nothing about failures.
- 2: generic "monitor and roll back".
- 3: concrete verification before each irreversible step (counts/consistency checks), and what to do
  if the backfill fails midway (resumable batches, idempotency).
- 4: as 3, plus explicit rollback procedure per phase and the declared point of no return with why.
- 5: as 4, plus operational limits (batch size/throttling vs replica lag, lock timeouts, how long to
  wait before contract steps) and signals that block progression.

## data_semantics (1–5)
- 1: name splitting not discussed.
- 2: "split on first space" with no edge cases.
- 3: a defined rule covering at least three of the listed examples (single name, compound family name,
  whitespace, no-space scripts) and where empty/NULL last names are allowed.
- 4: as 3, and addresses reversibility (how `name` is reconstructed for rollback / the reverse
  trigger, and that split→join→split is not lossless) and consistency between dual writes.
- 5: as 4, and recognises that automatic splitting is inherently ambiguous (cultural ordering), with a
  product/UX fallback (e.g. keep a display name, let users correct, flag low-confidence rows).
