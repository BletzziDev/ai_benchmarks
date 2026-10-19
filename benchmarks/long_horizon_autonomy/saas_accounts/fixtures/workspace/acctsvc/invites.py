"""Invitations: an owner/admin invites an email address; the invitee accepts with a token.

Only a SHA-256 hash of the token is stored. Tokens expire after ``INVITE_TTL`` and are single use.
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from acctsvc import audit, orgs, users
from acctsvc.errors import Conflict, Forbidden, NotFound
from acctsvc.permissions import require

INVITE_TTL = timedelta(days=7)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def invite(conn: sqlite3.Connection, org_id: int, email: str, role: str, invited_by: int,
           now: datetime | None = None) -> str:
    """Create an invitation and return the plaintext token (shown once, sent by email)."""
    now = now or datetime.now(timezone.utc)
    orgs.get_org(conn, org_id)
    require(conn, invited_by, org_id, "members.manage")
    if role not in orgs.ROLES:
        raise ValueError(f"unknown role {role!r}")
    if role == "owner":
        raise Forbidden("owners cannot be invited; promote an existing member instead")
    email = email.strip()
    pending = conn.execute(
        "SELECT 1 FROM invitations WHERE org_id = ? AND email = ? AND accepted_at IS NULL AND revoked_at IS NULL "
        "AND expires_at > ?", (org_id, email, now.isoformat())).fetchone()
    if pending:
        raise Conflict(f"{email} already has a pending invitation to org {org_id}")
    token = secrets.token_urlsafe(24)
    conn.execute(
        "INSERT INTO invitations(org_id, email, role, token_hash, invited_by, created_at, expires_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (org_id, email, role, _hash(token), invited_by, now.isoformat(), (now + INVITE_TTL).isoformat()))
    audit.record(conn, invited_by, "invitation.created", f"org:{org_id}", {"email": email, "role": role})
    return token


def accept(conn: sqlite3.Connection, token: str, full_name: str, now: datetime | None = None) -> int:
    """Accept an invitation; creates the user if needed and adds the membership. Returns user id."""
    now = now or datetime.now(timezone.utc)
    inv = conn.execute("SELECT * FROM invitations WHERE token_hash = ?", (_hash(token),)).fetchone()
    if inv is None or inv["revoked_at"] is not None:
        raise NotFound("invitation not found")
    if inv["accepted_at"] is not None:
        raise Conflict("invitation already used")
    if _parse(inv["expires_at"]) <= now:
        raise Forbidden("invitation expired")
    existing = users.get_user_by_email(conn, inv["email"])
    user_id = existing["id"] if existing else users.create_user(conn, inv["email"], full_name)
    orgs.add_member(conn, inv["org_id"], user_id, inv["role"])
    conn.execute("UPDATE invitations SET accepted_at = ? WHERE id = ?", (now.isoformat(), inv["id"]))
    return user_id


def revoke(conn: sqlite3.Connection, invitation_id: int, actor_id: int, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    inv = conn.execute("SELECT * FROM invitations WHERE id = ?", (invitation_id,)).fetchone()
    if inv is None:
        raise NotFound(f"invitation {invitation_id}")
    require(conn, actor_id, inv["org_id"], "members.manage")
    conn.execute("UPDATE invitations SET revoked_at = ? WHERE id = ?", (now.isoformat(), invitation_id))
    audit.record(conn, actor_id, "invitation.revoked", f"org:{inv['org_id']}", {"email": inv["email"]})


def pending_invitations(conn: sqlite3.Connection, org_id: int, now: datetime | None = None) -> list[sqlite3.Row]:
    now = now or datetime.now(timezone.utc)
    return list(conn.execute(
        "SELECT id, email, role, expires_at FROM invitations WHERE org_id = ? AND accepted_at IS NULL "
        "AND revoked_at IS NULL AND expires_at > ? ORDER BY id", (org_id, now.isoformat())))
