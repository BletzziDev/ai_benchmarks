# AIBENCH-CANARY: 9d41b6e3-legacy-report-refactor-hidden — this file must never be shown to evaluated models.
"""Behavioural equivalence of the refactored ledgerly.reports against a frozen copy of the original.

Groups: test_equiv_* (outputs and exceptions identical on generated and edge-case inputs),
test_api_* (public API and module layout).
"""

import copy
import inspect
import os
import sys

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, os.path.dirname(__file__))
import legacy_original as orig  # noqa: E402

import ledgerly  # noqa: E402
from ledgerly import reports as new  # noqa: E402

CURRENCIES = ["USD", "EUR", "GBP", "BRL"]
SETTINGS = settings(max_examples=150, deadline=None, derandomize=True, database=None,
                    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large])

amount = st.one_of(st.floats(min_value=0, max_value=5000, allow_nan=False, allow_infinity=False).map(lambda x: round(x, 2)),
                   st.sampled_from([0.0, 0.01, 0.005, 0.015, 1.005, 2.675, 99.995, 1000.0]))
tx = st.fixed_dictionaries({
    "id": st.from_regex(r"T[0-9]{3}", fullmatch=True),
    "date": st.dates(min_value=__import__("datetime").date(2024, 1, 25), max_value=__import__("datetime").date(2024, 3, 5)).map(str),
    "customer": st.sampled_from(["C001", "C002", "C003", "C004", "C005", "C006", ""]),
    "type": st.sampled_from(["sale", "sale", "sale", "refund", "fee", "chargeback"]),
    "amount": amount,
    "currency": st.sampled_from(CURRENCIES),
    "category": st.sampled_from(["books", "music", "electronics", "uncategorized", ""]),
})
txs = st.lists(tx, max_size=40)
months = st.sampled_from(["2024-01", "2024-02", "2024-03", "2024-12"])


def same(f_new, f_old, *args, **kwargs):
    """Call both with deep copies; require equal results or the same exception type."""
    a = copy.deepcopy(args)
    b = copy.deepcopy(args)
    try:
        expected = f_old(*b, **kwargs)
    except Exception as e:  # noqa: BLE001
        with pytest.raises(type(e)):
            f_new(*a, **kwargs)
        return
    got = f_new(*a, **kwargs)
    assert got == expected
    assert a == b, "input transactions were mutated differently"


@SETTINGS
@given(txs, months, st.sampled_from(CURRENCIES + ["JPY"]), st.sampled_from(["text", "markdown", "csv"]))
def test_equiv_monthly_report(t, m, cur, fmt):
    same(new.generate_monthly_report, orig.generate_monthly_report, t, m, cur, fmt)


@SETTINGS
@given(txs, months)
def test_equiv_summary_and_category_report(t, m):
    same(new.summarize_by_category, orig.summarize_by_category, t, m)
    for fmt in ("text", "markdown"):
        same(new.generate_category_report, orig.generate_category_report, t, m, fmt)


@SETTINGS
@given(txs, st.sampled_from(["C001", "C002", "", "C999"]), st.sampled_from(["2024-01-01", "2024-02-10", "2024-03-01"]),
       st.sampled_from(["2024-02-29", "2024-03-31", "2024-01-31"]), st.sampled_from(["text", "csv"]))
def test_equiv_customer_statement(t, c, start, end, fmt):
    same(new.generate_customer_statement, orig.generate_customer_statement, t, c, start, end, fmt)


@SETTINGS
@given(txs, months)
def test_equiv_payout_schedule(t, m):
    same(new.generate_payout_schedule, orig.generate_payout_schedule, t, m)


@SETTINGS
@given(txs, st.sampled_from([None, "2024-02", "2024-03"]))
def test_equiv_export_csv(tmp_path_factory, t, m):
    d = tmp_path_factory.mktemp("exp")
    pa, pb = d / "new.csv", d / "old.csv"
    try:
        expected = orig.export_csv(copy.deepcopy(t), pb, month=m)
    except Exception as e:  # noqa: BLE001
        with pytest.raises(type(e)):
            new.export_csv(copy.deepcopy(t), pa, month=m)
        return
    assert new.export_csv(copy.deepcopy(t), pa, month=m) == expected
    assert pa.read_bytes() == pb.read_bytes()


