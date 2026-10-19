import pytest

from acctsvc import db, orgs, users


@pytest.fixture
def conn():
    c = db.connect()
    db.migrate(c)
    yield c
    c.close()


@pytest.fixture
def org(conn):
    """An organisation with an owner (id returned in the dict) and helpers."""
    owner = users.create_user(conn, "owner@example.com", "Olive Owner")
    org_id = orgs.create_org(conn, "Example Org", owner)
    return {"id": org_id, "owner": owner}
