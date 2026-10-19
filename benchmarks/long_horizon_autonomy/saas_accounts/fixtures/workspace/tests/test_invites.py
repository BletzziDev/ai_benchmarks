from datetime import datetime, timedelta, timezone

import pytest

from acctsvc import invites, orgs, users
from acctsvc.errors import Conflict, Forbidden, NotFound

T0 = datetime(2025, 3, 1, 12, 0, tzinfo=timezone.utc)


def test_invite_and_accept_new_user(conn, org):
    token = invites.invite(conn, org["id"], "new@example.com", "member", org["owner"], now=T0)
    uid = invites.accept(conn, token, "New Person", now=T0 + timedelta(days=1))
    assert users.get_user(conn, uid)["email"] == "new@example.com"
    assert next(m["role"] for m in orgs.members(conn, org["id"]) if m["user_id"] == uid) == "member"
    with pytest.raises(Conflict):
        invites.accept(conn, token, "New Person", now=T0 + timedelta(days=2))


def test_expired_and_revoked(conn, org):
    t1 = invites.invite(conn, org["id"], "late@example.com", "member", org["owner"], now=T0)
    with pytest.raises(Forbidden):
        invites.accept(conn, t1, "Late", now=T0 + timedelta(days=8))
    t2 = invites.invite(conn, org["id"], "rev@example.com", "admin", org["owner"], now=T0)
    inv_id = invites.pending_invitations(conn, org["id"], now=T0)[-1]["id"]
    invites.revoke(conn, inv_id, org["owner"], now=T0)
    with pytest.raises(NotFound):
        invites.accept(conn, t2, "Rev", now=T0)


def test_no_owner_invites_and_no_duplicates(conn, org):
    with pytest.raises(Forbidden):
        invites.invite(conn, org["id"], "boss@example.com", "owner", org["owner"], now=T0)
    invites.invite(conn, org["id"], "dup@example.com", "member", org["owner"], now=T0)
    with pytest.raises(Conflict):
        invites.invite(conn, org["id"], "dup@example.com", "member", org["owner"], now=T0)


def test_member_cannot_invite(conn, org):
    m = users.create_user(conn, "m@example.com", "Mem Ber")
    orgs.add_member(conn, org["id"], m)
    with pytest.raises(Forbidden):
        invites.invite(conn, org["id"], "x@example.com", "member", m, now=T0)