CSV_CASES = {
    "ok": "id,date,customer,type,amount,currency,category\nT1,2024-03-01,C1,sale,10.5,eur,books\n\nT2,2024-03-02,C2,fee,1,,\n",
    "bad_type": "id,date,customer,type,amount,currency,category\nT1,2024-03-01,C1,gift,10,USD,x\n",
    "bad_amount": "id,date,customer,type,amount,currency,category\nT1,2024-03-01,C1,sale,ten,USD,x\n",
    "bad_date": "id,date,customer,type,amount,currency,category\nT1,2024-13-01,C1,sale,10,USD,x\n",
    "short_rows": "ID , Date,Customer,TYPE,amount\nT1,2024-03-01,C1,sale,3\nT2,2024-03-02\n",
    "missing_amount_col": "id,date,customer,type\nT1,2024-03-01,C1,sale\n",
    "empty": "",
    "header_only": "id,date,customer,type,amount,currency,category\n",
    "blank_lines": "id,date,customer,type,amount,currency,category\n\n,\nT1,2024-03-01,C1,refund, 7.25 ,gbp,\n",
}


@pytest.mark.parametrize("name", sorted(CSV_CASES))
def test_equiv_load_transactions(tmp_path, name):
    p = tmp_path / f"{name}.csv"
    p.write_text(CSV_CASES[name])
    same(new.load_transactions, orig.load_transactions, p)


@pytest.mark.parametrize("args", [
    ([], "2024-3", "USD", "text"), ([], "202403", "USD", "text"), ([], "2024-03", "USD", "html"),
    ([{"id": "T1", "date": "2024-03-01", "customer": "C1", "type": "sale", "amount": 5.0, "currency": "JPY", "category": "x"}],
     "2024-03", "USD", "text"),
])
def test_equiv_monthly_errors(args):
    same(new.generate_monthly_report, orig.generate_monthly_report, *args)


def test_equiv_statement_errors():
    same(new.generate_customer_statement, orig.generate_customer_statement, [], "C1", "2024-03-02", "2024-03-01")
    same(new.generate_customer_statement, orig.generate_customer_statement, [], "C1", "2024-03-01", "2024-03-02", "markdown")
    same(new.generate_customer_statement, orig.generate_customer_statement, [], "C1", "03/01/2024", "2024-03-02")


def test_equiv_rounding_edge_cases():
    edge = [{"id": f"T{i}", "date": "2024-03-0%d" % (1 + i % 9), "customer": "C%d" % (i % 3), "type": "sale",
             "amount": a, "currency": c, "category": "books"}
            for i, (a, c) in enumerate([(0.005, "USD"), (1.005, "EUR"), (2.675, "GBP"), (99.995, "BRL"), (0.015, "USD")])]
    for cur in CURRENCIES:
        for fmt in ("text", "markdown", "csv"):
            same(new.generate_monthly_report, orig.generate_monthly_report, edge, "2024-03", cur, fmt)


# ----------------------------------------------------------------------------- API

PUBLIC = ["load_transactions", "summarize_by_category", "generate_monthly_report", "generate_customer_statement",
          "export_csv", "generate_category_report", "generate_payout_schedule"]


def test_api_public_functions_and_signatures():
    for name in PUBLIC:
        f_new, f_old = getattr(ledgerly, name), getattr(orig, name)
        pn = [(p.name, p.default, p.kind) for p in inspect.signature(f_new).parameters.values()]
        po = [(p.name, p.default, p.kind) for p in inspect.signature(f_old).parameters.values()]
        assert pn == po, f"{name}: signature changed {pn} != {po}"
        assert getattr(new, name) is f_new, f"ledgerly.reports.{name} must remain importable"


def test_api_package_exports():
    assert set(PUBLIC) <= set(ledgerly.__all__)
