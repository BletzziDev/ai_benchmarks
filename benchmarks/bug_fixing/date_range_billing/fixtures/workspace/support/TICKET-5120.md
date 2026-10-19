# TICKET-5120 — "Upgrade charge doesn't match your pricing page"

**Reported by:** Billing support, 2025-04-02. Priority: high (refund requests piling up).

Several customers who changed plan in late March were charged amounts that don't match the
"remaining days × daily price" explanation on our pricing page. Monthly prices: Starter 29.00,
Pro 99.00. Our pricing page says proration is by calendar day in the customer's own timezone.

| Account | Timezone | Change (UTC) | Lines on invoice (cents) | What the customer computed |
|---|---|---|---|---|
| acct_8812 | America/New_York | 2025-03-20 15:00 | credit -1160, charge 3960 | 12 of 31 days: credit -1123, charge 3832 |
| acct_2290 | Europe/Berlin | 2025-03-25 09:00 | credit -580, charge 1980 | 7 of 31 days: credit -655, charge 2235 |
| acct_0457 | Asia/Tokyo | 2025-03-20 01:00 | credit -1123, charge 3832 | matches |

Support also noticed that a Sydney customer's October invoice "looks a day short". Nobody has
complained about February, June or November invoices.

Note from the ledger team: rounding must stay banker's rounding (half-even). Do not change it.
