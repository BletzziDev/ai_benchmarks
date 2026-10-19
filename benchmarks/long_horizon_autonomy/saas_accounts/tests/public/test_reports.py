from datetime import date

from acctsvc import exports, orgs, reports, subscriptions


def test_mrr_and_distribution(conn, org):
    subscriptions.subscribe(conn, org["id"], "team", date(2025, 1, 1))
    other = orgs.create_org(conn, "Other", org["owner"])
    subscriptions.subscribe(conn, other, "business", date(2025, 1, 1))
    assert reports.monthly_recurring_revenue_cents(conn) == 4900 + 19900
    assert reports.plan_distribution(conn) == {"free": 0, "team": 1, "business": 1}
    orgs.delete_org(conn, other, actor_id=org["owner"])
    assert reports.monthly_recurring_revenue_cents(conn) == 4900


def test_seat_usage_defaults_to_free(conn, org):
    usage = reports.seat_usage(conn)
    assert usage[0].plan == "free" and usage[0].members == 1 and usage[0].seats == 3


def test_exports(conn, org):
    text = exports.users_csv(conn)
    assert text.splitlines()[0] == "id,email,name,active,created_at"
    assert "Olive Owner" in text
    assert exports.org_members_csv(conn, org["id"]).splitlines()[1].endswith(",owner")
