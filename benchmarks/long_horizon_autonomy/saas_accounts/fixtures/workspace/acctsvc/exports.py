"""CSV exports for support (no secrets, no token hashes)."""

from __future__ import annotations

import csv
import io
import sqlite3

from acctsvc import orgs, users


def users_csv(conn: sqlite3.Connection) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["id", "email", "name", "active", "created_at"])
    for r in conn.execute("SELECT id, email, active, created_at FROM users ORDER BY id"):
        w.writerow([r["id"], r["email"], users.display_name(conn, r["id"]), int(r["active"]), r["created_at"]])
    return buf.getvalue()


def org_members_csv(conn: sqlite3.Connection, org_id: int) -> str:
    orgs.get_org(conn, org_id)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["user_id", "email", "role"])
    for m in orgs.members(conn, org_id):
        w.writerow([m["user_id"], m["email"], m["role"]])
    return buf.getvalue()
