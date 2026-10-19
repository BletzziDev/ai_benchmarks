"""SQLite persistence."""

from __future__ import annotations

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, salt TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    owner_id INTEGER NOT NULL REFERENCES users(id), title TEXT NOT NULL, body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY, note_id INTEGER NOT NULL REFERENCES notes(id), name TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: str = ":memory:"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        cur = self.conn.execute(sql, params)
        self.conn.commit()
        return cur

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        return list(self.conn.execute(sql, params))
