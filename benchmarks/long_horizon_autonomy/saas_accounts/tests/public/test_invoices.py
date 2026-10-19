from datetime import date

from acctsvc import invoices, subscriptions


def test_invoice_for_plan(conn, org):
    subscriptions.subscribe(conn, org["id"], "team", date(2025, 1, 15))
    inv = invoices.get_invoice(conn, invoices.generate_invoice(conn, org["id"], tax_rate_bp=2000,
                                                                 issued_on=date(2025, 1, 15)))
    assert inv["number"] == "INV-2025-00001"
    assert inv["subtotal_cents"] == 4900
    assert inv["tax_cents"] == 980
    assert inv["total_cents"] == 5880
    assert len(inv["lines"]) == 1


def test_adjustments_are_invoiced_once(conn, org):
    subscriptions.subscribe(conn, org["id"], "team", date(2025, 1, 15))
    subscriptions.change_plan(conn, org["id"], "business", date(2025, 1, 15))
    first = invoices.get_invoice(conn, invoices.generate_invoice(conn, org["id"], issued_on=date(2025, 1, 20)))
    second = invoices.get_invoice(conn, invoices.generate_invoice(conn, org["id"], issued_on=date(2025, 1, 21)))
    assert len(first["lines"]) == 2
    assert len(second["lines"]) == 1
    assert second["number"] == "INV-2025-00002"
