import pytest

from acctsvc import audit, orgs, users
from acctsvc.errors import Conflict, Forbidden, LastOwnerError, NotFound


def _user(conn, n):
    return users.create_user(conn, f"user{n}@example.com", f"User {n}")


def test_create_org_makes_owner(conn, org):
    assert orgs.owners(conn, org["id"]) == [org["owner"]]
    assert audit.entries(conn, action="org.created")[0]["target"] == f"org:{org['id']}"


def test_add_member_and_duplicate(conn, org):
    u = _user(conn, 1)
    orgs.add_member(conn, org["id"], u, "admin", actor_id=org["owner"])
    assert [(m["user_id"], m["role"]) for m in orgs.members(conn, org["id"])] == [(org["owner"], "owner"), (u, "admin")]
    with pytest.raises(Conflict):
        orgs.add_member(conn, org["id"], u)


def test_member_cannot_add_members(conn, org):
    a, b = _user(conn, 1), _user(conn, 2)
    orgs.add_member(conn, org["id"], a, "member")
    with pytest.raises(Forbidden):
        orgs.add_member(conn, org["id"], b, actor_id=a)


def test_cannot_demote_last_owner(conn, org):
    with pytest.raises(LastOwnerError):
        orgs.change_role(conn, org["id"], org["owner"], "admin")


def test_demote_owner_when_another_owner_exists(conn, org):
    u = _user(conn, 1)
    orgs.add_member(conn, org["id"], u, "owner")
    orgs.change_role(conn, org["id"], org["owner"], "member")
    assert orgs.owners(conn, org["id"]) == [u]


def test_remove_member(conn, org):
    u = _user(conn, 1)
    orgs.add_member(conn, org["id"], u)
    orgs.remove_member(conn, org["id"], u, actor_id=org["owner"])
    assert orgs.member_count(conn, org["id"]) == 1
    with pytest.raises(NotFound):
        orgs.remove_member(conn, org["id"], u)


def test_delete_org_by_owner(conn, org):
    orgs.delete_org(conn, org["id"], actor_id=org["owner"])
    assert orgs.get_org(conn, org["id"])["deleted_at"] is not None
