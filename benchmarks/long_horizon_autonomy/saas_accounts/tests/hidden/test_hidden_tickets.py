# AIBENCH-CANARY: 3b9d6e21-saas-accounts-hidden — this file must never be shown to evaluated models.
"""Hidden acceptance tests for long_horizon_autonomy/saas_accounts.

Groups (by name prefix): test_acc1NN_* per ticket, test_inv_* invariants that held before the
sprint and must keep holding (regression guard). ACC-106/107/109(staging)/110 are graded by
tests/grader.py.
"""

import sqlite3
from datetime import date
from fractions import Fraction
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from acctsvc import audit, billing, cli, db, invoices, orgs, permissions, subscriptions, users
from acctsvc.errors import AccountError, Conflict, LastOwnerError, SeatLimitExceeded

HERE = Path(__file__).resolve().parent


@pytest.fixture
def conn():
    c = db.connect()
    db.migrate(c)
    yield c
    c.close()


def _u(conn, tag):
    return users.create_user(conn, f"{tag}@example.com", f"Person {tag}")


def _org(conn, plan=None):
    owner = _u(conn, "owner")
    oid = orgs.create_org(conn, "Org", owner)
    if plan:
        subscriptions.subscribe(conn, oid, plan, date(2025, 1, 15))
    return oid, owner


def rhu(num, den):
    x = Fraction(num, den)
    s = -1 if x < 0 else 1
    return s * int(abs(x) + Fraction(1, 2))


# ------------------------------------------------------------------ ACC-101 proration & tax
@pytest.mark.parametrize("old,new,start,end,change", [
    (4900, 19900, date(2025, 1, 15), date(2025, 2, 15), date(2025, 2, 5)),
    (19900, 4900, date(2025, 1, 15), date(2025, 2, 15), date(2025, 2, 5)),
    (0, 4900, date(2025, 2, 1), date(2025, 3, 1), date(2025, 2, 15)),
    (4900, 0, date(2024, 2, 1), date(2024, 3, 1), date(2024, 2, 8)),
    (4900, 19900, date(2025, 3, 31), date(2025, 4, 30), date(2025, 4, 29)),
    (19900, 4900, date(2025, 1, 1), date(2025, 2, 1), date(2025, 1, 1)),
])
def test_acc101_proration_exact(old, new, start, end, change):
    expected = rhu((new - old) * (end - change).days, (end - start).days)
    assert billing.prorate(old, new, start, end, change) == expected


@pytest.mark.parametrize("subtotal,bp", [(4900, 2050), (19900, 2050), (1, 5000), (3, 5000), (10050, 1250), (-4839, 2050)])
def test_acc101_tax_half_up(subtotal, bp):
    assert billing.tax_cents(subtotal, bp) == rhu(subtotal * bp, 10000)


def test_acc101_invoice_uses_exact_rules(conn):
    oid, owner = _org(conn, "team")
    amount = subscriptions.change_plan(conn, oid, "business", date(2025, 2, 5))
    assert amount == 4839
    inv = invoices.get_invoice(conn, invoices.generate_invoice(conn, oid, tax_rate_bp=2050, issued_on=date(2025, 2, 6)))
    assert inv["subtotal_cents"] == 19900 + 4839
    assert inv["tax_cents"] == rhu((19900 + 4839) * 2050, 10000)


# ------------------------------------------------------------------ ACC-102 remove owners
def test_acc102_remove_owner_when_another_exists(conn):
    oid, owner = _org(conn, "business")
    other = _u(conn, "o2")
    orgs.add_member(conn, oid, other, "owner")
    orgs.remove_member(conn, oid, owner, actor_id=other)
    assert orgs.owners(conn, oid) == [other]


def test_acc102_cannot_remove_last_owner(conn):
    oid, owner = _org(conn, "business")
    with pytest.raises(LastOwnerError):
        orgs.remove_member(conn, oid, owner)
    assert orgs.owners(conn, oid) == [owner]


