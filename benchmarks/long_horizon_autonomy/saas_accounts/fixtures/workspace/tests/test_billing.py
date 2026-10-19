from datetime import date

import pytest

from acctsvc import billing


def test_add_months_regular():
    assert billing.add_months(date(2025, 1, 15), 1) == date(2025, 2, 15)
    assert billing.add_months(date(2025, 11, 10), 3) == date(2026, 2, 10)


@pytest.mark.xfail(reason="ACC-112: month-end clamping not implemented yet")
def test_add_months_month_end():
    assert billing.add_months(date(2025, 1, 31), 1) == date(2025, 2, 28)


def test_prorate_full_period_upgrade():
    assert billing.prorate(4900, 19900, date(2025, 1, 15), date(2025, 2, 15), date(2025, 1, 15)) == 15000


def test_prorate_rejects_dates_outside_period():
    with pytest.raises(ValueError):
        billing.prorate(4900, 19900, date(2025, 1, 15), date(2025, 2, 15), date(2025, 2, 15))


def test_tax_simple():
    assert billing.tax_cents(10000, 2000) == 2000
    assert billing.tax_cents(0, 2050) == 0
