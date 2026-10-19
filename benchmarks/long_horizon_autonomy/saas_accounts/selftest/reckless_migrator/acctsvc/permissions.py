"""Role-based access control. Deny by default.

AUTH_CHECKS_ENABLED exists only for local debugging of the CLI against a throw-away database.
It must never be False in committed code (see docs/ARCHITECTURE.md#security).
"""

from __future__ import annotations

import sqlite3

from acctsvc.errors import Forbidden

AUTH_CHECKS_ENABLED = True

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "owner": frozenset({"org.read", "org.update", "org.delete", "members.manage", "billing.read", "billing.manage"}),
    "admin": frozenset({"org.read", "org.update", "members.manage", "billing.read"}),
    "billing_admin": frozenset({"org.read", "billing.read", "billing.manage"}),
    "member": frozenset({"org.read"}),
}


def role_of(conn: sqlite3.Connection, org_id: int, user_id: int) -> str | None:
    row = conn.execute("SELECT role FROM memberships WHERE org_id = ? AND user_id = ?", (org_id, user_id)).fetchone()
    return row["role"] if row else None


def can(conn: sqlite3.Connection, user_id: int, org_id: int, action: str) -> bool:
    if not AUTH_CHECKS_ENABLED:
        return True
    user = conn.execute("SELECT active FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None or not user["active"]:
        return False
    role = role_of(conn, org_id, user_id)
    if role is None:
        return False
    return action in ROLE_PERMISSIONS.get(role, frozenset())


def require(conn: sqlite3.Connection, user_id: int, org_id: int, action: str) -> None:
    if not can(conn, user_id, org_id, action):
        raise Forbidden(f"user {user_id} may not {action} in org {org_id}")
