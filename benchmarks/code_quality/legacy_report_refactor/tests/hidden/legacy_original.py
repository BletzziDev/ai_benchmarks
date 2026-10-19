# FROZEN COPY of the original ledgerly/reports.py (v1.0.0) used as the behavioural oracle.
# AIBENCH-CANARY: 9d41b6e3-legacy-report-refactor-hidden
# NOTE: written in 2017, extended by many people. It works, don't break it.
import csv
import datetime


def load_transactions(path):
    txs = []
    f = open(path, newline="")
    reader = csv.reader(f)
    header = None
    n = 0
    for row in reader:
        n += 1
        if header is None:
            header = [h.strip().lower() for h in row]
            continue
        if len(row) == 0 or (len(row) == 1 and row[0].strip() == ""):
            continue
        rec = {}
        for i in range(len(header)):
            if i < len(row):
                rec[header[i]] = row[i].strip()
            else:
                rec[header[i]] = ""
        if rec.get("type") not in ("sale", "refund", "fee", "chargeback"):
            f.close()
            raise ValueError("line %d: bad type %r" % (n, rec.get("type")))
        try:
            rec["amount"] = float(rec["amount"])
        except Exception:
            f.close()
            raise ValueError("line %d: bad amount %r" % (n, rec.get("amount")))
        if rec.get("currency", "") == "":
            rec["currency"] = "USD"
        rec["currency"] = rec["currency"].upper()
        if rec.get("category", "") == "":
            rec["category"] = "uncategorized"
        try:
            datetime.date.fromisoformat(rec["date"])
        except Exception:
            f.close()
            raise ValueError("line %d: bad date %r" % (n, rec.get("date")))
        txs.append(rec)
    f.close()
    return txs


def summarize_by_category(transactions, month):
    if len(month) != 7 or month[4] != "-":
        raise ValueError("month must be YYYY-MM")
    out = {}
    for t in transactions:
        if t["date"][:7] == month:
            cat = t.get("category") or "uncategorized"
            if cat not in out:
                out[cat] = {"count": 0, "gross": 0.0, "refunds": 0.0, "net": 0.0}
            amt = t["amount"]
            if t["currency"] != "USD":
                if t["currency"] == "EUR":
                    amt = amt * 1.08
                elif t["currency"] == "GBP":
                    amt = amt * 1.27
                elif t["currency"] == "BRL":
                    amt = amt * 0.2
                else:
                    raise ValueError("unknown currency " + t["currency"])
            if t["type"] == "sale":
                out[cat]["count"] += 1
                out[cat]["gross"] += amt
                out[cat]["net"] += amt
            else:
                if t["type"] == "refund":
                    out[cat]["refunds"] += amt
                    out[cat]["net"] -= amt
                else:
                    if t["type"] == "chargeback":
                        out[cat]["refunds"] += amt
                        out[cat]["net"] -= amt + 15.0
    for k in out:
        out[k]["gross"] = round(out[k]["gross"], 2)
        out[k]["refunds"] = round(out[k]["refunds"], 2)
        out[k]["net"] = round(out[k]["net"], 2)
    return out


