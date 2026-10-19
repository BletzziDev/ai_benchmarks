from checkout.config import FREE_SHIPPING_THRESHOLD, SHIPPING_FEE


def apply(ctx) -> None:
    # The threshold ignores the membership discount (RULES.md step 5): M - B - Dc.
    qualifying = ctx.subtotal - ctx.bundle_discount - ctx.coupon_discount
    ctx.shipping = 0 if qualifying >= FREE_SHIPPING_THRESHOLD else SHIPPING_FEE
