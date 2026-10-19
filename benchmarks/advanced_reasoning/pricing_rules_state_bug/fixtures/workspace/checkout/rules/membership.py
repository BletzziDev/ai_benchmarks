from checkout.config import MEMBER_PERCENT
from checkout.money import percent_of


def apply(ctx) -> None:
    rate = MEMBER_PERCENT[ctx.customer.tier]
    if not rate:
        return
    base = ctx.regular_subtotal - ctx.bundle_discount
    ctx.member_discount = percent_of(base, rate)
    ctx.notes.append(f"{ctx.customer.tier} member: {ctx.member_discount} off")
