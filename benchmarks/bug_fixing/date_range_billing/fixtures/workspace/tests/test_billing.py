from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from billing import BillingPeriod, days_between, plan_change_lines, prorate

TOKYO = ZoneInfo("Asia/Tokyo")
NY = ZoneInfo("America/New_York")


def test_monthly_period_lengths():
    assert BillingPeriod.monthly(2025, 2, TOKYO).days == 28
    assert BillingPeriod.monthly(2024, 2, TOKYO).days == 29
    assert BillingPeriod.monthly(2025, 12, TOKYO).end == date(2026, 1, 1)


def test_full_period_is_full_price():
    p = BillingPeriod.monthly(2025, 6, NY)
    assert prorate(3000, p, p.start, p.end) == 3000


def test_half_month_in_june():
    p = BillingPeriod.monthly(2025, 6, NY)
    assert prorate(3000, p, date(2025, 6, 16), p.end) == 1500


def test_clipping_and_empty_overlap():
    p = BillingPeriod.monthly(2025, 6, TOKYO)
    assert prorate(3000, p, date(2025, 5, 1), date(2025, 6, 11)) == 1000
    assert prorate(3000, p, date(2025, 7, 1), date(2025, 7, 9)) == 0


def test_end_is_exclusive():
    assert days_between(date(2025, 6, 1), date(2025, 6, 2), TOKYO) == 1
    assert days_between(date(2025, 6, 1), date(2025, 6, 1), TOKYO) == 0


def test_plan_change_uses_local_day():
    p = BillingPeriod.monthly(2025, 6, TOKYO)
    # 2025-06-15T20:00Z is already June 16 in Tokyo
    lines = plan_change_lines(p, 3000, 6000, datetime(2025, 6, 15, 20, 0, tzinfo=timezone.utc))
    assert [l.amount_cents for l in lines] == [-1500, 3000]


def test_rejects_naive_and_out_of_period():
    p = BillingPeriod.monthly(2025, 6, TOKYO)
    with pytest.raises(ValueError):
        plan_change_lines(p, 3000, 6000, datetime(2025, 6, 15, 20, 0))
    with pytest.raises(ValueError):
        plan_change_lines(p, 3000, 6000, datetime(2025, 8, 1, tzinfo=timezone.utc))