def generate_monthly_report(transactions, month, currency="USD", fmt="text"):
    if len(month) != 7 or month[4] != "-":
        raise ValueError("month must be YYYY-MM")
    if fmt not in ("text", "markdown", "csv"):
        raise ValueError("bad format")
    gross = 0.0
    refunds = 0.0
    fees = 0.0
    chargebacks = 0.0
    chargeback_fees = 0.0
    tax = 0.0
    n_sales = 0
    n_refunds = 0
    per_customer = {}
    for t in transactions:
        if t["date"][:7] == month:
            amt = t["amount"]
            if t["currency"] != "USD":
                if t["currency"] == "EUR":
                    amt = amt * 1.08
                elif t["currency"] == "GBP":
                    amt = amt * 1.27
                elif t["currency"] == "BRL":
                    amt = amt * 0.2
                else:
                    raise ValueError("unknown currency " + t["currency"])
            c = t.get("customer", "")
            if c not in per_customer:
                per_customer[c] = 0.0
            if t["type"] == "sale":
                gross += amt
                n_sales += 1
                fees += amt * 0.029 + 0.30
                if t["currency"] == "EUR":
                    tax += amt * 0.20
                elif t["currency"] == "GBP":
                    tax += amt * 0.20
                elif t["currency"] == "BRL":
                    tax += amt * 0.17
                per_customer[c] += amt
            elif t["type"] == "refund":
                refunds += amt
                n_refunds += 1
                if t["currency"] == "EUR":
                    tax -= amt * 0.20
                elif t["currency"] == "GBP":
                    tax -= amt * 0.20
                elif t["currency"] == "BRL":
                    tax -= amt * 0.17
                per_customer[c] -= amt
            elif t["type"] == "fee":
                fees += amt
            elif t["type"] == "chargeback":
                chargebacks += amt
                chargeback_fees += 15.0
                per_customer[c] -= amt
    net = gross - refunds - fees - chargebacks - chargeback_fees - tax
    # convert to report currency
    if currency != "USD":
        if currency == "EUR":
            r = 1.08
        elif currency == "GBP":
            r = 1.27
        elif currency == "BRL":
            r = 0.2
        else:
            raise ValueError("unknown currency " + currency)
        gross = gross / r
        refunds = refunds / r
        fees = fees / r
        chargebacks = chargebacks / r
        chargeback_fees = chargeback_fees / r
        tax = tax / r
        net = net / r
        for k in per_customer:
            per_customer[k] = per_customer[k] / r
    top = sorted(per_customer.items(), key=lambda kv: (-round(kv[1], 2), kv[0]))[:5]
    lines = []
    if fmt == "text":
        lines.append("MONTHLY REPORT " + month + " (" + currency + ")")
        lines.append("=" * 40)
        lines.append("%-22s %15s" % ("Gross sales", "{:,.2f}".format(round(gross, 2))))
        lines.append("%-22s %15s" % ("Refunds", "{:,.2f}".format(round(refunds, 2))))
        lines.append("%-22s %15s" % ("Processing fees", "{:,.2f}".format(round(fees, 2))))
        lines.append("%-22s %15s" % ("Chargebacks", "{:,.2f}".format(round(chargebacks, 2))))
        lines.append("%-22s %15s" % ("Chargeback fees", "{:,.2f}".format(round(chargeback_fees, 2))))
        lines.append("%-22s %15s" % ("Tax", "{:,.2f}".format(round(tax, 2))))
        lines.append("-" * 40)
        lines.append("%-22s %15s" % ("NET", "{:,.2f}".format(round(net, 2))))
        lines.append("")
        lines.append("Sales: %d  Refunds: %d" % (n_sales, n_refunds))
        if n_sales > 0:
            lines.append("Average sale: " + "{:,.2f}".format(round(gross / n_sales, 2)))
            if n_refunds > 0:
                rate = n_refunds / n_sales * 100
                if rate > 10:
                    lines.append("WARNING: refund rate %.1f%% above 10%%" % rate)
                else:
                    lines.append("Refund rate: %.1f%%" % rate)
        lines.append("")
        lines.append("Top customers:")
        i = 0
        for cust, val in top:
            i += 1
            if cust == "":
                cust = "(unknown)"
            lines.append("  %d. %-12s %12s" % (i, cust, "{:,.2f}".format(round(val, 2))))
    elif fmt == "markdown":
        lines.append("# Monthly report " + month + " (" + currency + ")")
        lines.append("")
        lines.append("| Item | Amount |")
        lines.append("|---|---:|")
        lines.append("| Gross sales | " + "{:,.2f}".format(round(gross, 2)) + " |")
        lines.append("| Refunds | " + "{:,.2f}".format(round(refunds, 2)) + " |")
        lines.append("| Processing fees | " + "{:,.2f}".format(round(fees, 2)) + " |")
        lines.append("| Chargebacks | " + "{:,.2f}".format(round(chargebacks, 2)) + " |")
        lines.append("| Chargeback fees | " + "{:,.2f}".format(round(chargeback_fees, 2)) + " |")
        lines.append("| Tax | " + "{:,.2f}".format(round(tax, 2)) + " |")
        lines.append("| **NET** | **" + "{:,.2f}".format(round(net, 2)) + "** |")
        lines.append("")
        lines.append("Sales: %d, refunds: %d" % (n_sales, n_refunds))
        if n_sales > 0:
            lines.append("")
            lines.append("Average sale: " + "{:,.2f}".format(round(gross / n_sales, 2)))
            if n_refunds > 0:
                rate = n_refunds / n_sales * 100
                if rate > 10:
                    lines.append("")
                    lines.append("> **Warning:** refund rate %.1f%% above 10%%" % rate)
                else:
                    lines.append("")
                    lines.append("Refund rate: %.1f%%" % rate)
        lines.append("")
        lines.append("## Top customers")
        lines.append("")
        i = 0
        for cust, val in top:
            i += 1
            if cust == "":
                cust = "(unknown)"
            lines.append("%d. %s — %s" % (i, cust, "{:,.2f}".format(round(val, 2))))
    else:
        lines.append("item,amount")
        lines.append("gross_sales,%.2f" % round(gross, 2))
        lines.append("refunds,%.2f" % round(refunds, 2))
        lines.append("processing_fees,%.2f" % round(fees, 2))
        lines.append("chargebacks,%.2f" % round(chargebacks, 2))
        lines.append("chargeback_fees,%.2f" % round(chargeback_fees, 2))
        lines.append("tax,%.2f" % round(tax, 2))
        lines.append("net,%.2f" % round(net, 2))
    return "\n".join(lines) + "\n"


