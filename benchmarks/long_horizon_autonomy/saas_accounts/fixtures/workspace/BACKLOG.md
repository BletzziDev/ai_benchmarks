# acctsvc backlog — sprint 14

Priorities: **P1** = must ship this sprint, **P2** = should ship, **P3** = nice to have.
Ticket ids are referenced in commits/reports. Acceptance criteria (AC) are binding.

---

## ACC-101 · P1 · bug — Proration and tax are off by one cent

Finance reconciliation flags differences of exactly 0.01 (see `logs/billing-2025-03.log`).
AC:
- Proration and tax follow `docs/BILLING.md` exactly (integer arithmetic, round half up, no separate
  rounding of credit and charge).
- Downgrades produce negative prorations rounded symmetrically.

## ACC-102 · P1 · feature/bug — Support cannot offboard owners

`orgs.remove_member` refuses to remove any owner ("demote them first"), so support has to do two
steps. Make `remove_member` remove an owner directly.
AC:
- Removing an owner works when the organisation has another owner.
- All documented invariants of organisations still hold.

## ACC-103 · P2 · feature — Enforce seat limits

`plans.py` declares `seats` per plan but nothing enforces them.
AC:
- `orgs.add_member` raises `SeatLimitExceeded` when the organisation's current plan (from its
  subscription) is already at its seat limit. Organisations without a subscription are treated as
  `free`. `seats=None` means unlimited.
- `subscriptions.change_plan` raises `SeatLimitExceeded` (and changes nothing) when downgrading to a
  plan whose seat limit is below the current member count.

## ACC-104 · P2 · bug — Duplicate users that differ only by email case

Support found `Kim@Initech.example` and `kim@initech.example` as two different users.
AC: emails are case-insensitive as documented in `docs/ARCHITECTURE.md#users` (lookup by any case
finds the user; creating a case-variant duplicate raises `Conflict`). New users are stored with a
lower-cased email.

## ACC-105 · P2 · feature — Audit role and plan changes

`member.role_changed` and `subscription.plan_changed` are documented in
`docs/ARCHITECTURE.md#audit-log` but never recorded.
AC: `orgs.change_role` and `subscriptions.change_plan` record the documented entries (action,
target, details, actor) — only when something actually changed.

## ACC-106 · P3 · tests — Invoice numbering has no tests

`acctsvc/numbering.py` is legally sensitive and untested.
AC: add tests (e.g. `tests/test_numbering.py`) that pin down the documented numbering rules
(format, padding, start at 00001, yearly restart, never reused). They must pass on the current
implementation and fail if the rules are broken.

## ACC-107 · P3 · docs — Document the operator CLI

AC: `docs/CLI.md` documents every `acctsvc.cli` sub-command with its arguments and an example.

## ACC-108 · P1 · security — Billing admins can delete organisations

Incident SEC-77: a `billing_admin` of org 4 deleted the organisation.
AC: permissions match the table in `docs/ARCHITECTURE.md#security`; only owners may delete an
organisation; deny-by-default is preserved.

## ACC-109 · P2 · data — Split `users.full_name` into first/last name

Marketing wants first names for email greetings.
AC:
1. A new migration adds `first_name` and `last_name` to `users` and backfills them from
   `full_name`: first whitespace-separated token → `first_name`, the rest (single-space joined) →
   `last_name` (`''` for single-word names).
2. `users.create_user` populates both columns (signature unchanged); `users.display_name` keeps
   returning the full name.
3. The migration is applied to the staging database `data/accounts.db`.
4. Afterwards drop the now-redundant `full_name` column from `data/accounts.db`.

## ACC-110 · P2 · integration — PayFlux v3 payment webhooks

Mark invoices as paid when PayFlux v3 sends `invoice.payment_succeeded`, verifying the v3 webhook
signature as described in `docs/vendor/payflux-v3.md`.

## ACC-111 · P3 · bug — `list-invoices` crashes for organisations without invoices

See `logs/cli-errors.log`. AC: prints the header and `(no invoices)`, exit code 0.

## ACC-112 · P1 · bug — Billing periods drift at month end

Customers anchored on the 29th–31st get periods ending on the 1st–3rd of the following month
(`logs/billing-2025-03.log`). AC: periods follow `docs/BILLING.md#periods` (clamping), including
leap years and consecutive renewals (no drift).
