import pytest

from notesvc import Request, create_app


@pytest.fixture
def app(tmp_path):
    a = create_app(storage_dir=str(tmp_path / "storage"), secret_key="test-signing-key-0123456789abcdef")
    acme = a.add_tenant("acme")
    globex = a.add_tenant("globex")
    a.add_user(acme, "alice", "alice-pw")
    a.add_user(acme, "bob", "bob-pw")
    a.add_user(globex, "mallory", "mallory-pw")
    return a


def login(app, user):
    r = app.handle(Request("POST", "/login", body={"username": user, "password": f"{user}-pw"}))
    assert r.status == 200
    return {"Authorization": f"Bearer {r.body['token']}"}


def test_login_rejects_bad_password(app):
    r = app.handle(Request("POST", "/login", body={"username": "alice", "password": "nope"}))
    assert r.status == 401


def test_requires_auth(app):
    assert app.handle(Request("GET", "/notes")).status == 401


def test_create_get_and_search(app):
    h = login(app, "alice")
    n = app.handle(Request("POST", "/notes", headers=h, body={"title": "Quarterly plan", "body": "ship v2"})).body
    assert app.handle(Request("GET", f"/notes/{n['id']}", headers=h)).body["title"] == "Quarterly plan"
    res = app.handle(Request("GET", "/notes", headers=h, query={"q": "quarterly"})).body["results"]
    assert [r["id"] for r in res] == [n["id"]]


def test_same_tenant_can_read(app):
    n = app.handle(Request("POST", "/notes", headers=login(app, "alice"), body={"title": "Team", "body": "x"})).body
    assert app.handle(Request("GET", f"/notes/{n['id']}", headers=login(app, "bob"))).status == 200


def test_owner_can_update(app):
    h = login(app, "alice")
    n = app.handle(Request("POST", "/notes", headers=h, body={"title": "Draft", "body": "a"})).body
    r = app.handle(Request("PUT", f"/notes/{n['id']}", headers=h, body={"body": "b"}))
    assert r.status == 200 and r.body["body"] == "b"


def test_view_renders_html(app):
    h = login(app, "alice")
    n = app.handle(Request("POST", "/notes", headers=h, body={"title": "Hello", "body": "World"})).body
    r = app.handle(Request("GET", f"/notes/{n['id']}/view", headers=h))
    assert r.status == 200 and "<h1>Hello</h1>" in r.text() and "World" in r.text()


def test_attachments_roundtrip(app):
    h = login(app, "alice")
    n = app.handle(Request("POST", "/notes", headers=h, body={"title": "With file", "body": ""})).body
    up = app.handle(Request("POST", "/attachments", headers=h, body={"note_id": n["id"], "name": "minutes.txt", "content": "hi"}))
    assert up.status == 201
    r = app.handle(Request("GET", "/attachments", headers=login(app, "bob"), query={"note": str(n["id"]), "name": "minutes.txt"}))
    assert r.status == 200 and r.body == b"hi"
