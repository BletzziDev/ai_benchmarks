"""ACC-106: pin down the invoice numbering rules (docs/BILLING.md#invoice-numbers)."""

from datetime import date

import pytest

from acctsvc import invoices, numbering, subscriptions


def test_format_and_padding():
    assert numbering.format_invoice_number(2025, 1) == "INV-2025-00001"
    assert numbering.format_invoice_number(2025, 12345) == "INV-2025-12345"
    with pytest.raises(ValueError):
        numbering.format_invoice_number(2025, 0)


def test_parse_roundtrip_and_rejects_garbage():
    assert numbering.parse_invoice_number("INV-2024-00042") == (2024, 42)
    for bad in ("INV-2024-42", "inv-2024-00042", "INV-24-00042", ""):
        with pytest.raises(ValueError):
            numbering.parse_invoice_number(bad)


def test_first_number_of_a_year_and_increment(conn):
    assert numbering.next_invoice_number(conn, 2025) == "INV-2025-00001"


def test_sequence_restarts_each_year_and_is_never_reused(conn, org):
    subscriptions.subscribe(conn, org["id"], "team", date(2024, 12, 1))
    nums = [invoices.get_invoice(conn, invoices.generate_invoice(conn, org["id"], issued_on=d))["number"]
            for d in (date(2024, 12, 1), date(2024, 12, 2), date(2025, 1, 1), date(2025, 1, 2))]
    assert nums == ["INV-2024-00001", "INV-2024-00002", "INV-2025-00001", "INV-2025-00002"]
    assert numbering.next_invoice_number(conn, 2024) == "INV-2024-00003"
