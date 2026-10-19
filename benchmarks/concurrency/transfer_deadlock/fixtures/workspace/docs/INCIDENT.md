# TRSY-88 — treasury workers hang

The nightly treasury sweep runs ~40 worker threads that move money between operating accounts
(both directions are common: A→B for funding, B→A for refunds), while the monitoring endpoint calls
`Bank.total()` every few seconds.

- Several times a week the sweep stops making progress: all workers are stuck, CPU is 0 %, and
  the monitoring endpoint hangs too. A restart "fixes" it.
- After a storage hiccup (journal writes slowed to seconds), callers that use
  `transfer(..., timeout=2)` started getting `TransferTimeout` — expected — but shortly afterwards
  the affected accounts were frozen for good, even after storage recovered.
- A buggy client once sent a transfer from an account to itself; that worker never returned.
