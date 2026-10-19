# AIBENCH-CANARY: c84e2f17-pricing-rules-hidden — never shown to evaluated models.
"""Independent oracle implementing docs/RULES.md v4 literally (plain tuples, Fractions)."""

from fractions import Fraction
from math import floor

RATES = {"none": Fraction(0), "silver": Fraction(5, 100), "gold": Fraction(10, 100)}


def rnd(x: Fraction) -> int:
    """Round half up (all values are non-negative here)."""
    return floor(x + Fraction(1, 2))


def price(lines, tier="none", coupon=None):
    """lines: iterable of (unit_price, qty, on_sale, bundle). coupon: (kind, value, min_spend, applies_to_sale) or None.
    Returns dict with M, B, Dm, Dc, T, shipping, tax, total."""
    lines = list(lines)
    M = sum(p * q for p, q, _, _ in lines)
    R = sum(p * q for p, q, s, _ in lines if not s)
    S = M - R
    groups = {}
    for p, q, s, b in lines:
        if b and not s:
            groups.setdefault(b, []).extend([p] * q)
    B = 0
    for units in groups.values():
        units = sorted(units, reverse=True)
        B += sum(units[i] for i in range(2, len(units), 3))
    Dm = rnd(RATES[tier] * (R - B))
    Dc = 0
    if coupon is not None:
        kind, value, min_spend, ats = coupon
        threshold_base = (R - B) + (S if ats else 0)
        base = (R - B - Dm) + (S if ats else 0)
        if threshold_base >= min_spend:
            Dc = rnd(Fraction(value) / 100 * base) if kind == "percent" else min(value, base)
    T = M - B - Dm - Dc
    shipping = 0 if (M - B - Dc) >= 5000 else 599
    tax = rnd(Fraction(825, 10000) * T)
    return {"M": M, "B": B, "Dm": Dm, "Dc": Dc, "T": T, "shipping": shipping, "tax": tax, "total": T + shipping + tax}
