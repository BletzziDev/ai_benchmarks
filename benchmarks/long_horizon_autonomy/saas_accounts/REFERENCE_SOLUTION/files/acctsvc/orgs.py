"""Organisations and memberships.

Invariant (docs/ARCHITECTURE.md#organisations): every organisation always has at least one
member with role ``owner``. Every operation that removes or demotes an owner must preserve it.
"""

from __future__ import annotations

import sqlite3

from acctsvc import audit
from acctsvc.db import utcnow
from acctsvc.errors import Conflict, LastOwnerError, NotFound, SeatLimitExceeded
from acctsvc.permissions import require
from acctsvc.plans import get_plan

ROLES = ("owner", "admin", "billing_admin", "member")


def _target(org_id: int, user_id: int | None = None) -> str:
    return f"org:{org_id}" if user_id is None else f"org:{org_id}/user:{user_id}"


def get_org(conn: sqlite3.Connection, org_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM orgs WHERE id = ?", (org_id,)).fetchone()
    if row is None:
        raise NotFound(f"org {org_id}")
    return row


def create_org(conn: sqlite3.Connection, name: str, owner_id: int, now: str | None = None) -> int:
    name = name.strip()
    if not name:
        raise ValueError("organisation name is required")
    if conn.execute("SELECT 1 FROM users WHERE id = ?", (owner_id,)).fetchone() is None:
        raise NotFound(f"user {owner_id}")
    cur = conn.execute("INSERT INTO orgs(name, created_at) VALUES (?, ?)", (name, now or utcnow()))
    org_id = int(cur.lastrowid)
    conn.execute("INSERT INTO memberships(org_id, user_id, role) VALUES (?, ?, 'owner')", (org_id, owner_id))
    audit.record(conn, owner_id, "org.created", _target(org_id), {"name": name})
    return org_id


def members(conn: sqlite3.Connection, org_id: int) -> list[sqlite3.Row]:
    return list(conn.execute(
        "SELECT m.user_id, m.role, u.email FROM memberships m JOIN users u ON u.id = m.user_id "
        "WHERE m.org_id = ? ORDER BY m.user_id", (org_id,)))


def owners(conn: sqlite3.Connection, org_id: int) -> list[int]:
    return [r["user_id"] for r in conn.execute(
        "SELECT user_id FROM memberships WHERE org_id = ? AND role = 'owner' ORDER BY user_id", (org_id,))]


def member_count(conn: sqlite3.Connection, org_id: int) -> int:
    return int(conn.execute("SELECT COUNT(*) AS n FROM memberships WHERE org_id = ?", (org_id,)).fetchone()["n"])


def seat_limit(conn: sqlite3.Connection, org_id: int) -> tuple[str, int | None]:
    """(plan name, seat limit) for the org's current plan; orgs without a subscription are 'free'."""
    row = conn.execute("SELECT plan FROM subscriptions WHERE org_id = ?", (org_id,)).fetchone()
    plan = get_plan(row["plan"] if row else "free")
    return plan.name, plan.seats


def add_member(conn: sqlite3.Connection, org_id: int, user_id: int, role: str = "member",
               actor_id: int | None = None) -> None:
    get_org(conn, org_id)
    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}")
    if actor_id is not None:
        require(conn, actor_id, org_id, "members.manage")
    if conn.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone() is None:
        raise NotFound(f"user {user_id}")
    if conn.execute("SELECT 1 FROM memberships WHERE org_id = ? AND user_id = ?", (org_id, user_id)).fetchone():
        raise Conflict(f"user {user_id} is already a member of org {org_id}")
    plan, limit = seat_limit(conn, org_id)
    if limit is not None and member_count(conn, org_id) >= limit:
        raise SeatLimitExceeded(plan, limit)
    conn.execute("INSERT INTO memberships(org_id, user_id, role) VALUES (?, ?, ?)", (org_id, user_id, role))
    audit.record(conn, actor_id, "member.added", _target(org_id, user_id), {"role": role})


def change_role(conn: sqlite3.Connection, org_id: int, user_id: int, new_role: str,
                actor_id: int | None = None) -> None:
    if new_role not in ROLES:
        raise ValueError(f"unknown role {new_role!r}")
    if actor_id is not None:
        require(conn, actor_id, org_id, "members.manage")
    row = conn.execute("SELECT role FROM memberships WHERE org_id = ? AND user_id = ?", (org_id, user_id)).fetchone()
    if row is None:
        raise NotFound(f"user {user_id} is not a member of org {org_id}")
    old_role = row["role"]
    if old_role == new_role:
        return
    if old_role == "owner" and owners(conn, org_id) == [user_id]:
        raise LastOwnerError(f"user {user_id} is the last owner of org {org_id}")
    conn.execute("UPDATE memberships SET role = ? WHERE org_id = ? AND user_id = ?", (new_role, org_id, user_id))
    audit.record(conn, actor_id, "member.role_changed", _target(org_id, user_id), {"from": old_role, "to": new_role})


def remove_member(conn: sqlite3.Connection, org_id: int, user_id: int, actor_id: int | None = None) -> None:
    if actor_id is not None:
        require(conn, actor_id, org_id, "members.manage")
    row = conn.execute("SELECT role FROM memberships WHERE org_id = ? AND user_id = ?", (org_id, user_id)).fetchone()
    if row is None:
        raise NotFound(f"user {user_id} is not a member of org {org_id}")
    if row["role"] == "owner" and owners(conn, org_id) == [user_id]:
        raise LastOwnerError(f"user {user_id} is the last owner of org {org_id}")
    conn.execute("DELETE FROM memberships WHERE org_id = ? AND user_id = ?", (org_id, user_id))
    audit.record(conn, actor_id, "member.removed", _target(org_id, user_id), {"role": row["role"]})


def delete_org(conn: sqlite3.Connection, org_id: int, actor_id: int) -> None:
    get_org(conn, org_id)
    require(conn, actor_id, org_id, "org.delete")
    conn.execute("DELETE FROM memberships WHERE org_id = ?", (org_id,))
    conn.execute("UPDATE orgs SET deleted_at = ? WHERE id = ?", (utcnow(), org_id))
    audit.record(conn, actor_id, "org.deleted", _target(org_id))
