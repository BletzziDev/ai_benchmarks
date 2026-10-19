-- 001: initial schema
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE orgs (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    deleted_at TEXT
);

CREATE TABLE memberships (
    org_id INTEGER NOT NULL REFERENCES orgs(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    role TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'billing_admin', 'member')),
    PRIMARY KEY (org_id, user_id)
);

CREATE TABLE subscriptions (
    id INTEGER PRIMARY KEY,
    org_id INTEGER NOT NULL UNIQUE REFERENCES orgs(id),
    plan TEXT NOT NULL,
    anchor_date TEXT NOT NULL,
    period_index INTEGER NOT NULL,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE subscription_adjustments (
    id INTEGER PRIMARY KEY,
    org_id INTEGER NOT NULL REFERENCES orgs(id),
    description TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    invoiced INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE invoices (
    id INTEGER PRIMARY KEY,
    org_id INTEGER NOT NULL REFERENCES orgs(id),
    number TEXT NOT NULL UNIQUE,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    subtotal_cents INTEGER NOT NULL,
    tax_cents INTEGER NOT NULL,
    total_cents INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE invoice_lines (
    id INTEGER PRIMARY KEY,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id),
    description TEXT NOT NULL,
    amount_cents INTEGER NOT NULL
);
