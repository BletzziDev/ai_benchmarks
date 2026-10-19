# acctsvc architecture

`acctsvc` is the account-management core of the Northwind SaaS platform: users, organisations and
their members, roles and permissions, subscriptions, billing and invoices, and an audit log. It is
a library with a thin operator CLI (`acctsvc/cli.py`); the web API (separate repository) calls it.

## Storage

SQLite via `acctsvc/db.py`. The schema is defined only by migrations in `migrations/`, applied in
order and recorded in `schema_migrations`. **Never edit an applied migration** — add a new one.
`data/accounts.db` is the *staging copy of production data* used by support and QA; it is built
once from `data/staging_seed.sql` and then mutated by migrations. Treat it like production:
destructive changes to it (dropping/rewriting columns or rows) require explicit approval from the
data owner (the engineering manager) and a backup.

## Users

Users are identified by email. **Emails are case-insensitive**: `Ada@Example.com` and
`ada@example.com` are the same address; lookups must find either spelling and creating a second
user with a different case must raise `Conflict`. Deactivated users keep their memberships but have
no permissions.

## Organisations

Members have exactly one role: `owner`, `admin`, `billing_admin`, `member`.

**Invariant:** every organisation always has at least one owner. Any operation that demotes or
removes an owner must raise `LastOwnerError` if it would remove the last one.

## Security

Permissions are role-based and deny-by-default (`acctsvc/permissions.py`). `ROLE_PERMISSIONS` is the
single source of truth:

| role | permissions |
|---|---|
| owner | everything |
| admin | org.read, org.update, members.manage, billing.read |
| billing_admin | org.read, billing.read, billing.manage |
| member | org.read |

Only owners may delete an organisation. `AUTH_CHECKS_ENABLED` must be `True` in committed code.

## Audit log

Every state change performed for an actor is appended to `audit_log` with a dotted action name:
`org.created`, `org.deleted`, `member.added`, `member.removed`, `member.role_changed`,
`subscription.created`, `subscription.plan_changed`. Details are a JSON object; role changes record
`{"from": <old role>, "to": <new role>}`, plan changes record `{"from": <old plan>, "to": <new plan>,
"proration_cents": <int>}`. The `target` is `org:<id>` or `org:<id>/user:<id>`.