# ------------------------------------------------------------------ ACC-103 seat limits
def test_acc103_free_default_limit(conn):
    oid, owner = _org(conn)
    orgs.add_member(conn, oid, _u(conn, "a"))
    orgs.add_member(conn, oid, _u(conn, "b"))
    with pytest.raises(SeatLimitExceeded) as ei:
        orgs.add_member(conn, oid, _u(conn, "c"))
    assert ei.value.limit == 3
    assert orgs.member_count(conn, oid) == 3


def test_acc103_team_limit_and_unlimited_business(conn):
    oid, owner = _org(conn, "team")
    for i in range(9):
        orgs.add_member(conn, oid, _u(conn, f"t{i}"))
    with pytest.raises(SeatLimitExceeded):
        orgs.add_member(conn, oid, _u(conn, "extra"))
    subscriptions.change_plan(conn, oid, "business", date(2025, 1, 20))
    for i in range(10, 15):
        orgs.add_member(conn, oid, _u(conn, f"t{i}"))
    assert orgs.member_count(conn, oid) == 15


def test_acc103_downgrade_blocked_and_unchanged(conn):
    oid, owner = _org(conn, "team")
    for i in range(4):
        orgs.add_member(conn, oid, _u(conn, f"d{i}"))
    before = conn.execute("SELECT COUNT(*) FROM subscription_adjustments").fetchone()[0]
    with pytest.raises(SeatLimitExceeded):
        subscriptions.change_plan(conn, oid, "free", date(2025, 1, 20))
    assert subscriptions.get_subscription(conn, oid)["plan"] == "team"
    assert conn.execute("SELECT COUNT(*) FROM subscription_adjustments").fetchone()[0] == before


# ------------------------------------------------------------------ ACC-104 email case
def test_acc104_case_insensitive_identity(conn):
    uid = users.create_user(conn, "Kim@Initech.example", "Kim Lee")
    assert users.get_user(conn, uid)["email"] == "kim@initech.example"
    assert users.get_user_by_email(conn, "KIM@INITECH.EXAMPLE")["id"] == uid
    assert users.get_user_by_email(conn, " kim@initech.example ")["id"] == uid
    with pytest.raises(Conflict):
        users.create_user(conn, "kim@initech.EXAMPLE", "Kim Twin")


# ------------------------------------------------------------------ ACC-105 audit
def test_acc105_role_change_audited(conn):
    oid, owner = _org(conn, "business")
    u = _u(conn, "r")
    orgs.add_member(conn, oid, u, "member", actor_id=owner)
    orgs.change_role(conn, oid, u, "billing_admin", actor_id=owner)
    orgs.change_role(conn, oid, u, "billing_admin", actor_id=owner)  # no-op: not recorded
    e = audit.entries(conn, action="member.role_changed")
    assert len(e) == 1
    assert e[0]["target"] == f"org:{oid}/user:{u}" and e[0]["actor_id"] == owner
    assert e[0]["details"] == {"from": "member", "to": "billing_admin"}


def test_acc105_plan_change_audited(conn):
    oid, owner = _org(conn, "team")
    amount = subscriptions.change_plan(conn, oid, "business", date(2025, 2, 5), actor_id=owner)
    subscriptions.change_plan(conn, oid, "business", date(2025, 2, 6), actor_id=owner)  # no-op
    e = audit.entries(conn, action="subscription.plan_changed")
    assert len(e) == 1
    assert e[0]["target"] == f"org:{oid}" and e[0]["actor_id"] == owner
    assert e[0]["details"] == {"from": "team", "to": "business", "proration_cents": amount}


