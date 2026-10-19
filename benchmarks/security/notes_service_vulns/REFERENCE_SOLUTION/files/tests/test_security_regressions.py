"""Regression tests for the security review (SQLi, access control, XSS, traversal, secrets)."""

import logging

import pytest

from notesvc import Request, create_app

KEY = "regression-signing-key-0123456789abcdef0123"


def login(app, user):
    r = app.handle(Request("POST", "/login", body={"username": user, "password": f"{user}-pw"}))
    return {"Authorization": f"Bearer {r.body['token']}"}


@pytest.fixture
def app(tmp_path):
    a = create_app(storage_dir=str(tmp_path / "storage"), secret_key=KEY)
    acme, globex = a.add_tenant("acme"), a.add_tenant("globex")
    a.add_user(acme, "alice", "alice-pw")
    a.add_user(acme, "bob", "bob-pw")
    a.add_user(globex, "mallory", "mallory-pw")
    return a


def note(app, user, title, body=""):
    return app.handle(Request("POST", "/notes", headers=login(app, user), body={"title": title, "body": body})).body["id"]


def test_search_injection_does_not_cross_tenants(app):
    note(app, "mallory", "Globex secret")
    r = app.handle(Request("GET", "/notes", headers=login(app, "alice"), query={"q": "' OR '1'='1"}))
    assert "Globex secret" not in str(r.body)


def test_search_with_apostrophe(app):
    note(app, "alice", "O'Brien")
    r = app.handle(Request("GET", "/notes", headers=login(app, "alice"), query={"q": "O'Brien"}))
    assert [x["title"] for x in r.body["results"]] == ["O'Brien"]


def test_cross_tenant_read_and_update_denied(app):
    nid = note(app, "alice", "Plan")
    m = login(app, "mallory")
    assert app.handle(Request("GET", f"/notes/{nid}", headers=m)).status == 404
    assert app.handle(Request("PUT", f"/notes/{nid}", headers=m, body={"title": "x"})).status == 404


def test_non_owner_update_denied(app):
    nid = note(app, "alice", "Plan")
    assert app.handle(Request("PUT", f"/notes/{nid}", headers=login(app, "bob"), body={"title": "x"})).status == 403


def test_view_escapes_html(app):
    nid = note(app, "alice", '"><script>alert(1)</script>', "<img src=x onerror=alert(1)>")
    html = app.handle(Request("GET", f"/notes/{nid}/view", headers=login(app, "alice"))).text()
    assert "<script" not in html and "<img" not in html


def test_attachment_traversal_rejected(app, tmp_path):
    (tmp_path / "outside.txt").write_text("secret")
    nid = note(app, "alice", "Files")
    h = login(app, "alice")
    r = app.handle(Request("GET", "/attachments", headers=h, query={"note": "..", "name": "outside.txt"}))
    assert r.status == 404
    app.handle(Request("POST", "/attachments", headers=h, body={"note_id": nid, "name": "../../evil.txt", "content": "x"}))
    assert not (tmp_path / "evil.txt").exists()


def test_cross_tenant_attachment_denied(app):
    nid = note(app, "alice", "Files")
    app.handle(Request("POST", "/attachments", headers=login(app, "alice"), body={"note_id": nid, "name": "a.txt", "content": "x"}))
    r = app.handle(Request("GET", "/attachments", headers=login(app, "mallory"), query={"note": str(nid), "name": "a.txt"}))
    assert r.status == 404


def test_secret_key_required_from_env(tmp_path, monkeypatch):
    monkeypatch.delenv("NOTES_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        create_app(storage_dir=str(tmp_path / "s"))


def test_signing_key_not_logged(app, caplog):
    caplog.set_level(logging.DEBUG)
    login(app, "alice")
    assert KEY not in caplog.text
