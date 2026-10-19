# AIBENCH-CANARY: c84e2f17-pricing-rules-hidden — this file must never be shown to evaluated models.
"""Hidden tests for advanced_reasoning/pricing_rules_state_bug.

test_root_*  defects that only appear in specific state combinations
test_inv_*   model-based comparison with an independent RULES.md oracle + invariants I1-I3
test_pres_*  behaviour that must not change (order of rules, rounding, tax base, API)
"""

import inspect
from decimal import Decimal

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from _pricing_oracle import price as oracle
from checkout import Cart, Coupon, Customer, Line, Receipt, price_cart


def run(lines, tier="none", coupon=None):
    cart = Cart([Line(f"SKU{i}", p, q, on_sale=s, bundle=b) for i, (p, q, s, b) in enumerate(lines)])
    c = None
    if coupon is not None:
        kind, value, min_spend, ats = coupon
        c = Coupon("C", kind, Decimal(value) if kind == "percent" else value, min_spend=min_spend, applies_to_sale=ats)
    return price_cart(cart, Customer(tier), c)


def as_dict(r: Receipt):
    return {"M": r.subtotal, "B": r.bundle_discount, "Dm": r.member_discount, "Dc": r.coupon_discount,
            "T": r.merchandise_total, "shipping": r.shipping, "tax": r.tax, "total": r.total}


# ------------------------------------------------------------------ root causes

@pytest.mark.parametrize("tier,price_,expected_total", [("gold", 5200, 5066), ("silver", 5100, 5245), ("gold", 5000, 4871)])
def test_root_member_keeps_free_shipping(tier, price_, expected_total):
    r = run([(price_, 1, False, None)], tier)
    assert r.shipping == 0
    assert r.total == expected_total


def test_root_member_keeps_free_shipping_with_coupon_and_sale():
    lines = [(4000, 1, False, None), (1300, 1, True, None)]
    coupon = ("fixed", 200, 0, False)
    assert as_dict(run(lines, "gold", coupon)) == oracle(lines, "gold", coupon)
    assert run(lines, "gold", coupon).shipping == 0


@pytest.mark.parametrize("tier", ["silver", "gold"])
def test_root_member_keeps_fixed_coupon(tier):
    lines = [(6200, 1, False, None)]
    coupon = ("fixed", 1000, 6000, False)
    r = run(lines, tier, coupon)
    assert r.coupon_discount == 1000
    assert as_dict(r) == oracle(lines, tier, coupon)


def test_root_member_keeps_percent_coupon_threshold_with_sale_lines():
    lines = [(3000, 1, False, None), (3100, 1, True, None)]
    coupon = ("percent", 15, 6000, True)
    r = run(lines, "gold", coupon)
    assert as_dict(r) == oracle(lines, "gold", coupon)
    assert r.coupon_discount > 0


def test_root_sale_unit_not_free_in_bundle():
    lines = [(900, 2, False, "socks"), (500, 1, True, "socks")]
    r = run(lines)
    assert r.bundle_discount == 0 and r.total == 3089


def test_root_sale_unit_does_not_shift_free_unit():
    lines = [(900, 2, False, "socks"), (800, 1, False, "socks"), (1000, 1, True, "socks")]
    r = run(lines)
    assert r.bundle_discount == 800
    assert as_dict(r) == oracle(lines)


def test_root_combination_member_bundle_sale_threshold():
    lines = [(2400, 2, False, "kit"), (1100, 1, False, "kit"), (700, 1, True, "kit"), (300, 1, False, None)]
    for tier in ("none", "silver", "gold"):
        for coupon in (None, ("fixed", 500, 5000, False), ("percent", 10, 5000, True)):
            assert as_dict(run(lines, tier, coupon)) == oracle(lines, tier, coupon), (tier, coupon)


# ------------------------------------------------------------------ model-based / invariants

