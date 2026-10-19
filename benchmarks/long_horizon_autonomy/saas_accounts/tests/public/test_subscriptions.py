from datetime import date

import pytest

from acctsvc import subscriptions
from acctsvc.errors import Conflict, InvalidPlan


def test_subscribe_and_renew(conn, org):
    subscriptions.subscribe(conn, org["id"], "team", date(2025, 1, 15))
    assert subscriptions.current_period(conn, org["id"]) == (date(2025, 1, 15), date(2025, 2, 15))
    assert subscriptions.renew(conn, org["id"]) == (date(2025, 2, 15), date(2025, 3, 15))


def test_one_subscription_per_org(conn, org):
    subscriptions.subscribe(conn, org["id"], "free", date(2025, 1, 1))
    with pytest.raises(Conflict):
        subscriptions.subscribe(conn, org["id"], "team", date(2025, 1, 1))


def test_invalid_plan(conn, org):
    with pytest.raises(InvalidPlan):
        subscriptions.subscribe(conn, org["id"], "platinum", date(2025, 1, 1))


def test_change_plan_same_plan_is_noop(conn, org):
    subscriptions.subscribe(conn, org["id"], "team", date(2025, 1, 15))
    assert subscriptions.change_plan(conn, org["id"], "team", date(2025, 1, 20)) == 0
