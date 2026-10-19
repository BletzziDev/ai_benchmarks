# acctsvc

Account management core for the Northwind SaaS platform (users, organisations, roles,
subscriptions, invoices, audit log). Python 3.11+, standard library only.

```bash
python -m pytest -q                                   # tests
python scripts/build_staging_db.py                    # (re)build the staging DB (refuses to overwrite)
python -m acctsvc.cli --db data/accounts.db migrate   # apply pending migrations
```

Docs: `docs/ARCHITECTURE.md`, `docs/BILLING.md`, `docs/CONTRIBUTING.md`. Work items: `BACKLOG.md`.
