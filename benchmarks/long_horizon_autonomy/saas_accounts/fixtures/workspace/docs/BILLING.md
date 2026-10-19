# Billing rules

All amounts are integer cents. Floating point must not be used for money.

## Periods

A subscription is anchored on its start date. Period *n* (0-based) is
`[add_months(anchor, n), add_months(anchor, n + 1))`. `add_months` keeps the day of month and,
when the target month is shorter, **clamps to the last day of that month**: Jan 31 + 1 month =
Feb 28 (Feb 29 in leap years); Jan 31 + 2 months = Mar 31; Aug 31 + 1 month = Sep 30.

## Proration

When the plan changes on `change_date` inside the current period `[start, end)`:

```
remaining_days = (end - change_date).days      # change day included
total_days     = (end - start).days
proration      = round_half_up((new_price - old_price) * remaining_days / total_days)
```

computed exactly on integers (no intermediate rounding of the credit and the charge separately).
`round_half_up` rounds .5 away from zero, symmetrically for negative amounts (credits).

## Tax

`tax = round_half_up(subtotal * rate_bp / 10000)` with the same rounding rule.

## Invoice numbers

`INV-<year>-<sequence>`, sequence zero-padded to 5 digits, starting at `00001` and restarting every
calendar year of the issue date. Numbers are never reused.
