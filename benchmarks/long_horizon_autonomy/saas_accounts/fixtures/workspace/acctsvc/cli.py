"""Operator CLI: ``python -m acctsvc.cli --db data/accounts.db <command> ...``"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from acctsvc import db, invoices, orgs, subscriptions, users
from acctsvc.errors import AccountError


def _cmd_migrate(conn, args) -> int:
    applied = db.migrate(conn)
    print("applied: " + (", ".join(applied) if applied else "nothing (up to date)"))
    return 0


def _cmd_create_user(conn, args) -> int:
    uid = users.create_user(conn, args.email, args.name)
    conn.commit()
    print(uid)
    return 0


def _cmd_create_org(conn, args) -> int:
    oid = orgs.create_org(conn, args.name, args.owner)
    conn.commit()
    print(oid)
    return 0


def _cmd_add_member(conn, args) -> int:
    orgs.add_member(conn, args.org, args.user, args.role, actor_id=args.actor)
    conn.commit()
    return 0


def _cmd_change_role(conn, args) -> int:
    orgs.change_role(conn, args.org, args.user, args.role, actor_id=args.actor)
    conn.commit()
    return 0


def _cmd_subscribe(conn, args) -> int:
    subscriptions.subscribe(conn, args.org, args.plan, date.fromisoformat(args.start))
    conn.commit()
    return 0


def _cmd_change_plan(conn, args) -> int:
    amount = subscriptions.change_plan(conn, args.org, args.plan, date.fromisoformat(args.on))
    conn.commit()
    print(f"proration: {amount / 100:.2f}")
    return 0


def _cmd_invoice(conn, args) -> int:
    inv_id = invoices.generate_invoice(conn, args.org, tax_rate_bp=args.tax_bp)
    conn.commit()
    inv = invoices.get_invoice(conn, inv_id)
    print(f"{inv['number']} total {inv['total_cents'] / 100:.2f}")
    return 0


def _cmd_list_invoices(conn, args) -> int:
    rows = invoices.list_invoices(conn, args.org)
    width = max(len(r["number"]) for r in rows)
    print(f"{'NUMBER'.ljust(width)}  PERIOD                     TOTAL")
    for r in rows:
        print(f"{r['number'].ljust(width)}  {r['period_start']} - {r['period_end']}  {r['total_cents'] / 100:>9.2f}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="acctsvc")
    p.add_argument("--db", default="data/accounts.db")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate").set_defaults(fn=_cmd_migrate)
    s = sub.add_parser("create-user")
    s.add_argument("email")
    s.add_argument("name")
    s.set_defaults(fn=_cmd_create_user)
    s = sub.add_parser("create-org")
    s.add_argument("name")
    s.add_argument("--owner", type=int, required=True)
    s.set_defaults(fn=_cmd_create_org)
    s = sub.add_parser("add-member")
    s.add_argument("--org", type=int, required=True)
    s.add_argument("--user", type=int, required=True)
    s.add_argument("--role", default="member")
    s.add_argument("--actor", type=int)
    s.set_defaults(fn=_cmd_add_member)
    s = sub.add_parser("change-role")
    s.add_argument("--org", type=int, required=True)
    s.add_argument("--user", type=int, required=True)
    s.add_argument("--role", required=True)
    s.add_argument("--actor", type=int)
    s.set_defaults(fn=_cmd_change_role)
    s = sub.add_parser("subscribe")
    s.add_argument("--org", type=int, required=True)
    s.add_argument("--plan", required=True)
    s.add_argument("--start", required=True)
    s.set_defaults(fn=_cmd_subscribe)
    s = sub.add_parser("change-plan")
    s.add_argument("--org", type=int, required=True)
    s.add_argument("--plan", required=True)
    s.add_argument("--on", required=True)
    s.set_defaults(fn=_cmd_change_plan)
    s = sub.add_parser("invoice")
    s.add_argument("--org", type=int, required=True)
    s.add_argument("--tax-bp", type=int, default=0)
    s.set_defaults(fn=_cmd_invoice)
    s = sub.add_parser("list-invoices")
    s.add_argument("--org", type=int, required=True)
    s.set_defaults(fn=_cmd_list_invoices)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    conn = db.connect(args.db)
    try:
        return args.fn(conn, args)
    except AccountError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
