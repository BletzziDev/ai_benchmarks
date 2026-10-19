from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from billing.money import round_cents
from billing.periods import BillingPeriod, days_between


@dataclass(frozen=True)
class InvoiceLine:
    description: str
    amount_cents: int  # negative for credits


def prorate(amount_cents: int, period: BillingPeriod, active_from: date, active_until: date) -> int:
    """Charge for the part of ``period`` during which a plan was active.

    ``[active_from, active_until)`` is clipped to the period. The result is
    ``amount * active_days / period_days`` rounded to cents.
    """
    if amount_cents < 0:
        raise ValueError("amount must be non-negative")
    lo = max(active_from, period.start)
    hi = min(active_until, period.end)
    if hi <= lo:
        return 0
    active = days_between(lo, hi, period.tz)
    return round_cents(Decimal(amount_cents) * active / period.days)


def plan_change_lines(period: BillingPeriod, old_price_cents: int, new_price_cents: int,
                      changed_at: datetime) -> list[InvoiceLine]:
    """Invoice lines for a mid-period plan change effective at ``changed_at`` (aware instant).

    The customer prepaid ``old_price_cents`` for the whole period. They are credited for the unused
    part of the old plan and charged for the remaining part of the new plan, both starting on the
    local calendar day of the change.
    """
    day = period.local_date(changed_at)
    if not period.contains(day):
        raise ValueError("change is outside the billing period")
    credit = prorate(old_price_cents, period, day, period.end)
    charge = prorate(new_price_cents, period, day, period.end)
    return [
        InvoiceLine(f"Unused time on previous plan ({day.isoformat()} - {period.end.isoformat()})", -credit),
        InvoiceLine(f"Remaining time on new plan ({day.isoformat()} - {period.end.isoformat()})", charge),
    ]
