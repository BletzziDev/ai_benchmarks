from decimal import Decimal

from checkout.money import percent_of


def apply(ctx) -> None:
    c = ctx.coupon
    if c is None:
        return
    sale = ctx.sale_subtotal if c.applies_to_sale else 0
    # min_spend ignores the membership discount: membership must never cost a coupon (RULES.md step 3).
    threshold_base = ctx.regular_subtotal - ctx.bundle_discount + sale
    base = ctx.regular_after_discounts + sale
    if threshold_base < c.min_spend:
        ctx.notes.append(f"coupon {c.code}: minimum spend {c.min_spend} not reached")
        return
    if c.kind == "percent":
        ctx.coupon_discount = percent_of(base, Decimal(c.value))
    else:
        ctx.coupon_discount = min(int(c.value), base)
    ctx.notes.append(f"coupon {c.code}: {ctx.coupon_discount} off")
