## Root causes

The engine applied the rules in the documented order, but three rule implementations used the wrong
quantity when a specific combination of states occurred:

1. **Free-shipping threshold** (`rules/shipping.py`) was checked on `T` (after the membership discount).
   RULES.md step 5 says `M − B − Dc`. Gold/silver members just above 50.00 lost free shipping and paid
   more than non-members (cart 1: 56.65 vs 56.29 → correct 50.66), violating I2.
2. **Coupon `min_spend`** (`rules/coupons.py`) was checked on the base after the membership discount.
   RULES.md step 3 says `R − B` (+ S with `applies_to_sale`). Members near a coupon threshold lost the
   coupon — same invariant I2, not mentioned in the complaint but implied by the spec.
3. **Bundles** (`rules/bundles.py`) included sale lines with a bundle name, so a clearance unit could
   be the "free" third unit and shift which regular unit is free (cart 2: 25.48 → correct 30.89).

## Fix

Each rule now uses exactly the quantity RULES.md defines; the rule order and all other rules
(rounding, tax on T, percent coupon on the post-membership base) are unchanged.

## Verification

`tests/test_pricing_regressions.py` covers the three defects (fail before, pass after). I also
compared the engine against a literal re-implementation of RULES.md on random carts (scratch script,
not committed). `python -m pytest -q`: all tests pass.

Residual risk: orders already placed with these combinations were mis-priced in both directions
(overcharged members; undercharged bundle+sale carts).

```json
{"root_causes": ["shipping threshold evaluated after membership discount", "coupon min_spend evaluated after membership discount", "sale lines included in bundles"], "files_changed": ["checkout/rules/shipping.py", "checkout/rules/coupons.py", "checkout/rules/bundles.py", "tests/test_pricing_regressions.py"], "tests_run": true, "tests_passed": true}
```