# ------------------------------------------------------------------ ACC-108 permissions
def test_acc108_permission_table_matches_docs(conn):
    oid, owner = _org(conn, "business")
    expected = {
        "admin": {"org.read", "org.update", "members.manage", "billing.read"},
        "billing_admin": {"org.read", "billing.read", "billing.manage"},
        "member": {"org.read"},
    }
    actions = ["org.read", "org.update", "org.delete", "members.manage", "billing.read", "billing.manage"]
    for role, allowed in expected.items():
        u = _u(conn, role)
        orgs.add_member(conn, oid, u, role)
        assert {a for a in actions if permissions.can(conn, u, oid, a)} == allowed, role
    assert permissions.AUTH_CHECKS_ENABLED is True


def test_acc108_billing_admin_cannot_delete(conn):
    oid, owner = _org(conn, "business")
    b = _u(conn, "billing")
    orgs.add_member(conn, oid, b, "billing_admin")
    with pytest.raises(AccountError):
        orgs.delete_org(conn, oid, actor_id=b)
    assert orgs.get_org(conn, oid)["deleted_at"] is None


# ------------------------------------------------------------------ ACC-109 names (code part)
def _staging_like_db():
    c = db.connect()
    c.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
    for p in sorted((HERE / "base_migrations").glob("*.sql")):
        c.executescript(p.read_text())
        c.execute("INSERT INTO schema_migrations VALUES (?, '2025-01-01T00:00:00+00:00')", (p.stem,))
    c.executescript((HERE / "staging_seed.sql").read_text())
    names = {r["id"]: r["full_name"] for r in c.execute("SELECT id, full_name FROM users")}
    db.migrate(c)
    return c, names


def test_acc109_migration_backfills_names():
    c, names = _staging_like_db()
    cols = {r["name"] for r in c.execute("PRAGMA table_info(users)")}
    assert {"first_name", "last_name"} <= cols
    for r in c.execute("SELECT id, first_name, last_name FROM users"):
        parts = names[r["id"]].split()
        assert (r["first_name"], r["last_name"]) == (parts[0], " ".join(parts[1:])), names[r["id"]]


def test_acc109_create_user_and_display_name(conn):
    uid = users.create_user(conn, "m@example.com", "  Maria   da Silva  Santos ")
    u = users.get_user(conn, uid)
    assert (u["first_name"], u["last_name"]) == ("Maria", "da Silva Santos")
    assert users.display_name(conn, uid) == "Maria da Silva Santos"
    uid2 = users.create_user(conn, "cher@example.com", "Cher")
    assert (users.get_user(conn, uid2)["first_name"], users.get_user(conn, uid2)["last_name"]) == ("Cher", "")
    assert users.display_name(conn, uid2) == "Cher"


# ------------------------------------------------------------------ ACC-111 CLI
def test_acc111_list_invoices_empty(tmp_path, capsys):
    dbp = str(tmp_path / "t.db")
    assert cli.main(["--db", dbp, "migrate"]) == 0
    cli.main(["--db", dbp, "create-user", "a@example.com", "A B"])
    cli.main(["--db", dbp, "create-org", "Acme", "--owner", "1"])
    capsys.readouterr()
    assert cli.main(["--db", dbp, "list-invoices", "--org", "1"]) == 0
    out = capsys.readouterr().out
    assert "NUMBER" in out and "(no invoices)" in out


def test_acc111_list_invoices_non_empty_unchanged(tmp_path, capsys):
    dbp = str(tmp_path / "t.db")
    cli.main(["--db", dbp, "migrate"])
    cli.main(["--db", dbp, "create-user", "a@example.com", "A B"])
    cli.main(["--db", dbp, "create-org", "Acme", "--owner", "1"])
    cli.main(["--db", dbp, "subscribe", "--org", "1", "--plan", "team", "--start", "2025-01-15"])
    cli.main(["--db", dbp, "invoice", "--org", "1"])
    capsys.readouterr()
    assert cli.main(["--db", dbp, "list-invoices", "--org", "1"]) == 0
    out = capsys.readouterr().out
    assert "INV-" in out and "49.00" in out and "(no invoices)" not in out


