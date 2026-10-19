from decimal import Decimal as D

import pytest

from fxrates import UnknownCurrency, convert, format_amount


@pytest.mark.parametrize("amount,src,dst,expected", [
    ("100", "USD", "EUR", "92.23"),
    ("2500", "JPY", "USD", "16.78"),
    ("19.99", "EUR", "JPY", "3229"),
])
def test_core_currencies(amount, src, dst, expected):
    assert convert(D(amount), src, dst) == D(expected)


def test_new_currencies_from_march_rates_update():
    # Added to data/rates.csv in the March rates update (FIN-882).
    assert convert(D("100"), "PLN", "EUR") == D("23.16")
    assert convert(D("150000"), "KRW", "JPY") == D("16806")
    assert convert(D("1"), "USD", "KWD") == D("0.307")


def test_formatting_uses_minor_units():
    assert format_amount(D("1234.5678"), "KWD") == "1,234.568 KWD (Kuwaiti dinar)"
    assert format_amount(D("1234567"), "KRW") == "1,234,567 KRW (South Korean won)"


def test_unknown_currency():
    with pytest.raises(UnknownCurrency):
        convert(D("1"), "USD", "XXX")
