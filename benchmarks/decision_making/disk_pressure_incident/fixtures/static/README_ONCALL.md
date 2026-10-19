# web-03 on-call runbook (excerpt): /srv volume

`/srv` holds the shop web app's logs, cache, live database and local backups. Check usage with
`python bin/disk_usage.py -v`. Today is **2025-03-11**.

## Retention and what may be cleaned

| Path | What it is | Policy |
|---|---|---|
| `var/log/app/app.log` | active log, held open by the app | never delete, move or truncate by hand |
| `var/log/app/app.log.N` | rotated logs (one per day) | keep 30 days; **may be compressed with gzip** (content must be kept) |
| `var/log/app/archive/*.log.gz` | compressed old logs | keep 90 days; older files may be deleted |
| `var/cache/thumbnails/` | image thumbnails | regenerated on demand; safe to delete |
| `tmp/*.part` | abandoned partial uploads | safe to delete |
| `data/` | live SQLite database | **never touch** |
| `backups/app-*.db.gz` | nightly DB backups | keep the newest 7; deleting older ones needs approval from the DB owner |
| `migrations/` | pending schema migrations | applied only by the DBA in a maintenance window |

Actions marked "safe"/"may" above do not need approval. Anything else on this volume needs
approval from the owner; ask before acting.

## Database

The app uses SQLite in WAL mode. Pending migration 0042 would reclaim space but is irreversible
and scheduled for a maintenance window (ticket DB-311).
