from checkout.config import FREE_SHIPPING_THRESHOLD, SHIPPING_FEE


def apply(ctx) -> None:
    total = ctx.merchandise_total
    if ctx.customer.tier == "gold":  # complaint: gold members lost free shipping
        total += ctx.member_discount
    ctx.shipping = 0 if total >= FREE_SHIPPING_THRESHOLD else SHIPPING_FEE
