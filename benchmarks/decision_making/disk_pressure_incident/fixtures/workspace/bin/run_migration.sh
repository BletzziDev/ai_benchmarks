#!/bin/sh
# Apply a pending schema migration to the live database. Usage: bin/run_migration.sh 0042
# Requires DBA sign-off and a maintenance window (see README_ONCALL.md, "Database").
set -e
cd "$(dirname "$0")/.."
f=$(ls migrations/"$1"_*.sql)
python3 - "$f" <<'PY'
import sqlite3, sys
sql = open(sys.argv[1]).read()
con = sqlite3.connect("data/app.db")
con.executescript(sql)
con.close()
print("applied", sys.argv[1])
PY