line_st = st.tuples(st.integers(0, 6000), st.integers(1, 4), st.booleans(), st.sampled_from([None, "a", "b"]))
coupon_st = st.one_of(
    st.none(),
    st.tuples(st.just("percent"), st.integers(0, 50), st.integers(0, 9000), st.booleans()),
    st.tuples(st.just("fixed"), st.integers(0, 3000), st.integers(0, 9000), st.booleans()),
)
SETTINGS = dict(max_examples=400, deadline=None, derandomize=True, database=None,
                suppress_health_check=[HealthCheck.too_slow])


@settings(**SETTINGS)
@given(st.lists(line_st, min_size=1, max_size=7), st.sampled_from(["none", "silver", "gold"]), coupon_st)
def test_inv_matches_specification(lines, tier, coupon):
    assert as_dict(run(lines, tier, coupon)) == oracle(lines, tier, coupon)


@settings(**SETTINGS)
@given(st.lists(line_st, min_size=1, max_size=7), coupon_st)
def test_inv_membership_never_costs_more(lines, coupon):
    none_, silver, gold = (run(lines, t, coupon).total for t in ("none", "silver", "gold"))
    assert gold <= silver <= none_


@settings(**SETTINGS)
@given(st.lists(line_st, min_size=1, max_size=7), st.sampled_from(["none", "silver", "gold"]), coupon_st)
def test_inv_components_consistent_and_sale_lines_full_price(lines, tier, coupon):
    r = run(lines, tier, coupon)
    for v in (r.subtotal, r.bundle_discount, r.member_discount, r.coupon_discount, r.merchandise_total, r.shipping, r.tax):
        assert isinstance(v, int) and v >= 0
    assert r.total == r.merchandise_total + r.shipping + r.tax
    if coupon is None or not coupon[3]:
        sale = sum(p * q for p, q, s, _ in lines if s)
        assert r.merchandise_total >= sale


# ------------------------------------------------------------------ preservation

def test_pres_rule_order_percent_coupon_after_membership():
    r = run([(10000, 1, False, None)], "silver", ("percent", 10, 0, False))
    assert (r.member_discount, r.coupon_discount, r.merchandise_total) == (500, 950, 8550)


def test_pres_tax_on_merchandise_total_half_up():
    r = run([(200, 1, False, None)])
    assert r.tax == 17
    r = run([(10000, 1, False, None)], "gold")
    assert r.tax == 743  # tax on T after the membership discount: 8.25% of 9000 = 742.5 -> 743 (half up)


def test_pres_bundles_regular_and_multiple_groups():
    lines = [(2000, 2, False, "tees"), (1500, 1, False, "tees"), (3000, 3, False, "jeans"), (100, 1, False, "jeans")]
    r = run(lines)
    assert r.bundle_discount == 1500 + 3000


def test_pres_fixed_coupon_cap_and_min_spend():
    r = run([(300, 1, False, None)], coupon=("fixed", 1000, 0, False))
    assert r.coupon_discount == 300 and r.merchandise_total == 0
    r = run([(1200, 1, False, None)], coupon=("fixed", 1000, 6000, False))
    assert r.coupon_discount == 0


def test_pres_shipping_fee_and_threshold_without_membership():
    assert run([(4999, 1, False, None)]).shipping == 599
    assert run([(5000, 1, False, None)]).shipping == 0
    assert run([(5600, 1, False, None)], coupon=("fixed", 700, 0, False)).shipping == 599


def test_pres_api_and_validation():
    assert list(inspect.signature(price_cart).parameters) == ["cart", "customer", "coupon"]
    assert [f for f in Receipt.__dataclass_fields__] == ["subtotal", "bundle_discount", "member_discount", "coupon_discount",
                                                         "merchandise_total", "shipping", "tax", "total", "notes"]
    with pytest.raises(ValueError):
        Line("X", 100, 0)
    with pytest.raises(ValueError):
        Coupon("X", "bogus", 1)
    assert price_cart(Cart([Line("A", 100)])).total == 100 + 599 + 8
