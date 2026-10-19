"""Build data/accounts.db — the staging copy of production data — from data/staging_seed.sql.

Run from the repository root: ``python scripts/build_staging_db.py``. Refuses to overwrite an
existing database unless ``--force`` is given (the staging DB is shared with the support team).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from acctsvc import db  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data" / "accounts.db"))
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    out = Path(args.out)
    if out.exists() and not args.force:
        print(f"{out} exists; use --force to rebuild (this destroys its current contents)", file=sys.stderr)
        return 1
    if out.exists():
        out.unlink()
    out.parent.mkdir(parents=True, exist_ok=True)
    conn = db.connect(out)
    initial = [p for p in sorted((ROOT / "migrations").iterdir()) if p.stem[:3] in ("001", "002", "003")]
    for p in initial:
        conn.executescript(p.read_text())
        db.applied_versions(conn)
        conn.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (?, '2025-01-01T00:00:00+00:00')", (p.stem,))
    conn.executescript((ROOT / "data" / "staging_seed.sql").read_text())
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    print(f"built {out} with {n} users")
    return 0


if __name__ == "__main__":
    sys.exit(main())
