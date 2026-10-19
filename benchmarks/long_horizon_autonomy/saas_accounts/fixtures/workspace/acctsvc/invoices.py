"""Invoice generation for the current billing period."""

from __future__ import annotations

import sqlite3
from datetime import date

from acctsvc import billing, numbering
from acctsvc.db import utcnow
from acctsvc.plans import get_plan
from acctsvc.subscriptions import get_subscription


def generate_invoice(conn: sqlite3.Connection, org_id: int, tax_rate_bp: int = 0,
                     issued_on: date | None = None) -> int:
    """Create an invoice for the current period: plan charge + pending adjustments + tax."""
    issued_on = issued_on or date.today()
    sub = get_subscription(conn, org_id)
    plan = get_plan(sub["plan"])
    lines: list[tuple[str, int]] = [
        (f"{plan.name} plan {sub['period_start']} to {sub['period_end']}", plan.monthly_price_cents)]
    adjustments = list(conn.execute(
        "SELECT id, description, amount_cents FROM subscription_adjustments WHERE org_id = ? AND invoiced = 0 "
        "ORDER BY id", (org_id,)))
    lines += [(a["description"], a["amount_cents"]) for a in adjustments]
    subtotal = sum(amount for _, amount in lines)
    tax = billing.tax_cents(subtotal, tax_rate_bp)
    number = numbering.next_invoice_number(conn, issued_on.year)
    cur = conn.execute(
        "INSERT INTO invoices(org_id, number, period_start, period_end, subtotal_cents, tax_cents, total_cents, "
        "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (org_id, number, sub["period_start"], sub["period_end"], subtotal, tax, subtotal + tax, utcnow()))
    invoice_id = int(cur.lastrowid)
    conn.executemany("INSERT INTO invoice_lines(invoice_id, description, amount_cents) VALUES (?, ?, ?)",
                     [(invoice_id, d, a) for d, a in lines])
    conn.executemany("UPDATE subscription_adjustments SET invoiced = 1 WHERE id = ?", [(a["id"],) for a in adjustments])
    return invoice_id


def get_invoice(conn: sqlite3.Connection, invoice_id: int) -> dict:
    inv = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    if inv is None:
        raise KeyError(invoice_id)
    lines = [dict(r) for r in conn.execute(
        "SELECT description, amount_cents FROM invoice_lines WHERE invoice_id = ? ORDER BY id", (invoice_id,))]
    return {**dict(inv), "lines": lines}


def list_invoices(conn: sqlite3.Connection, org_id: int) -> list[sqlite3.Row]:
    return list(conn.execute("SELECT * FROM invoices WHERE org_id = ? ORDER BY number", (org_id,)))
