# AIBENCH-CANARY: 3b91d0e4-date-range-billing-hidden — this file must never be shown to evaluated models.
"""Hidden evaluation tests for bug_fixing/date_range_billing.

test_root_*  - the DST day-count defect, in both hemispheres and both transition directions
test_inv_*   - calendar-day additivity / full-period invariants (property-based)
test_pres_*  - preserved behaviour: half-even rounding, exclusive ends, clipping, validation, API
"""

import inspect
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from billing import BillingPeriod, days_between, plan_change_lines, prorate

NY = ZoneInfo("America/New_York")
BERLIN = ZoneInfo("Europe/Berlin")
SYDNEY = ZoneInfo("Australia/Sydney")
LORD_HOWE = ZoneInfo("Australia/Lord_Howe")  # 30-minute DST shift
SANTIAGO = ZoneInfo("America/Santiago")
TOKYO = ZoneInfo("Asia/Tokyo")
ZONES = [NY, BERLIN, SYDNEY, LORD_HOWE, SANTIAGO, TOKYO, ZoneInfo("UTC"), ZoneInfo("America/Los_Angeles")]


def _true_days(a, b):
    return (b - a).days


@pytest.mark.parametrize("tz,year,month,expected", [
    (NY, 2025, 3, 31), (BERLIN, 2025, 3, 31), (SYDNEY, 2025, 10, 31), (LORD_HOWE, 2025, 10, 31),
    (SANTIAGO, 2025, 9, 30), (NY, 2024, 3, 31), (ZoneInfo("America/Los_Angeles"), 2026, 3, 31),
])
def test_root_spring_forward_months_keep_all_days(tz, year, month, expected):
    assert BillingPeriod.monthly(year, month, tz).days == expected


@pytest.mark.parametrize("tz,year,month,expected", [
    (NY, 2025, 11, 30), (BERLIN, 2025, 10, 31), (SYDNEY, 2025, 4, 30), (LORD_HOWE, 2025, 4, 30),
])
def test_root_fall_back_months_keep_exact_days(tz, year, month, expected):
    assert BillingPeriod.monthly(year, month, tz).days == expected


def test_root_interval_spanning_transition():
    assert days_between(date(2025, 3, 25), date(2025, 4, 1), BERLIN) == 7
    assert days_between(date(2025, 3, 9), date(2025, 3, 10), NY) == 1
    assert days_between(date(2025, 10, 5), date(2025, 10, 6), SYDNEY) == 1
    assert days_between(date(2025, 11, 2), date(2025, 11, 3), NY) == 1
    assert days_between(date(2025, 1, 1), date(2026, 1, 1), NY) == 365


def test_root_ticket_replay():
    p = BillingPeriod.monthly(2025, 3, NY)
    assert [l.amount_cents for l in plan_change_lines(p, 2900, 9900, datetime(2025, 3, 20, 15, tzinfo=timezone.utc))] == [-1123, 3832]
    p = BillingPeriod.monthly(2025, 3, BERLIN)
    assert [l.amount_cents for l in plan_change_lines(p, 2900, 9900, datetime(2025, 3, 25, 9, tzinfo=timezone.utc))] == [-655, 2235]


def test_root_change_on_transition_day():
    p = BillingPeriod.monthly(2025, 3, NY)
    # 2025-03-09 is the spring-forward day in New York; 23 of 31 days remain
    lines = plan_change_lines(p, 3100, 6200, datetime(2025, 3, 9, 12, tzinfo=timezone.utc))
    assert [l.amount_cents for l in lines] == [-2300, 4600]


@settings(max_examples=300, deadline=None, derandomize=True, database=None)
@given(tz=st.sampled_from(ZONES), start=st.dates(date(2020, 1, 1), date(2030, 12, 31)),
       d1=st.integers(0, 120), d2=st.integers(0, 120))
def test_inv_day_counts_are_calendar_days_and_additive(tz, start, d1, d2):
    mid = start + timedelta(days=d1)
    end = mid + timedelta(days=d2)
    a, b = days_between(start, mid, tz), days_between(mid, end, tz)
    assert a == _true_days(start, mid)
    assert b == _true_days(mid, end)
    assert days_between(start, end, tz) == a + b


@settings(max_examples=200, deadline=None, derandomize=True, database=None)
@given(tz=st.sampled_from(ZONES), year=st.integers(2020, 2030), month=st.integers(1, 12),
       amount=st.integers(0, 10**7))
def test_inv_full_period_costs_full_price(tz, year, month, amount):
    p = BillingPeriod.monthly(year, month, tz)
    assert prorate(amount, p, p.start, p.end) == amount
    nxt = BillingPeriod.monthly(year + (month == 12), month % 12 + 1, tz)
    assert p.days == _true_days(p.start, nxt.start)


def test_pres_banker_rounding():
    p = BillingPeriod(date(2025, 6, 1), date(2025, 6, 3), TOKYO)  # 2 days
    assert prorate(1, p, date(2025, 6, 2), p.end) == 0   # 0.5 -> 0 (half-even)
    assert prorate(3, p, date(2025, 6, 2), p.end) == 2   # 1.5 -> 2
    assert prorate(5, p, date(2025, 6, 2), p.end) == 2   # 2.5 -> 2


def test_pres_exclusive_end_and_clipping():
    p = BillingPeriod.monthly(2025, 6, NY)
    assert prorate(3000, p, date(2025, 5, 1), date(2025, 6, 11)) == 1000
    assert prorate(3000, p, date(2025, 7, 1), date(2025, 7, 9)) == 0
    assert prorate(3000, p, date(2025, 6, 30), date(2025, 7, 1)) == 100
    assert days_between(date(2025, 6, 1), date(2025, 6, 1), NY) == 0


def test_pres_validation():
    with pytest.raises(ValueError):
        days_between(date(2025, 6, 2), date(2025, 6, 1), NY)
    with pytest.raises(ValueError):
        BillingPeriod(date(2025, 6, 1), date(2025, 6, 1), NY)
    p = BillingPeriod.monthly(2025, 6, NY)
    with pytest.raises(ValueError):
        prorate(-1, p, p.start, p.end)
    with pytest.raises(ValueError):
        plan_change_lines(p, 1, 2, datetime(2025, 6, 3, 12))


def test_pres_local_date_conversion():
    p = BillingPeriod.monthly(2025, 6, TOKYO)
    lines = plan_change_lines(p, 3000, 6000, datetime(2025, 6, 15, 20, 0, tzinfo=timezone.utc))
    assert [l.amount_cents for l in lines] == [-1500, 3000]
    p = BillingPeriod.monthly(2025, 6, ZoneInfo("America/Los_Angeles"))
    lines = plan_change_lines(p, 3000, 6000, datetime(2025, 6, 16, 3, 0, tzinfo=timezone.utc))  # still June 15 in LA
    assert [l.amount_cents for l in lines] == [-1600, 3200]


def test_pres_api():
    names = lambda f: list(inspect.signature(f).parameters)
    assert names(days_between) == ["start", "end", "tz"]
    assert names(prorate) == ["amount_cents", "period", "active_from", "active_until"]
    assert names(plan_change_lines) == ["period", "old_price_cents", "new_price_cents", "changed_at"]
    assert BillingPeriod.monthly(2025, 2, NY).end == date(2025, 3, 1)
