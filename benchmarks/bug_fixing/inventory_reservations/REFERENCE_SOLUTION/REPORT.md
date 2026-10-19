## Summary

INC-2291 had three defects in `stockroom/service.py`, all violating the invariants documented on `InventoryService`:

1. `restock()` invalidated the cache with the raw SKU (`"lamp-01 "`) instead of the canonical key, so restocks from the admin tool left a stale "0 available" entry for up to the 60 s TTL.
2. `expire_due()` marked holds as expired without invalidating the cache, so freed units stayed invisible (false "insufficient stock").
3. `confirm()` accepted expired holds (and active holds whose time had lapsed). A late payment webhook confirmed R000101 after its units were re-reserved, which drove availability to -2; the `max(0, ...)` clamp in `confirm()` then hid the oversell by pinning on_hand at 0.

Fixes: invalidate with the canonical key; centralise expiry in `_expire()` which invalidates the cache; `available()` sweeps lapsed holds first; `confirm()` raises `ReservationExpired` (as its docstring promises) for expired/lapsed holds; the clamp was removed because a valid confirm can no longer drive on_hand negative.

Regression tests: `tests/test_incident_2291.py` (fail on the original code, pass now). Full suite: `python -m pytest -q` → all passing.

Residual risk: a payment captured for an expired hold must now be refunded or re-reserved by the caller (the webhook handler is outside this repository). The cache is per-process; a multi-instance deployment would need shared invalidation.

```json
{"root_causes": ["restock invalidates non-canonical cache key", "expire_due does not invalidate cache", "confirm accepts expired/lapsed holds"], "files_changed": ["stockroom/service.py", "tests/test_incident_2291.py"], "tests_run": true, "tests_passed": true}
```
