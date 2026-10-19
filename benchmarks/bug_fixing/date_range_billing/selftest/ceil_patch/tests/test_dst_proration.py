"""Regression tests for TICKET-5120: periods containing a DST transition lost a day."""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from billing import BillingPeriod, days_between, plan_change_lines

NY = ZoneInfo("America/New_York")
BERLIN = ZoneInfo("Europe/Berlin")
SYDNEY = ZoneInfo("Australia/Sydney")


def test_spring_forward_month_has_all_its_days():
    assert BillingPeriod.monthly(2025, 3, NY).days == 31
    assert BillingPeriod.monthly(2025, 3, BERLIN).days == 31
    assert BillingPeriod.monthly(2025, 10, SYDNEY).days == 31


def test_interval_containing_transition():
    assert days_between(date(2025, 3, 25), date(2025, 4, 1), BERLIN) == 7


def test_ticket_examples():
    p = BillingPeriod.monthly(2025, 3, NY)
    assert [l.amount_cents for l in plan_change_lines(p, 2900, 9900, datetime(2025, 3, 20, 15, tzinfo=timezone.utc))] == [-1123, 3832]
    p = BillingPeriod.monthly(2025, 3, BERLIN)
    assert [l.amount_cents for l in plan_change_lines(p, 2900, 9900, datetime(2025, 3, 25, 9, tzinfo=timezone.utc))] == [-655, 2235]
