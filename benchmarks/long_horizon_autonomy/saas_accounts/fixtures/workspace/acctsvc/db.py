"""SQLite connection helpers and the migration runner.

Migrations live in ``migrations/`` and are applied in lexical order. Two formats are supported:

* ``NNN_name.sql`` — executed with ``executescript``;
* ``NNN_name.py``  — must define ``up(conn)``.

Applied versions are recorded in ``schema_migrations``. Migrations are never edited after they
have been applied anywhere; add a new one instead.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def connect(path: str | Path = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def applied_versions(conn: sqlite3.Connection) -> set[str]:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    return {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}


def pending(conn: sqlite3.Connection, migrations_dir: Path = MIGRATIONS_DIR) -> list[Path]:
    done = applied_versions(conn)
    files = sorted(p for p in Path(migrations_dir).iterdir() if p.suffix in (".sql", ".py") and p.stem[:3].isdigit())
    return [p for p in files if p.stem not in done]


def migrate(conn: sqlite3.Connection, migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply pending migrations; returns the versions applied."""
    applied = []
    for path in pending(conn, migrations_dir):
        if path.suffix == ".sql":
            conn.executescript(path.read_text(encoding="utf-8"))
        else:
            spec = importlib.util.spec_from_file_location(f"migration_{path.stem}", path)
            mod = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(mod)
            mod.up(conn)
        conn.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                     (path.stem, datetime.now(timezone.utc).isoformat(timespec="seconds")))
        conn.commit()
        applied.append(path.stem)
    return applied


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
