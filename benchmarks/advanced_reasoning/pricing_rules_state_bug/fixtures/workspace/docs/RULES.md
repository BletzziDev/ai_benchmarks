# Checkout pricing rules — v4 (approved by Finance, 2024-11-04)

This document is the specification. When the code and this document disagree, the document wins.

All money values are **integer cents**. "round(x)" means rounding half **up** to a whole cent.

## Inputs

- Cart lines: `sku`, `unit_price` (cents, ≥ 0), `quantity` (≥ 1), `on_sale` (bool), optional `bundle`
  (bundle group name).
- Customer tier: `none`, `silver` or `gold`.
- At most one coupon: `kind` (`percent` or `fixed`), `value` (percent points or cents), `min_spend`
  (cents, default 0), `applies_to_sale` (bool, default false).

## Definitions

- **M** — merchandise subtotal: Σ `unit_price × quantity` over all lines.
- **Regular lines** are lines with `on_sale = false`; **R** is their subtotal.
- **S** — subtotal of sale lines (`M = R + S`).

## Steps (applied in this order)

1. **Bundles ("3 for 2").** For each bundle group, collect the *units* of regular lines in that group
   (a line with quantity q contributes q units at its unit price). **Sale lines never take part in
   bundles**, even if they carry a bundle name. Sort the units by price, highest first; every third
   unit (3rd, 6th, 9th, …) is free. **B** = total price of the free units over all groups.
2. **Membership.** Silver 5 %, gold 10 % of `R − B`: **Dm** = round(rate × (R − B)). Sale lines are
   never discounted by membership.
3. **Coupon.** The coupon *base* is `R − B − Dm`, plus `S` when `applies_to_sale`.
   - `min_spend` is checked against the base **without the membership discount**, i.e. `R − B`
     (plus `S` when `applies_to_sale`). *Membership must never make a customer lose a coupon.*
   - `percent`: **Dc** = round(value / 100 × base). `fixed`: **Dc** = min(value, base).
   - If `min_spend` is not met, **Dc** = 0.
4. **Merchandise total** `T = M − B − Dm − Dc`.
5. **Shipping.** Free when `M − B − Dc ≥ 5000`; otherwise 599. The threshold deliberately ignores the
   membership discount: *membership must never cost a customer free shipping.*
6. **Tax.** 8.25 % of `T`, rounded once on the total (not per line): `tax = round(0.0825 × T)`.
   Shipping is not taxed.

`total = T + shipping + tax`.

## Invariants

- **I1** Every component is a non-negative integer and `total = T + shipping + tax`.
- **I2** For the same cart and coupon, a gold member never pays more than a silver member, and a
  silver member never pays more than a customer without membership.
- **I3** Sale lines are always charged their full price, except for coupons with `applies_to_sale`.
