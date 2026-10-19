# PERF-118 — nightly leaderboard job takes hours since release 2.3.0

**From:** data platform on-call · **Severity:** high (dashboards stale every morning)

The nightly job calls `eventstats.summarize(events, top_k=100)` once on the day's merged export.

| Release | Events/day | Job duration |
|---|---|---|
| 2.2.4 | ~0.9 M | 3 min 40 s |
| 2.3.0 | ~1.1 M | killed after 3 h (timeout) |

Release notes of 2.3.0 (abridged): "refactor: dedupe preserves first-seen order of events; ranking
tie-break by first appearance documented in the docstring; parse_event no longer mutates caller
records." The output of 2.3.0 is the *intended* output — the BI team signed off on its semantics on
a 10 k-event sample, so any fix must produce exactly the same results.

Staging reproduction on a 50 k-event slice: 2.2.4 ≈ 0.2 s, 2.3.0 ≈ 41 s.
Machine: the job has ~2 GB of memory available.
