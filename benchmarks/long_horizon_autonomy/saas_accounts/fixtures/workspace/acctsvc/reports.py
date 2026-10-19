"""Read-only business reports used by the finance and customer-success dashboards."""

from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass

from acctsvc.plans import PLANS, get_plan


@dataclass(frozen=True)
class SeatUsage:
    org_id: int
    org_name: str
    plan: str
    members: int
    seats: int | None

    @property
    def utilisation(self) -> float | None:
        return None if self.seats is None else self.members / self.seats


def monthly_recurring_revenue_cents(conn: sqlite3.Connection) -> int:
    """Sum of monthly plan prices of active subscriptions of non-deleted organisations."""
    total = 0
    for row in conn.execute(
            "SELECT s.plan FROM subscriptions s JOIN orgs o ON o.id = s.org_id "
            "WHERE s.status = 'active' AND o.deleted_at IS NULL"):
        total += get_plan(row["plan"]).monthly_price_cents
    return total


def plan_distribution(conn: sqlite3.Connection) -> dict[str, int]:
    counts = Counter(r["plan"] for r in conn.execute(
        "SELECT s.plan FROM subscriptions s JOIN orgs o ON o.id = s.org_id WHERE o.deleted_at IS NULL"))
    return {name: counts.get(name, 0) for name in PLANS}


def seat_usage(conn: sqlite3.Connection) -> list[SeatUsage]:
    rows = conn.execute(
        "SELECT o.id, o.name, COALESCE(s.plan, 'free') AS plan, "
        "(SELECT COUNT(*) FROM memberships m WHERE m.org_id = o.id) AS members "
        "FROM orgs o LEFT JOIN subscriptions s ON s.org_id = o.id WHERE o.deleted_at IS NULL ORDER BY o.id")
    return [SeatUsage(r["id"], r["name"], r["plan"], r["members"], get_plan(r["plan"]).seats) for r in rows]


def orgs_over_seat_limit(conn: sqlite3.Connection) -> list[SeatUsage]:
    return [u for u in seat_usage(conn) if u.seats is not None and u.members > u.seats]
