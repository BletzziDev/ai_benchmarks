# AIBENCH-CANARY: 91be44c0-flaky-build-hidden — never show to evaluated models.
"""Hidden checks for tool_use/flaky_build_recovery. Run with cwd = workspace root."""

import hashlib
from decimal import Decimal as D
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import _gen_ref

WS = Path.cwd()
CSV_SHA256 = "a4e9d2d9a7ebf10d0723a5e789a810e7fccfe6a5aacde99460cbe91f8a105b7e"


def test_gen_source_csv_unchanged():
    assert hashlib.sha256((WS / "data" / "rates.csv").read_bytes()).hexdigest() == CSV_SHA256


def test_gen_tables_equal_generator_output():
    _gen_ref.SRC = WS / "data" / "rates.csv"
    assert (WS / "fxrates" / "_tables.py").read_text() == _gen_ref.render(), "tables were not produced by the generator"


def test_gen_new_currencies_present():
    from fxrates._tables import MINOR_DIGITS, USD_PER_UNIT

    assert {"PLN", "KRW", "KWD"} <= set(USD_PER_UNIT)
    assert (MINOR_DIGITS["KRW"], MINOR_DIGITS["KWD"]) == (0, 3)


@pytest.mark.parametrize("amount,src,dst,expected", [
    ("80", "BRL", "PLN", "64.07"),
    ("999999", "KRW", "USD", "752.00"),
    ("12.3456", "KWD", "USD", "40.21"),
    ("100", "PLN", "EUR", "23.16"),
])
def test_conv_values(amount, src, dst, expected):
    from fxrates import convert

    assert convert(D(amount), src, dst) == D(expected)


CODES = ["USD", "EUR", "GBP", "JPY", "CHF", "BRL", "PLN", "KRW", "KWD"]


@settings(max_examples=200, derandomize=True, database=None, deadline=None)
@given(st.decimals(min_value=0, max_value=10**9, places=2), st.sampled_from(CODES))
def test_conv_identity_is_rounding_only(x, code):
    from fxrates import convert
    from fxrates._tables import MINOR_DIGITS

    q = D(1).scaleb(-MINOR_DIGITS[code])
    assert convert(x, code, code) == x.quantize(q, rounding="ROUND_HALF_EVEN")


def test_conv_unknown_currency_still_raises():
    from fxrates import UnknownCurrency, convert

    with pytest.raises(UnknownCurrency):
        convert(D("1"), "USD", "XXX")