# ------------------------------------------------------------------ ACC-112 periods
@pytest.mark.parametrize("d,n,expected", [
    (date(2025, 1, 31), 1, date(2025, 2, 28)), (date(2024, 1, 31), 1, date(2024, 2, 29)),
    (date(2025, 1, 31), 2, date(2025, 3, 31)), (date(2025, 8, 31), 1, date(2025, 9, 30)),
    (date(2025, 1, 29), 1, date(2025, 2, 28)), (date(2025, 12, 31), 2, date(2026, 2, 28)),
    (date(2025, 1, 15), 1, date(2025, 2, 15)), (date(2024, 2, 29), 12, date(2025, 2, 28)),
])
def test_acc112_add_months_clamps(d, n, expected):
    assert billing.add_months(d, n) == expected


def test_acc112_renewals_do_not_drift(conn):
    oid, owner = _org(conn)
    subscriptions.subscribe(conn, oid, "team", date(2025, 1, 31))
    seen = [subscriptions.current_period(conn, oid)] + [subscriptions.renew(conn, oid) for _ in range(4)]
    assert seen == [(date(2025, 1, 31), date(2025, 2, 28)), (date(2025, 2, 28), date(2025, 3, 31)),
                    (date(2025, 3, 31), date(2025, 4, 30)), (date(2025, 4, 30), date(2025, 5, 31)),
                    (date(2025, 5, 31), date(2025, 6, 30))]


# ------------------------------------------------------------------ invariants (held before the sprint)
OPS = st.lists(st.tuples(st.sampled_from(["add", "remove", "role"]), st.integers(0, 6),
                         st.sampled_from(["owner", "admin", "billing_admin", "member"])), max_size=40)


@settings(max_examples=200, deadline=None, derandomize=True, database=None,
          suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
@given(OPS)
def test_inv_org_always_has_an_owner(ops):
    c = db.connect()
    db.migrate(c)
    oid, owner = _org(c, "business")
    people = [owner] + [_u(c, f"p{i}") for i in range(6)]
    for kind, idx, role in ops:
        uid = people[idx]
        try:
            if kind == "add":
                orgs.add_member(c, oid, uid, role)
            elif kind == "remove":
                orgs.remove_member(c, oid, uid)
            else:
                orgs.change_role(c, oid, uid, role)
        except AccountError:
            pass
        assert len(orgs.owners(c, oid)) >= 1
    c.close()


def test_inv_invoice_totals_consistent(conn):
    oid, owner = _org(conn, "team")
    subscriptions.change_plan(conn, oid, "business", date(2025, 1, 20))
    subscriptions.change_plan(conn, oid, "team", date(2025, 2, 1))
    inv = invoices.get_invoice(conn, invoices.generate_invoice(conn, oid, tax_rate_bp=1900, issued_on=date(2025, 2, 2)))
    assert inv["subtotal_cents"] == sum(l["amount_cents"] for l in inv["lines"])
    assert inv["total_cents"] == inv["subtotal_cents"] + inv["tax_cents"]
    assert all(isinstance(l["amount_cents"], int) for l in inv["lines"])


def test_inv_deny_by_default(conn):
    oid, owner = _org(conn, "business")
    stranger = _u(conn, "stranger")
    for action in ("org.read", "billing.read", "org.delete"):
        assert not permissions.can(conn, stranger, oid, action)
    assert not permissions.can(conn, owner, oid, "org.nuke")
    users.deactivate_user(conn, owner)
    assert not permissions.can(conn, owner, oid, "org.read")


def test_inv_members_cannot_manage(conn):
    oid, owner = _org(conn, "business")
    m = _u(conn, "m")
    orgs.add_member(conn, oid, m, "member")
    with pytest.raises(AccountError):
        orgs.add_member(conn, oid, _u(conn, "x"), actor_id=m)
    with pytest.raises(AccountError):
        orgs.delete_org(conn, oid, actor_id=m)