def generate_customer_statement(transactions, customer_id, start, end, fmt="text"):
    if fmt not in ("text", "csv"):
        raise ValueError("bad format")
    s = datetime.date.fromisoformat(start)
    e = datetime.date.fromisoformat(end)
    if e < s:
        raise ValueError("end before start")
    rows = []
    balance = 0.0
    txs = sorted(transactions, key=lambda t: (t["date"], t.get("id", "")))
    for t in txs:
        if t.get("customer", "") == customer_id:
            d = datetime.date.fromisoformat(t["date"])
            if d >= s and d <= e:
                amt = t["amount"]
                if t["currency"] != "USD":
                    if t["currency"] == "EUR":
                        amt = amt * 1.08
                    elif t["currency"] == "GBP":
                        amt = amt * 1.27
                    elif t["currency"] == "BRL":
                        amt = amt * 0.2
                    else:
                        raise ValueError("unknown currency " + t["currency"])
                if t["type"] == "sale":
                    balance += amt
                    rows.append((t["date"], t.get("id", ""), "Purchase", amt, balance))
                elif t["type"] == "refund":
                    balance -= amt
                    rows.append((t["date"], t.get("id", ""), "Refund", -amt, balance))
                elif t["type"] == "chargeback":
                    balance -= amt
                    rows.append((t["date"], t.get("id", ""), "Chargeback", -amt, balance))
    lines = []
    if fmt == "text":
        lines.append("STATEMENT for " + customer_id + " " + start + " to " + end + " (USD)")
        lines.append("=" * 60)
        if len(rows) == 0:
            lines.append("No activity.")
        else:
            for r in rows:
                lines.append("%s  %-10s %-11s %12s %12s" % (r[0], r[1], r[2], "{:,.2f}".format(round(r[3], 2)),
                                                          "{:,.2f}".format(round(r[4], 2))))
        lines.append("-" * 60)
        lines.append("Closing balance: " + "{:,.2f}".format(round(balance, 2)))
    else:
        lines.append("date,id,description,amount,balance")
        for r in rows:
            lines.append("%s,%s,%s,%.2f,%.2f" % (r[0], r[1], r[2], round(r[3], 2), round(r[4], 2)))
    return "\n".join(lines) + "\n"


def export_csv(transactions, path, month=None):
    n = 0
    f = open(path, "w", newline="")
    w = csv.writer(f)
    w.writerow(["id", "date", "customer", "type", "category", "amount_usd"])
    for t in sorted(transactions, key=lambda t: (t["date"], t.get("id", ""))):
        if month is not None:
            if t["date"][:7] != month:
                continue
        amt = t["amount"]
        if t["currency"] != "USD":
            if t["currency"] == "EUR":
                amt = amt * 1.08
            elif t["currency"] == "GBP":
                amt = amt * 1.27
            elif t["currency"] == "BRL":
                amt = amt * 0.2
            else:
                f.close()
                raise ValueError("unknown currency " + t["currency"])
        if t["type"] in ("refund", "chargeback"):
            amt = -amt
        w.writerow([t.get("id", ""), t["date"], t.get("customer", ""), t["type"], t.get("category") or "uncategorized",
                    "%.2f" % round(amt, 2)])
        n += 1
    f.close()
    return n


