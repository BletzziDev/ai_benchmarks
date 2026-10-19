"""Billing arithmetic: periods, proration and tax. See docs/BILLING.md for the rules."""

from __future__ import annotations

import calendar
from datetime import date
from fractions import Fraction


def add_months(d: date, months: int) -> date:
    """Same day-of-month ``months`` later (see docs/BILLING.md#periods)."""
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def round_half_up(x: Fraction) -> int:
    """Round to the nearest integer, .5 away from zero (symmetric for negatives)."""
    sign = -1 if x < 0 else 1
    a = abs(x)
    return sign * int(a + Fraction(1, 2))


def period(anchor: date, index: int) -> tuple[date, date]:
    """Billing period ``index`` (0-based) of a subscription anchored on ``anchor``: [start, end)."""
    return add_months(anchor, index), add_months(anchor, index + 1)


def prorate(old_price_cents: int, new_price_cents: int, period_start: date, period_end: date,
            change_date: date) -> int:
    """Amount to charge (positive) or credit (negative) when the plan changes mid-period."""
    if not period_start <= change_date < period_end:
        raise ValueError("change_date must fall inside the current period")
    total_days = (period_end - period_start).days
    remaining_days = (period_end - change_date).days
    return round_half_up(Fraction((new_price_cents - old_price_cents) * remaining_days, total_days))


def tax_cents(subtotal_cents: int, rate_bp: int) -> int:
    """Tax for ``subtotal_cents`` at ``rate_bp`` basis points (1 bp = 0.01%)."""
    return round_half_up(Fraction(subtotal_cents * rate_bp, 10000))
