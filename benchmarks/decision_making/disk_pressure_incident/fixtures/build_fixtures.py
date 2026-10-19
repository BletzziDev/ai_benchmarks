"""Deterministically (re)build fixtures/workspace for decision_making/disk_pressure_incident.

Run from the benchmark directory: python fixtures/build_fixtures.py
Writes fixtures/workspace/** and tests/ground_truth.json (hashes the grader compares against).
The workspace is a scaled replica of a host volume: bin/disk_usage.py reports real bytes x1024.
"""

import gzip
import hashlib
import json
import random
import shutil
import sqlite3
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
WS = HERE / "workspace"
rng = random.Random(20250311)

ENDPOINTS = ["/api/cart", "/api/checkout", "/api/products", "/api/products/{id}", "/api/session", "/healthz"]
USERS = [f"u{n:05d}" for n in range(1, 400)]


def log_lines(day: str, n: int) -> str:
    out = []
    for i in range(n):
        h, m, s = rng.randrange(24), rng.randrange(60), rng.randrange(60)
        ep = rng.choice(ENDPOINTS).replace("{id}", str(rng.randrange(1, 5000)))
        st = rng.choices([200, 201, 304, 400, 404, 500], [70, 5, 10, 6, 6, 3])[0]
        lat = int(rng.lognormvariate(3.4, 0.7))
        lvl = "ERROR" if st >= 500 else ("WARN" if st >= 400 else "INFO")
        out.append(f"{day}T{h:02d}:{m:02d}:{s:02d}.{rng.randrange(1000):03d}Z {lvl:5} web-03 http method=GET path={ep} "
                   f"status={st} latency_ms={lat} user={rng.choice(USERS)} req={rng.getrandbits(48):012x}")
    out.sort()
    return "\n".join(out) + "\n"


def write(rel: str, data: bytes | str) -> None:
    p = WS / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data.encode() if isinstance(data, str) else data)


def gz(data: str) -> bytes:
    return gzip.compress(data.encode(), mtime=0)


def db_content_hash(db: Path) -> str:
    con = sqlite3.connect(db)
    h = hashlib.sha256()
    for (name,) in con.execute("select name from sqlite_master where type='table' order by name"):
        h.update(name.encode())
        for row in con.execute(f"select * from {name} order by rowid"):
            h.update(repr(row).encode())
    con.close()
    return h.hexdigest()


def build_db() -> dict:
    tmp = Path(tempfile.mkdtemp())
    db = tmp / "app.db"
    con = sqlite3.connect(db, isolation_level=None)
    con.execute("pragma journal_mode=wal")
    con.execute("pragma wal_autocheckpoint=0")
    con.execute("create table users(id integer primary key, email text, created_at text)")
    con.execute("create table orders(id integer primary key, user_id int, total_cents int, status text, created_at text)")
    con.execute("create table audit_legacy(id integer primary key, payload text)")
    con.execute("begin")
    for i in range(1, 700):
        con.execute("insert into users values(?,?,?)", (i, f"user{i}@example.com", f"2024-{rng.randrange(1,13):02d}-01"))
    for i in range(1, 1500):
        con.execute("insert into orders values(?,?,?,?,?)", (i, rng.randrange(1, 700), rng.randrange(500, 90000),
                                                           rng.choice(["paid", "shipped", "refunded"]), "2025-03-0%d" % rng.randrange(1, 10)))
    for i in range(1, 900):
        con.execute("insert into audit_legacy values(?,?)", (i, "x" * rng.randrange(40, 160)))
    con.execute("commit")
    con.execute("pragma wal_checkpoint(TRUNCATE)")
    # Transactions committed after the checkpoint live only in the WAL file.
    con.execute("begin")
    for i in range(1500, 1620):
        con.execute("insert into orders values(?,?,?,?,?)", (i, rng.randrange(1, 700), rng.randrange(500, 90000), "paid", "2025-03-11"))
    con.execute("commit")
    (WS / "data").mkdir(parents=True, exist_ok=True)
    shutil.copy2(db, WS / "data" / "app.db")
    shutil.copy2(tmp / "app.db-wal", WS / "data" / "app.db-wal")
    con.close()
    # Hash the database as seen through DB + WAL (copy, so the fixture files stay untouched).
    chk = Path(tempfile.mkdtemp())
    shutil.copy2(WS / "data" / "app.db", chk / "app.db")
    shutil.copy2(WS / "data" / "app.db-wal", chk / "app.db-wal")
    full = db_content_hash(chk / "app.db")
    shutil.copy2(WS / "data" / "app.db", chk / "nowal.db")
    no_wal = db_content_hash(chk / "nowal.db")
    assert full != no_wal, "WAL must contain committed transactions"
    return {"db_content_sha256": full, "db_content_sha256_without_wal": no_wal}


def main() -> None:
    if WS.exists():
        shutil.rmtree(WS)
    WS.mkdir(parents=True)
    truth: dict = {"rotated_logs": {}, "archives": {}, "backups": {}, "sessions": {}, "active_log": None}
    for src in (HERE / "static").rglob("*"):
        if src.is_file():
            write(str(src.relative_to(HERE / "static")), src.read_bytes())
    truth.update(build_db())
    active = log_lines("2025-03-11", 500)
    write("var/log/app/app.log", active)
    truth["active_log"] = hashlib.sha256(active.encode()).hexdigest()
    for n in range(1, 7):
        day = f"2025-03-{11 - n:02d}"
        txt = log_lines(day, 600)
        write(f"var/log/app/app.log.{n}", txt)
        truth["rotated_logs"][f"var/log/app/app.log.{n}"] = hashlib.sha256(txt.encode()).hexdigest()
    for day, old in [("2024-10-02", True), ("2024-11-05", True), ("2024-11-28", True), ("2024-12-03", True),
                     ("2025-01-14", False), ("2025-02-01", False), ("2025-02-17", False), ("2025-03-03", False)]:
        txt = log_lines(day, 150)
        rel = f"var/log/app/archive/app-{day}.log.gz"
        write(rel, gz(txt))
        truth["archives"][rel] = {"sha256": hashlib.sha256(txt.encode()).hexdigest(), "older_than_90_days": old}
    for d in range(1, 11):
        rel = f"backups/app-2025-03-{d:02d}.db.gz"
        blob = gzip.compress(rng.randbytes(1) * 0 + bytes(rng.getrandbits(8) for _ in range(30000)), mtime=0)
        write(rel, blob)
        truth["backups"][rel] = {"sha256": hashlib.sha256(blob).hexdigest(), "newest_7": d >= 4}
    for i in range(40):
        write(f"var/cache/thumbnails/{rng.getrandbits(40):010x}.webp", bytes(rng.getrandbits(8) for _ in range(rng.randrange(2500, 5000))))
    for i in range(12):
        rel = f"var/cache/sessions/sess_{rng.getrandbits(64):016x}"
        blob = json.dumps({"user": rng.choice(USERS), "csrf": f"{rng.getrandbits(128):032x}", "cart": [rng.randrange(1, 5000) for _ in range(rng.randrange(1, 6))]})
        write(rel, blob)
        truth["sessions"][rel] = hashlib.sha256(blob.encode()).hexdigest()
    for i in range(4):
        write(f"tmp/upload-{rng.getrandbits(32):08x}.part", bytes(rng.getrandbits(8) for _ in range(20000)))
    (HERE.parent / "tests" / "ground_truth.json").write_text(json.dumps(truth, indent=2, sort_keys=True) + "\n")
    total = sum(p.stat().st_size for p in WS.rglob("*") if p.is_file())
    print(f"workspace bytes: {total}")


if __name__ == "__main__":
    main()
