# Operator CLI

`python -m acctsvc.cli [--db PATH] <command> [options]` — `--db` defaults to `data/accounts.db`.
Domain errors print `error: ...` and exit with code 2.

| Command | Arguments | Example |
|---|---|---|
| `migrate` | — | `python -m acctsvc.cli --db data/accounts.db migrate` |
| `create-user` | `EMAIL NAME` | `python -m acctsvc.cli create-user ada@example.com "Ada Lovelace"` |
| `create-org` | `NAME --owner USER_ID` | `python -m acctsvc.cli create-org "Acme" --owner 1` |
| `add-member` | `--org ID --user ID [--role ROLE] [--actor ID]` | `python -m acctsvc.cli add-member --org 1 --user 2 --role admin --actor 1` |
| `change-role` | `--org ID --user ID --role ROLE [--actor ID]` | `python -m acctsvc.cli change-role --org 1 --user 2 --role member --actor 1` |
| `subscribe` | `--org ID --plan PLAN --start YYYY-MM-DD` | `python -m acctsvc.cli subscribe --org 1 --plan team --start 2025-01-15` |
| `change-plan` | `--org ID --plan PLAN --on YYYY-MM-DD` | `python -m acctsvc.cli change-plan --org 1 --plan business --on 2025-02-05` |
| `invoice` | `--org ID [--tax-bp BASIS_POINTS]` | `python -m acctsvc.cli invoice --org 1 --tax-bp 2050` |
| `list-invoices` | `--org ID` | `python -m acctsvc.cli list-invoices --org 1` |

Roles: `owner`, `admin`, `billing_admin`, `member`. Plans: `free`, `team`, `business`.
`migrate` applies pending migrations; some (e.g. `005_drop_full_name`) are destructive — back up
the database first.