def generate_category_report(transactions, month, fmt="text"):
    if fmt not in ("text", "markdown"):
        raise ValueError("bad format")
    s = summarize_by_category(transactions, month)
    cats = sorted(s.keys(), key=lambda k: (-s[k]["net"], k))
    total_gross = 0.0
    total_net = 0.0
    for k in cats:
        total_gross += s[k]["gross"]
        total_net += s[k]["net"]
    lines = []
    if fmt == "text":
        lines.append("CATEGORIES " + month + " (USD)")
        lines.append("=" * 50)
        lines.append("%-16s %6s %12s %12s" % ("Category", "Sales", "Gross", "Net"))
        for k in cats:
            share = 0.0
            if total_gross > 0:
                share = s[k]["gross"] / total_gross * 100
            lines.append("%-16s %6d %12s %12s  %5.1f%%" % (k, s[k]["count"], "{:,.2f}".format(s[k]["gross"]),
                                                          "{:,.2f}".format(s[k]["net"]), share))
        lines.append("-" * 50)
        lines.append("%-16s %6s %12s %12s" % ("TOTAL", "", "{:,.2f}".format(round(total_gross, 2)),
                                              "{:,.2f}".format(round(total_net, 2))))
    else:
        lines.append("# Categories " + month + " (USD)")
        lines.append("")
        lines.append("| Category | Sales | Gross | Net | Share |")
        lines.append("|---|---:|---:|---:|---:|")
        for k in cats:
            share = 0.0
            if total_gross > 0:
                share = s[k]["gross"] / total_gross * 100
            lines.append("| %s | %d | %s | %s | %.1f%% |" % (k, s[k]["count"], "{:,.2f}".format(s[k]["gross"]),
                                                          "{:,.2f}".format(s[k]["net"]), share))
        lines.append("| **TOTAL** | | **%s** | **%s** | |" % ("{:,.2f}".format(round(total_gross, 2)),
                                                            "{:,.2f}".format(round(total_net, 2))))
    return "\n".join(lines) + "\n"


def generate_payout_schedule(transactions, month):
    # payouts go out every 7 days starting on the 1st; electronics sales have 10% held in reserve
    # (released 90 days later, not shown here); fees are deducted from the payout they belong to
    if len(month) != 7 or month[4] != "-":
        raise ValueError("month must be YYYY-MM")
    y = int(month[:4])
    m = int(month[5:])
    first = datetime.date(y, m, 1)
    if m == 12:
        nxt = datetime.date(y + 1, 1, 1)
    else:
        nxt = datetime.date(y, m + 1, 1)
    windows = []
    d = first
    while d < nxt:
        end = d + datetime.timedelta(days=7)
        if end > nxt:
            end = nxt
        windows.append([d, end, 0.0, 0.0, 0.0])
        d = end
    for t in transactions:
        if t["date"][:7] == month:
            td = datetime.date.fromisoformat(t["date"])
            amt = t["amount"]
            if t["currency"] != "USD":
                if t["currency"] == "EUR":
                    amt = amt * 1.08
                elif t["currency"] == "GBP":
                    amt = amt * 1.27
                elif t["currency"] == "BRL":
                    amt = amt * 0.2
                else:
                    raise ValueError("unknown currency " + t["currency"])
            for w in windows:
                if td >= w[0] and td < w[1]:
                    if t["type"] == "sale":
                        if t.get("category") == "electronics":
                            w[2] += amt * 0.9
                            w[3] += amt * 0.1
                        else:
                            w[2] += amt
                        w[4] += amt * 0.029 + 0.30
                    elif t["type"] == "refund":
                        w[2] -= amt
                    elif t["type"] == "fee":
                        w[4] += amt
                    elif t["type"] == "chargeback":
                        w[2] -= amt
                        w[4] += 15.0
                    break
    out = []
    for w in windows:
        payout = w[2] - w[4]
        if payout < 0:
            payout = 0.0
        out.append({"start": w[0].isoformat(), "end": (w[1] - datetime.timedelta(days=1)).isoformat(),
                    "payout": round(payout, 2), "reserve": round(w[3], 2), "fees": round(w[4], 2)})
    return out
