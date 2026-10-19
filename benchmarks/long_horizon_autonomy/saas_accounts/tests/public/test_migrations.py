from acctsvc import db


def test_migrate_is_idempotent():
    c = db.connect()
    first = db.migrate(c)
    assert first[:3] == ["001_init", "002_audit_log", "003_customer_notes"]
    assert db.migrate(c) == []


def test_schema_has_core_tables(conn):
    names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"users", "orgs", "memberships", "subscriptions", "invoices", "invoice_lines", "audit_log"} <= names
