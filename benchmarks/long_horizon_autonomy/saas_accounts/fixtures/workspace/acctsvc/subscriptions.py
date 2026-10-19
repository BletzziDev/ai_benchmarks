"""Subscriptions: one per organisation, anchored on its start date."""

from __future__ import annotations

import sqlite3
from datetime import date

from acctsvc import audit, billing
from acctsvc.errors import Conflict, NotFound
from acctsvc.plans import get_plan


def subscribe(conn: sqlite3.Connection, org_id: int, plan_name: str, start: date,
              actor_id: int | None = None) -> int:
    get_plan(plan_name)
    if conn.execute("SELECT 1 FROM subscriptions WHERE org_id = ?", (org_id,)).fetchone():
        raise Conflict(f"org {org_id} already has a subscription")
    p_start, p_end = billing.period(start, 0)
    cur = conn.execute(
        "INSERT INTO subscriptions(org_id, plan, anchor_date, period_index, period_start, period_end, status) "
        "VALUES (?, ?, ?, 0, ?, ?, 'active')",
        (org_id, plan_name, start.isoformat(), p_start.isoformat(), p_end.isoformat()))
    audit.record(conn, actor_id, "subscription.created", f"org:{org_id}", {"plan": plan_name})
    return int(cur.lastrowid)


def get_subscription(conn: sqlite3.Connection, org_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM subscriptions WHERE org_id = ?", (org_id,)).fetchone()
    if row is None:
        raise NotFound(f"org {org_id} has no subscription")
    return row


def current_period(conn: sqlite3.Connection, org_id: int) -> tuple[date, date]:
    s = get_subscription(conn, org_id)
    return date.fromisoformat(s["period_start"]), date.fromisoformat(s["period_end"])


def renew(conn: sqlite3.Connection, org_id: int) -> tuple[date, date]:
    """Advance to the next billing period."""
    s = get_subscription(conn, org_id)
    idx = s["period_index"] + 1
    p_start, p_end = billing.period(date.fromisoformat(s["anchor_date"]), idx)
    conn.execute("UPDATE subscriptions SET period_index = ?, period_start = ?, period_end = ? WHERE org_id = ?",
                 (idx, p_start.isoformat(), p_end.isoformat(), org_id))
    return p_start, p_end


def change_plan(conn: sqlite3.Connection, org_id: int, new_plan: str, on_date: date,
                actor_id: int | None = None) -> int:
    """Switch plans mid-period. Returns the proration amount (cents) added to the next invoice."""
    s = get_subscription(conn, org_id)
    old = get_plan(s["plan"])
    new = get_plan(new_plan)
    if old.name == new.name:
        return 0
    p_start, p_end = date.fromisoformat(s["period_start"]), date.fromisoformat(s["period_end"])
    amount = billing.prorate(old.monthly_price_cents, new.monthly_price_cents, p_start, p_end, on_date)
    conn.execute("UPDATE subscriptions SET plan = ? WHERE org_id = ?", (new.name, org_id))
    conn.execute(
        "INSERT INTO subscription_adjustments(org_id, description, amount_cents, invoiced) VALUES (?, ?, ?, 0)",
        (org_id, f"Proration {old.name} -> {new.name} from {on_date.isoformat()}", amount))
    return amount
