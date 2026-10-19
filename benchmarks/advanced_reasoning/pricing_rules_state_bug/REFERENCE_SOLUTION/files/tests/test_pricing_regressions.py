"""Regression tests: thresholds evaluated after the membership discount; sale units in bundles."""

from checkout import Cart, Coupon, Customer, Line, price_cart


def test_gold_member_keeps_free_shipping():
    cart = Cart([Line("JKT", 5200)])
    gold = price_cart(cart, Customer("gold"))
    assert gold.shipping == 0
    assert gold.total == 5066
    assert gold.total <= price_cart(cart).total


def test_member_keeps_fixed_coupon_eligibility():
    cart = Cart([Line("BOOTS", 6200)])
    coupon = Coupon("SAVE10", "fixed", 1000, min_spend=6000)
    gold = price_cart(cart, Customer("gold"), coupon)
    assert gold.coupon_discount == 1000
    assert gold.total <= price_cart(cart, None, coupon).total


def test_sale_units_do_not_join_bundles():
    cart = Cart([Line("SOCK-A", 900, 2, bundle="socks"), Line("SOCK-B", 500, 1, on_sale=True, bundle="socks")])
    r = price_cart(cart)
    assert r.bundle_discount == 0
    assert r.total == 3089
