"""Merchant reports: monthly report, customer statements, category summaries, payouts, CSV export.

Output formats are a contract with downstream consumers (dashboard, finance macros, emails), so
numbers are computed with exactly the same float operations, in the same order, as before.
"""

from __future__ import annotations

import csv
import datetime
from dataclasses import dataclass, field
from os import PathLike
from typing import Any, Callable

Transaction = dict[str, Any]

TRANSACTION_TYPES = ("sale", "refund", "fee", "chargeback")
FX_TO_USD = {"EUR": 1.08, "GBP": 1.27, "BRL": 0.2}  # multiply a foreign amount to get USD
SALES_TAX_RATES = {"EUR": 0.20, "GBP": 0.20, "BRL": 0.17}  # no tax is collected on USD sales
PROCESSING_FEE_RATE = 0.029
PROCESSING_FEE_FIXED = 0.30
CHARGEBACK_FEE = 15.0
REFUND_RATE_WARNING_PCT = 10
TOP_CUSTOMERS = 5
PAYOUT_WINDOW_DAYS = 7
RESERVE_CATEGORY = "electronics"
RESERVE_SHARE = 0.1
UNCATEGORIZED = "uncategorized"


# ----------------------------------------------------------------------------- helpers


def _validate_month(month: str) -> None:
    if len(month) != 7 or month[4] != "-":
        raise ValueError("month must be YYYY-MM")


def _fx_rate(currency: str) -> float:
    try:
        return FX_TO_USD[currency]
    except KeyError:
        raise ValueError("unknown currency " + currency) from None


def to_usd(tx: Transaction) -> float:
    amount = tx["amount"]
    return amount if tx["currency"] == "USD" else amount * _fx_rate(tx["currency"])


def processing_fee(amount_usd: float) -> float:
    return amount_usd * PROCESSING_FEE_RATE + PROCESSING_FEE_FIXED


def _money(value: float) -> str:
    return "{:,.2f}".format(round(value, 2))


def _in_month(tx: Transaction, month: str) -> bool:
    return tx["date"][:7] == month


def _by_date(transactions: list[Transaction]) -> list[Transaction]:
    return sorted(transactions, key=lambda t: (t["date"], t.get("id", "")))


# ----------------------------------------------------------------------------- loading / export


def _parse_row(header: list[str], row: list[str], line: int) -> Transaction:
    rec: Transaction = {name: (row[i].strip() if i < len(row) else "") for i, name in enumerate(header)}
    if rec.get("type") not in TRANSACTION_TYPES:
        raise ValueError("line %d: bad type %r" % (line, rec.get("type")))
    try:
        rec["amount"] = float(rec["amount"])
    except Exception:
        raise ValueError("line %d: bad amount %r" % (line, rec.get("amount"))) from None
    rec["currency"] = (rec.get("currency", "") or "USD").upper()
    if rec.get("category", "") == "":
        rec["category"] = UNCATEGORIZED
    try:
        datetime.date.fromisoformat(rec["date"])
    except Exception:
        raise ValueError("line %d: bad date %r" % (line, rec.get("date"))) from None
    return rec


def load_transactions(path: str | PathLike[str]) -> list[Transaction]:
    with open(path, newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return []
    header = [h.strip().lower() for h in rows[0]]
    return [_parse_row(header, row, line) for line, row in enumerate(rows[1:], start=2)
            if row and not (len(row) == 1 and row[0].strip() == "")]


def export_csv(transactions: list[Transaction], path: str | PathLike[str], month: str | None = None) -> int:
    count = 0
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "date", "customer", "type", "category", "amount_usd"])
        for t in _by_date(transactions):
            if month is not None and not _in_month(t, month):
                continue
            amount = to_usd(t)
            if t["type"] in ("refund", "chargeback"):
                amount = -amount
            writer.writerow([t.get("id", ""), t["date"], t.get("customer", ""), t["type"],
                             t.get("category") or UNCATEGORIZED, "%.2f" % round(amount, 2)])
            count += 1
    return count


# ----------------------------------------------------------------------------- category summary


