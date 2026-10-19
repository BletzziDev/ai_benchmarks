"""Invoice numbers: ``INV-<year>-<sequence>``, sequence zero-padded to 5 digits and restarting at
00001 every calendar year (legal requirement, see docs/BILLING.md#invoice-numbers)."""

from __future__ import annotations

import re
import sqlite3

NUMBER_RE = re.compile(r"^INV-(\d{4})-(\d{5})$")


def format_invoice_number(year: int, seq: int) -> str:
    if seq < 1:
        raise ValueError("sequence starts at 1")
    return f"INV-{year}-{seq:05d}"


def parse_invoice_number(number: str) -> tuple[int, int]:
    m = NUMBER_RE.match(number)
    if not m:
        raise ValueError(f"not an invoice number: {number!r}")
    return int(m.group(1)), int(m.group(2))


def next_invoice_number(conn: sqlite3.Connection, year: int) -> str:
    row = conn.execute("SELECT number FROM invoices WHERE number LIKE ? ORDER BY number DESC LIMIT 1",
                       (f"INV-{year}-%",)).fetchone()
    seq = parse_invoice_number(row["number"])[1] + 1 if row else 1
    return format_invoice_number(year, seq)
