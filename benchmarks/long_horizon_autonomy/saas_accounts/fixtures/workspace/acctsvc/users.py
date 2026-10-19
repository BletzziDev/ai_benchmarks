"""User accounts.

Email addresses identify users and must be unique. See docs/ARCHITECTURE.md#users.
"""

from __future__ import annotations

import re
import sqlite3

from acctsvc.db import utcnow
from acctsvc.errors import Conflict, NotFound

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def create_user(conn: sqlite3.Connection, email: str, full_name: str, now: str | None = None) -> int:
    email = email.strip()
    full_name = " ".join(full_name.split())
    if not EMAIL_RE.match(email):
        raise ValueError(f"invalid email: {email!r}")
    if not full_name:
        raise ValueError("full_name is required")
    if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
        raise Conflict(f"a user with email {email} already exists")
    cur = conn.execute("INSERT INTO users(email, full_name, created_at, active) VALUES (?, ?, ?, 1)",
                       (email, full_name, now or utcnow()))
    return int(cur.lastrowid)


def get_user(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise NotFound(f"user {user_id}")
    return row


def get_user_by_email(conn: sqlite3.Connection, email: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM users WHERE email = ?", (email.strip(),)).fetchone()


def display_name(conn: sqlite3.Connection, user_id: int) -> str:
    return get_user(conn, user_id)["full_name"]


def deactivate_user(conn: sqlite3.Connection, user_id: int) -> None:
    get_user(conn, user_id)
    conn.execute("UPDATE users SET active = 0 WHERE id = ?", (user_id,))


def list_users(conn: sqlite3.Connection, active_only: bool = True) -> list[sqlite3.Row]:
    sql = "SELECT * FROM users" + (" WHERE active = 1" if active_only else "") + " ORDER BY id"
    return list(conn.execute(sql))
