from decimal import Decimal

import pytest

from checkout import Cart, Coupon, Customer, Line, price_cart


def test_simple_cart_below_free_shipping():
    r = price_cart(Cart([Line("MUG", 1200, 2)]))
    assert (r.subtotal, r.shipping, r.tax, r.total) == (2400, 599, 198, 3197)


def test_free_shipping_for_large_cart():
    r = price_cart(Cart([Line("COAT", 8000)]))
    assert r.shipping == 0
    assert r.total == 8000 + 660


def test_three_for_two_bundle():
    r = price_cart(Cart([Line("TEE-A", 2000, 2, bundle="tees"), Line("TEE-B", 1500, 1, bundle="tees")]))
    assert r.bundle_discount == 1500


def test_gold_discount_on_regular_items_only():
    cart = Cart([Line("COAT", 9000), Line("HAT", 1000, on_sale=True)])
    r = price_cart(cart, Customer("gold"))
    assert r.member_discount == 900
    assert r.merchandise_total == 9100


def test_percent_coupon_after_membership():
    cart = Cart([Line("COAT", 10000)])
    r = price_cart(cart, Customer("silver"), Coupon("TEN", "percent", Decimal(10)))
    assert (r.member_discount, r.coupon_discount, r.merchandise_total) == (500, 950, 8550)


def test_fixed_coupon_min_spend_not_met():
    r = price_cart(Cart([Line("MUG", 1200)]), coupon=Coupon("SAVE10", "fixed", 1000, min_spend=6000))
    assert r.coupon_discount == 0


def test_fixed_coupon_capped_at_base():
    r = price_cart(Cart([Line("PEN", 300)]), coupon=Coupon("BIG", "fixed", 1000))
    assert r.coupon_discount == 300 and r.merchandise_total == 0


def test_tax_rounds_half_up_on_total():
    r = price_cart(Cart([Line("A", 200)]))  # 8.25% of 200 = 16.5 -> 17
    assert r.tax == 17


def test_validation():
    with pytest.raises(ValueError):
        Line("X", -1)
    with pytest.raises(ValueError):
        Customer("platinum")
