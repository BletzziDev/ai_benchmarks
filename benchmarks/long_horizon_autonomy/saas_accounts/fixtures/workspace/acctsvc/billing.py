"""Billing arithmetic: periods, proration and tax. See docs/BILLING.md for the rules."""

from __future__ import annotations

from datetime import date, timedelta


def add_months(d: date, months: int) -> date:
    """Same day-of-month ``months`` later (see docs/BILLING.md#periods)."""
    y, m = divmod(d.month - 1 + months, 12)
    first = date(d.year + y, m + 1, 1)
    return first + timedelta(days=d.day - 1)


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
    credit = old_price_cents * remaining_days / total_days
    charge = new_price_cents * remaining_days / total_days
    return round(charge) - round(credit)


def tax_cents(subtotal_cents: int, rate_bp: int) -> int:
    """Tax for ``subtotal_cents`` at ``rate_bp`` basis points (1 bp = 0.01%)."""
    return round(subtotal_cents * rate_bp / 10000)