def summarize_by_category(transactions: list[Transaction], month: str) -> dict[str, dict[str, Any]]:
    _validate_month(month)
    out: dict[str, dict[str, Any]] = {}
    for t in transactions:
        if not _in_month(t, month):
            continue
        entry = out.setdefault(t.get("category") or UNCATEGORIZED, {"count": 0, "gross": 0.0, "refunds": 0.0, "net": 0.0})
        amount = to_usd(t)
        if t["type"] == "sale":
            entry["count"] += 1
            entry["gross"] += amount
            entry["net"] += amount
        elif t["type"] == "refund":
            entry["refunds"] += amount
            entry["net"] -= amount
        elif t["type"] == "chargeback":
            entry["refunds"] += amount
            entry["net"] -= amount + CHARGEBACK_FEE
    for entry in out.values():
        for key in ("gross", "refunds", "net"):
            entry[key] = round(entry[key], 2)
    return out


def generate_category_report(transactions: list[Transaction], month: str, fmt: str = "text") -> str:
    if fmt not in ("text", "markdown"):
        raise ValueError("bad format")
    summary = summarize_by_category(transactions, month)
    cats = sorted(summary, key=lambda k: (-summary[k]["net"], k))
    total_gross = total_net = 0.0
    for k in cats:
        total_gross += summary[k]["gross"]
        total_net += summary[k]["net"]

    def share(k: str) -> float:
        return summary[k]["gross"] / total_gross * 100 if total_gross > 0 else 0.0

    def amounts(k: str) -> tuple[str, str]:
        return "{:,.2f}".format(summary[k]["gross"]), "{:,.2f}".format(summary[k]["net"])

    if fmt == "text":
        lines = ["CATEGORIES " + month + " (USD)", "=" * 50, "%-16s %6s %12s %12s" % ("Category", "Sales", "Gross", "Net")]
        lines += ["%-16s %6d %12s %12s  %5.1f%%" % (k, summary[k]["count"], *amounts(k), share(k)) for k in cats]
        lines += ["-" * 50, "%-16s %6s %12s %12s" % ("TOTAL", "", _money(total_gross), _money(total_net))]
    else:
        lines = ["# Categories " + month + " (USD)", "", "| Category | Sales | Gross | Net | Share |", "|---|---:|---:|---:|---:|"]
        lines += ["| %s | %d | %s | %s | %.1f%% |" % (k, summary[k]["count"], *amounts(k), share(k)) for k in cats]
        lines.append("| **TOTAL** | | **%s** | **%s** | |" % (_money(total_gross), _money(total_net)))
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------- monthly report


@dataclass
class MonthlyTotals:
    gross: float = 0.0
    refunds: float = 0.0
    fees: float = 0.0
    chargebacks: float = 0.0
    chargeback_fees: float = 0.0
    tax: float = 0.0
    n_sales: int = 0
    n_refunds: int = 0
    per_customer: dict[str, float] = field(default_factory=dict)

    @property
    def net(self) -> float:
        return self.gross - self.refunds - self.fees - self.chargebacks - self.chargeback_fees - self.tax

    def add(self, t: Transaction) -> None:
        amount = to_usd(t)
        customer = t.get("customer", "")
        self.per_customer.setdefault(customer, 0.0)
        kind = t["type"]
        if kind == "sale":
            self.gross += amount
            self.n_sales += 1
            self.fees += processing_fee(amount)
            if t["currency"] in SALES_TAX_RATES:
                self.tax += amount * SALES_TAX_RATES[t["currency"]]
            self.per_customer[customer] += amount
        elif kind == "refund":
            self.refunds += amount
            self.n_refunds += 1
            if t["currency"] in SALES_TAX_RATES:
                self.tax -= amount * SALES_TAX_RATES[t["currency"]]
            self.per_customer[customer] -= amount
        elif kind == "fee":
            self.fees += amount
        elif kind == "chargeback":
            self.chargebacks += amount
            self.chargeback_fees += CHARGEBACK_FEE
            self.per_customer[customer] -= amount

    def lines(self, divisor: float) -> list[tuple[str, str, float]]:
        """(label, csv key, amount in report currency) for the summary table."""
        def conv(v: float) -> float:
            return v / divisor if divisor != 1.0 else v

        return [("Gross sales", "gross_sales", conv(self.gross)), ("Refunds", "refunds", conv(self.refunds)),
                ("Processing fees", "processing_fees", conv(self.fees)),
                ("Chargebacks", "chargebacks", conv(self.chargebacks)),
                ("Chargeback fees", "chargeback_fees", conv(self.chargeback_fees)), ("Tax", "tax", conv(self.tax)),
                ("NET", "net", conv(self.net))]


