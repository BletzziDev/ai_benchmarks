# accounts-api — operational context

- **Database:** PostgreSQL 15, primary + 2 streaming replicas. Table `users`: ~40 million rows,
  ~3 000 writes/s at peak (sign-ups and profile edits), ~25 000 reads/s.
- **Deploys:** rolling deploys over 20 pods take ~15 minutes. During a rollout the old and the new
  app version serve traffic **at the same time** and share the same database.
- **Release train:** at most 3 application releases are available for this migration this quarter.
- **SLOs:** no downtime and no maintenance window; p99 write latency < 150 ms. Statements that
  hold an `ACCESS EXCLUSIVE` lock on `users` for more than a second, or `UPDATE`s touching more
  than ~50 000 rows in one transaction (lock contention, replica lag), violate the SLO.
- **Rollback policy:** until the migration's declared point of no return, on-call must be able to
  roll back to v1 by re-deploying previous releases (newest first). Schema additions do not need to
  be undone to roll back.
- **Current app (v1):** reads and writes `users.name` only (see `app_v1_users_repo.py`).

## Product requirement (ticket ACC-731)

Replace `users.name` by `users.first_name` and `users.last_name` (localisation, legal-name
handling, sorting by last name). At the end of the migration the application must read and write
only the new columns, `users.name` must be gone, and every row must have correct values in the new
columns. How existing names are split must be decided and documented (see the examples below).

| name today | notes |
|---|---|
| `Ada Lovelace` | simple case |
| `Gabriel García Márquez` | compound family name |
| `Prince` | single name |
| `  Grace   Hopper ` | stray whitespace |
| `李小龙` | no spaces, family name first |
