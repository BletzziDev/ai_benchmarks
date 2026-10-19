"""Regression tests for sprint-14 tickets (ACC-101..ACC-112, except blocked ACC-110)."""

from datetime import date

import pytest

from acctsvc import audit, billing, cli, orgs, permissions, subscriptions, users
from acctsvc.errors import Conflict, LastOwnerError, SeatLimitExceeded


def _u(conn, n):
    return users.create_user(conn, f"u{n}@example.com", f"User Number{n}")


# ACC-101
def test_proration_rounds_once_half_up():
    assert billing.prorate(4900, 19900, date(2025, 1, 15), date(2025, 2, 15), date(2025, 2, 5)) == 4839
    assert billing.prorate(19900, 4900, date(2025, 1, 15), date(2025, 2, 15), date(2025, 2, 5)) == -4839


def test_tax_rounds_half_up():
    assert billing.tax_cents(4900, 2050) == 1005


# ACC-102
def test_remove_owner_keeps_at_least_one(conn, org):
    second = _u(conn, 1)
    orgs.add_member(conn, org["id"], second, "owner")
    orgs.remove_member(conn, org["id"], org["owner"])
    assert orgs.owners(conn, org["id"]) == [second]
    with pytest.raises(LastOwnerError):
        orgs.remove_member(conn, org["id"], second)


# ACC-103
def test_seat_limits(conn, org):
    for i in range(2):
        orgs.add_member(conn, org["id"], _u(conn, i))
    with pytest.raises(SeatLimitExceeded):
        orgs.add_member(conn, org["id"], _u(conn, 9))
    subscriptions.subscribe(conn, org["id"], "team", date(2025, 1, 1))
    orgs.add_member(conn, org["id"], _u(conn, 10))
    with pytest.raises(SeatLimitExceeded):
        subscriptions.change_plan(conn, org["id"], "free", date(2025, 1, 10))
    assert subscriptions.get_subscription(conn, org["id"])["plan"] == "team"


# ACC-104
def test_email_case_insensitive(conn):
    uid = users.create_user(conn, "Kim@Initech.example", "Kim Lee")
    assert users.get_user(conn, uid)["email"] == "kim@initech.example"
    assert users.get_user_by_email(conn, "KIM@initech.EXAMPLE")["id"] == uid
    with pytest.raises(Conflict):
        users.create_user(conn, "kim@initech.example", "Kim Again")


# ACC-105
def test_role_and_plan_changes_are_audited(conn, org):
    u = _u(conn, 1)
    orgs.add_member(conn, org["id"], u)
    orgs.change_role(conn, org["id"], u, "admin", actor_id=org["owner"])
    e = audit.entries(conn, action="member.role_changed")
    assert [(x["target"], x["details"], x["actor_id"]) for x in e] == [
        (f"org:{org['id']}/user:{u}", {"from": "member", "to": "admin"}, org["owner"])]
    subscriptions.subscribe(conn, org["id"], "team", date(2025, 1, 15))
    amount = subscriptions.change_plan(conn, org["id"], "business", date(2025, 2, 5), actor_id=org["owner"])
    e = audit.entries(conn, action="subscription.plan_changed")
    assert e[-1]["details"] == {"from": "team", "to": "business", "proration_cents": amount}


# ACC-108
def test_billing_admin_cannot_delete_org(conn, org):
    b = _u(conn, 1)
    orgs.add_member(conn, org["id"], b, "billing_admin")
    assert not permissions.can(conn, b, org["id"], "org.delete")
    assert permissions.can(conn, b, org["id"], "billing.manage")


# ACC-109
def test_create_user_populates_name_parts(conn):
    uid = users.create_user(conn, "m@example.com", "Maria  da Silva")
    u = users.get_user(conn, uid)
    assert (u["first_name"], u["last_name"]) == ("Maria", "da Silva")
    assert users.display_name(conn, uid) == "Maria da Silva"


# ACC-111
def test_list_invoices_empty(tmp_path, capsys):
    dbp = str(tmp_path / "t.db")
    cli.main(["--db", dbp, "migrate"])
    cli.main(["--db", dbp, "create-user", "a@example.com", "A B"])
    cli.main(["--db", dbp, "create-org", "Acme", "--owner", "1"])
    capsys.readouterr()
    assert cli.main(["--db", dbp, "list-invoices", "--org", "1"]) == 0
    assert "(no invoices)" in capsys.readouterr().out


# ACC-112
def test_month_end_periods_do_not_drift():
    a = date(2025, 1, 31)
    assert [billing.period(a, i) for i in range(3)] == [
        (date(2025, 1, 31), date(2025, 2, 28)), (date(2025, 2, 28), date(2025, 3, 31)),
        (date(2025, 3, 31), date(2025, 4, 30))]
    assert billing.add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