def _refund_rate_note(totals: MonthlyTotals) -> tuple[bool, float] | None:
    if totals.n_sales == 0 or totals.n_refunds == 0:
        return None
    rate = totals.n_refunds / totals.n_sales * 100
    return rate > REFUND_RATE_WARNING_PCT, rate


def _top_customers(totals: MonthlyTotals, divisor: float) -> list[tuple[str, float]]:
    values = {c: (v / divisor if divisor != 1.0 else v) for c, v in totals.per_customer.items()}
    ranked = sorted(values.items(), key=lambda kv: (-round(kv[1], 2), kv[0]))[:TOP_CUSTOMERS]
    return [(c or "(unknown)", v) for c, v in ranked]


def _monthly_text(month: str, currency: str, totals: MonthlyTotals, divisor: float) -> list[str]:
    rows = totals.lines(divisor)
    lines = ["MONTHLY REPORT " + month + " (" + currency + ")", "=" * 40]
    lines += ["%-22s %15s" % (label, _money(v)) for label, _, v in rows[:-1]]
    lines += ["-" * 40, "%-22s %15s" % ("NET", _money(rows[-1][2])), "",
              "Sales: %d  Refunds: %d" % (totals.n_sales, totals.n_refunds)]
    if totals.n_sales > 0:
        lines.append("Average sale: " + _money(rows[0][2] / totals.n_sales))
    note = _refund_rate_note(totals)
    if note:
        warn, rate = note
        lines.append(("WARNING: refund rate %.1f%% above 10%%" if warn else "Refund rate: %.1f%%") % rate)
    lines += ["", "Top customers:"]
    lines += ["  %d. %-12s %12s" % (i, c, _money(v)) for i, (c, v) in enumerate(_top_customers(totals, divisor), 1)]
    return lines


def _monthly_markdown(month: str, currency: str, totals: MonthlyTotals, divisor: float) -> list[str]:
    rows = totals.lines(divisor)
    lines = ["# Monthly report " + month + " (" + currency + ")", "", "| Item | Amount |", "|---|---:|"]
    lines += ["| %s | %s |" % (label, _money(v)) for label, _, v in rows[:-1]]
    lines += ["| **NET** | **" + _money(rows[-1][2]) + "** |", "",
              "Sales: %d, refunds: %d" % (totals.n_sales, totals.n_refunds)]
    if totals.n_sales > 0:
        lines += ["", "Average sale: " + _money(rows[0][2] / totals.n_sales)]
    note = _refund_rate_note(totals)
    if note:
        warn, rate = note
        lines += ["", ("> **Warning:** refund rate %.1f%% above 10%%" if warn else "Refund rate: %.1f%%") % rate]
    lines += ["", "## Top customers", ""]
    lines += ["%d. %s — %s" % (i, c, _money(v)) for i, (c, v) in enumerate(_top_customers(totals, divisor), 1)]
    return lines


def _monthly_csv(month: str, currency: str, totals: MonthlyTotals, divisor: float) -> list[str]:
    return ["item,amount"] + ["%s,%.2f" % (key, round(v, 2)) for _, key, v in totals.lines(divisor)]


_MONTHLY_RENDERERS: dict[str, Callable[[str, str, MonthlyTotals, float], list[str]]] = {
    "text": _monthly_text, "markdown": _monthly_markdown, "csv": _monthly_csv,
}


def generate_monthly_report(transactions: list[Transaction], month: str, currency: str = "USD", fmt: str = "text") -> str:
    _validate_month(month)
    if fmt not in _MONTHLY_RENDERERS:
        raise ValueError("bad format")
    totals = MonthlyTotals()
    for t in transactions:
        if _in_month(t, month):
            totals.add(t)
    divisor = 1.0 if currency == "USD" else _fx_rate(currency)
    return "\n".join(_MONTHLY_RENDERERS[fmt](month, currency, totals, divisor)) + "\n"


