import pytest

from acctsvc import users
from acctsvc.errors import Conflict, NotFound


def test_create_and_get(conn):
    uid = users.create_user(conn, "ada@example.com", "Ada  Lovelace")
    u = users.get_user(conn, uid)
    assert u["email"] == "ada@example.com"
    assert users.display_name(conn, uid) == "Ada Lovelace"


def test_duplicate_email_conflict(conn):
    users.create_user(conn, "ada@example.com", "Ada Lovelace")
    with pytest.raises(Conflict):
        users.create_user(conn, "ada@example.com", "Ada L.")


def test_invalid_email_and_name(conn):
    with pytest.raises(ValueError):
        users.create_user(conn, "not-an-email", "X")
    with pytest.raises(ValueError):
        users.create_user(conn, "x@example.com", "   ")


def test_lookup_by_email(conn):
    uid = users.create_user(conn, "grace@example.com", "Grace Hopper")
    assert users.get_user_by_email(conn, "grace@example.com")["id"] == uid
    assert users.get_user_by_email(conn, "nobody@example.com") is None


def test_deactivate(conn):
    uid = users.create_user(conn, "alan@example.com", "Alan Turing")
    users.deactivate_user(conn, uid)
    assert [u["id"] for u in users.list_users(conn)] == []
    assert [u["id"] for u in users.list_users(conn, active_only=False)] == [uid]
    with pytest.raises(NotFound):
        users.deactivate_user(conn, 999)
