from __future__ import annotations

from dataclasses import dataclass, field

from checkout.models import Cart, Coupon, Customer, Receipt
from checkout.rules import bundles, coupons, membership, shipping, tax


@dataclass
class PricingContext:
    cart: Cart
    customer: Customer
    coupon: Coupon | None
    subtotal: int = 0          # M
    regular_subtotal: int = 0  # R
    sale_subtotal: int = 0     # S
    bundle_discount: int = 0   # B
    member_discount: int = 0   # Dm
    coupon_discount: int = 0   # Dc
    shipping: int = 0
    tax: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def regular_after_discounts(self) -> int:
        """Regular-line subtotal after bundle and membership discounts (R - B - Dm)."""
        return self.regular_subtotal - self.bundle_discount - self.member_discount

    @property
    def merchandise_total(self) -> int:
        """T = M - B - Dm - Dc."""
        return self.subtotal - self.bundle_discount - self.member_discount - self.coupon_discount


# Membership last so that it cannot affect coupon or shipping thresholds.
RULES = [bundles.apply, coupons.apply, shipping.apply, tax.apply, membership.apply]


def price_cart(cart: Cart, customer: Customer | None = None, coupon: Coupon | None = None) -> Receipt:
    ctx = PricingContext(cart, customer or Customer(), coupon)
    ctx.subtotal = sum(l.subtotal for l in cart.lines)
    ctx.regular_subtotal = sum(l.subtotal for l in cart.lines if not l.on_sale)
    ctx.sale_subtotal = ctx.subtotal - ctx.regular_subtotal
    for rule in RULES:
        rule(ctx)
    t = ctx.merchandise_total
    return Receipt(ctx.subtotal, ctx.bundle_discount, ctx.member_discount, ctx.coupon_discount, t,
                   ctx.shipping, ctx.tax, t + ctx.shipping + ctx.tax, ctx.notes)
