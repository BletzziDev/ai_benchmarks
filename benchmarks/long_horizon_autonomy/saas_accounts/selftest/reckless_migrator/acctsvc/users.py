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
    email = normalize_email(email)
    full_name = " ".join(full_name.split())
    if not EMAIL_RE.match(email):
        raise ValueError(f"invalid email: {email!r}")
    if not full_name:
        raise ValueError("full_name is required")
    if conn.execute("SELECT 1 FROM users WHERE lower(email) = ?", (email,)).fetchone():
        raise Conflict(f"a user with email {email} already exists")
    first, last = split_name(full_name)
    cur = conn.execute("INSERT INTO users(email, first_name, last_name, created_at, active) VALUES (?, ?, ?, ?, 1)",
                       (email, first, last, now or utcnow()))
    return int(cur.lastrowid)


def normalize_email(email: str) -> str:
    """Emails are case-insensitive (docs/ARCHITECTURE.md#users); stored lower-cased."""
    return email.strip().lower()


def split_name(full_name: str) -> tuple[str, str]:
    """First whitespace-separated token, and the rest single-space joined ('' if none)."""
    parts = full_name.split()
    return (parts[0], " ".join(parts[1:])) if parts else ("", "")


def get_user(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise NotFound(f"user {user_id}")
    return row


def get_user_by_email(conn: sqlite3.Connection, email: str) -> sqlite3.Row | None:
    # Rows created before ACC-104 may have mixed-case emails, so compare case-insensitively.
    return conn.execute("SELECT * FROM users WHERE lower(email) = ? ORDER BY id LIMIT 1",
                        (normalize_email(email),)).fetchone()


def display_name(conn: sqlite3.Connection, user_id: int) -> str:
    u = get_user(conn, user_id)
    return f"{u['first_name']} {u['last_name']}".strip()


def deactivate_user(conn: sqlite3.Connection, user_id: int) -> None:
    get_user(conn, user_id)
    conn.execute("UPDATE users SET active = 0 WHERE id = ?", (user_id,))


def list_users(conn: sqlite3.Connection, active_only: bool = True) -> list[sqlite3.Row]:
    sql = "SELECT * FROM users" + (" WHERE active = 1" if active_only else "") + " ORDER BY id"
    return list(conn.execute(sql))
