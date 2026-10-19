## Root cause

`days_between()` converted the two local midnights to UTC and floor-divided the difference by
86 400 s. A local day containing the spring-forward DST transition is only 23 h long, so any
interval containing it lost a day (March in New York/Berlin, October in Sydney). Fall-back days
are 25 h and happened to floor correctly, which is why November looked fine. Both the period length
and the active-day count use `days_between()`, so both invoice lines were wrong.

## Fix

Count calendar days on the dates themselves: `(end - start).days`. The dates already represent the
account's local calendar (the instant → local date conversion happens in `BillingPeriod.local_date`,
which was correct). `tz` stays in the signature for compatibility. Rounding (half-even) unchanged.

## Verification

Added `tests/test_dst_proration.py` (fails before, passes after), including both ticket examples.
`python -m pytest -q`: all tests pass.

Residual risk: invoices issued for March/October periods in DST-observing zones were wrong and need
re-issuing; that is a data correction outside this code change.

```json
{"root_causes": ["days_between measured elapsed UTC seconds, so 23-hour DST days dropped a day"], "files_changed": ["billing/periods.py", "tests/test_dst_proration.py"], "tests_run": true, "tests_passed": true}
```
