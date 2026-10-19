"""Append-only audit log. Every state change made on behalf of a user must be recorded.

Action names are dotted ``<entity>.<verb>`` strings (see docs/ARCHITECTURE.md#audit-log).
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from acctsvc.db import utcnow


def record(conn: sqlite3.Connection, actor_id: int | None, action: str, target: str,
           details: dict[str, Any] | None = None, now: str | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO audit_log(ts, actor_id, action, target, details_json) VALUES (?, ?, ?, ?, ?)",
        (now or utcnow(), actor_id, action, target, json.dumps(details or {}, sort_keys=True)),
    )
    return int(cur.lastrowid)


def entries(conn: sqlite3.Connection, target: str | None = None, action: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT id, ts, actor_id, action, target, details_json FROM audit_log"
    clauses, args = [], []
    if target is not None:
        clauses.append("target = ?")
        args.append(target)
    if action is not None:
        clauses.append("action = ?")
        args.append(action)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY id"
    return [
        {"id": r["id"], "ts": r["ts"], "actor_id": r["actor_id"], "action": r["action"], "target": r["target"],
         "details": json.loads(r["details_json"])}
        for r in conn.execute(sql, args)
    ]
