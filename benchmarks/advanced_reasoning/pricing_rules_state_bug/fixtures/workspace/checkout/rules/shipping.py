from checkout.config import FREE_SHIPPING_THRESHOLD, SHIPPING_FEE


def apply(ctx) -> None:
    ctx.shipping = 0 if ctx.merchandise_total >= FREE_SHIPPING_THRESHOLD else SHIPPING_FEE