# ----------------------------------------------------------------------------- customer statement

_STATEMENT_LABELS = {"sale": ("Purchase", 1), "refund": ("Refund", -1), "chargeback": ("Chargeback", -1)}


def _statement_rows(transactions: list[Transaction], customer_id: str, start: datetime.date,
                    end: datetime.date) -> tuple[list[tuple[str, str, str, float, float]], float]:
    rows = []
    balance = 0.0
    for t in _by_date(transactions):
        if t.get("customer", "") != customer_id or not (start <= datetime.date.fromisoformat(t["date"]) <= end):
            continue
        amount = to_usd(t)
        if t["type"] not in _STATEMENT_LABELS:
            continue
        label, sign = _STATEMENT_LABELS[t["type"]]
        if sign > 0:
            balance += amount
            rows.append((t["date"], t.get("id", ""), label, amount, balance))
        else:
            balance -= amount
            rows.append((t["date"], t.get("id", ""), label, -amount, balance))
    return rows, balance


def generate_customer_statement(transactions: list[Transaction], customer_id: str, start: str, end: str,
                                fmt: str = "text") -> str:
    if fmt not in ("text", "csv"):
        raise ValueError("bad format")
    s, e = datetime.date.fromisoformat(start), datetime.date.fromisoformat(end)
    if e < s:
        raise ValueError("end before start")
    rows, balance = _statement_rows(transactions, customer_id, s, e)
    if fmt == "csv":
        lines = ["date,id,description,amount,balance"]
        lines += ["%s,%s,%s,%.2f,%.2f" % (d, i, label, round(a, 2), round(b, 2)) for d, i, label, a, b in rows]
        return "\n".join(lines) + "\n"
    lines = ["STATEMENT for " + customer_id + " " + start + " to " + end + " (USD)", "=" * 60]
    if not rows:
        lines.append("No activity.")
    lines += ["%s  %-10s %-11s %12s %12s" % (d, i, label, _money(a), _money(b)) for d, i, label, a, b in rows]
    lines += ["-" * 60, "Closing balance: " + _money(balance)]
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------- payouts


@dataclass
class _PayoutWindow:
    start: datetime.date
    end: datetime.date  # exclusive
    gross: float = 0.0
    reserve: float = 0.0
    fees: float = 0.0

    def add(self, t: Transaction, amount: float) -> None:
        kind = t["type"]
        if kind == "sale":
            if t.get("category") == RESERVE_CATEGORY:
                self.gross += amount * (1 - RESERVE_SHARE)
                self.reserve += amount * RESERVE_SHARE
            else:
                self.gross += amount
            self.fees += processing_fee(amount)
        elif kind == "refund":
            self.gross -= amount
        elif kind == "fee":
            self.fees += amount
        elif kind == "chargeback":
            self.gross -= amount
            self.fees += CHARGEBACK_FEE


def _payout_windows(month: str) -> list[_PayoutWindow]:
    year, mon = int(month[:4]), int(month[5:])
    first = datetime.date(year, mon, 1)
    nxt = datetime.date(year + 1, 1, 1) if mon == 12 else datetime.date(year, mon + 1, 1)
    windows, day = [], first
    while day < nxt:
        end = min(day + datetime.timedelta(days=PAYOUT_WINDOW_DAYS), nxt)
        windows.append(_PayoutWindow(day, end))
        day = end
    return windows


def generate_payout_schedule(transactions: list[Transaction], month: str) -> list[dict[str, Any]]:
    """Payouts every 7 days from the 1st. Electronics sales keep 10% in reserve (released after
    90 days, not shown). Fees are deducted from the payout of the window they belong to."""
    _validate_month(month)
    windows = _payout_windows(month)
    for t in transactions:
        if not _in_month(t, month):
            continue
        day = datetime.date.fromisoformat(t["date"])
        amount = to_usd(t)
        window = next((w for w in windows if w.start <= day < w.end), None)
        if window is not None:
            window.add(t, amount)
    return [{"start": w.start.isoformat(), "end": (w.end - datetime.timedelta(days=1)).isoformat(),
             "payout": round(max(w.gross - w.fees, 0.0), 2), "reserve": round(w.reserve, 2), "fees": round(w.fees, 2)}
            for w in windows]
