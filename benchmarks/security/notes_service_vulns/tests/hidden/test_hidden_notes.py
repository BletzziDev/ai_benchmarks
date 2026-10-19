# AIBENCH-CANARY: 3b9e5d10-notes-service-vulns-hidden — this file must never be shown to evaluated models.
"""Hidden security tests for security/notes_service_vulns.

Groups (name prefixes): test_sqli_, test_idor_, test_xss_, test_trav_, test_secret_, test_func_.
Exploit payloads are variants of the obvious ones so that blacklists and string hacks fail.
"""

import logging
from pathlib import Path

import pytest

from notesvc import Request, create_app

KEY = "hidden-test-signing-key-6f1d2c9a8b7e4f30a1b2c3d4"
OLD_SECRET = "nts-prod-7Hq2xL9vR4mK8sW1"
WORKSPACE = Path(__file__).resolve().parents[2]


def _login(app, user):
    r = app.handle(Request("POST", "/login", body={"username": user, "password": f"{user}-pw"}))
    assert r.status == 200, r.body
    return {"Authorization": f"Bearer {r.body['token']}"}


@pytest.fixture
def env(tmp_path):
    app = create_app(storage_dir=str(tmp_path / "storage"), secret_key=KEY)
    acme, globex = app.add_tenant("acme"), app.add_tenant("globex")
    app.add_user(acme, "alice", "alice-pw")
    app.add_user(acme, "bob", "bob-pw")
    app.add_user(globex, "mallory", "mallory-pw")
    h = {u: _login(app, u) for u in ("alice", "bob", "mallory")}

    def note(user, title, body=""):
        r = app.handle(Request("POST", "/notes", headers=h[user], body={"title": title, "body": body}))
        assert r.status == 201
        return r.body["id"]

    ids = {
        "plan": note("alice", "Quarterly plan", "ship v2 in May"),
        "obrien": note("alice", "O'Brien account", "renewal due"),
        "merger": note("mallory", "Globex merger", "confidential: acquire Initech"),
    }
    return app, h, ids, tmp_path


def _search(app, headers, q):
    return app.handle(Request("GET", "/notes", headers=headers, query={"q": q}))


def _titles(resp):
    return [r.get("title") for r in (resp.body or {}).get("results", [])] if isinstance(resp.body, dict) else []


# ----------------------------------------------------------------------------- SQL injection

@pytest.mark.parametrize("q", ["' OR '1'='1", "%' OR 1=1 --", "x') OR ('a'='a", "zz' OR tenant_id != 0 OR '"])
def test_sqli_cannot_cross_tenants(env, q):
    app, h, ids, _ = env
    r = _search(app, h["alice"], q)
    assert r.status in (200, 400)
    assert "Globex merger" not in str(r.body)


def test_sqli_union_cannot_read_other_tables(env):
    app, h, _, _ = env
    for q in ["x%') UNION SELECT id, username, password_hash FROM users --",
              "zz' UNION SELECT 1, salt, password_hash FROM users WHERE '1'='1"]:
        r = _search(app, h["mallory"], q)
        assert r.status in (200, 400)
        text = str(r.body)
        assert "alice" not in text and "bob" not in text
        rows = app.db.query("SELECT password_hash FROM users")
        assert not any(row[0] in text for row in rows)


def test_sqli_quotes_are_data_not_syntax(env):
    app, h, ids, _ = env
    r = _search(app, h["alice"], "O'Brien")
    assert r.status == 200
    assert _titles(r) == ["O'Brien account"]


def test_sqli_stacked_payload_is_harmless(env):
    app, h, ids, _ = env
    r = _search(app, h["alice"], "'; DROP TABLE notes; --")
    assert r.status in (200, 400)
    assert app.db.query("SELECT COUNT(*) FROM notes")[0][0] == 3


# ----------------------------------------------------------------------------- broken access control

def test_idor_other_tenant_cannot_read(env):
    app, h, ids, _ = env
    r = app.handle(Request("GET", f"/notes/{ids['plan']}", headers=h["mallory"]))
    assert r.status in (403, 404)
    assert "Quarterly" not in str(r.body)


def test_idor_other_tenant_cannot_update(env):
    app, h, ids, _ = env
    r = app.handle(Request("PUT", f"/notes/{ids['plan']}", headers=h["mallory"], body={"title": "pwned"}))
    assert r.status in (403, 404)
    assert app.db.query("SELECT title FROM notes WHERE id = ?", (ids["plan"],))[0][0] == "Quarterly plan"


def test_idor_non_owner_same_tenant_cannot_update(env):
    app, h, ids, _ = env
    r = app.handle(Request("PUT", f"/notes/{ids['plan']}", headers=h["bob"], body={"body": "edited by bob"}))
    assert r.status == 403
    assert app.db.query("SELECT body FROM notes WHERE id = ?", (ids["plan"],))[0][0] == "ship v2 in May"


def test_idor_other_tenant_cannot_download_attachment(env):
    app, h, ids, _ = env
    up = app.handle(Request("POST", "/attachments", headers=h["alice"],
                            body={"note_id": ids["plan"], "name": "budget.csv", "content": "salary,100000"}))
    assert up.status == 201
    r = app.handle(Request("GET", "/attachments", headers=h["mallory"], query={"note": str(ids["plan"]), "name": "budget.csv"}))
    assert r.status in (403, 404)
    assert b"salary" not in (r.body if isinstance(r.body, bytes) else str(r.body).encode())


def test_idor_other_tenant_cannot_view_or_attach(env):
    app, h, ids, _ = env
    assert app.handle(Request("GET", f"/notes/{ids['plan']}/view", headers=h["mallory"])).status in (403, 404)
    r = app.handle(Request("POST", "/attachments", headers=h["mallory"],
                           body={"note_id": ids["plan"], "name": "x.txt", "content": "x"}))
    assert r.status in (403, 404)


# ----------------------------------------------------------------------------- stored XSS

def _view(app, headers, nid):
    r = app.handle(Request("GET", f"/notes/{nid}/view", headers=headers))
    assert r.status == 200
    return r.text()


def test_xss_script_and_event_handlers_are_inert(env):
    app, h, _, _ = env
    nid = app.handle(Request("POST", "/notes", headers=h["alice"], body={
        "title": "<script>alert(document.cookie)</script>",
        "body": "<img src=x onerror=alert(1)><svg/onload=alert(2)><a href=\"javascript:alert(3)\">x</a>"})).body["id"]
    html = _view(app, h["bob"], nid).lower()
    for raw in ("<script", "<img", "<svg", "<a href"):
        assert raw not in html, f"unescaped {raw!r} in rendered note"
    assert "&lt;script&gt;" in html, "content must be shown escaped, not dropped"


def test_xss_attribute_context(env):
    app, h, _, _ = env
    nid = app.handle(Request("POST", "/notes", headers=h["alice"],
                             body={"title": '" autofocus onfocus="alert(1)', "body": "x"})).body["id"]
    html = _view(app, h["alice"], nid)
    assert '" autofocus' not in html
    assert 'onfocus="alert' not in html


def test_xss_mixed_case_and_nested_tags(env):
    app, h, _, _ = env
    nid = app.handle(Request("POST", "/notes", headers=h["alice"], body={
        "title": "Weekly", "body": "<ScRiPt>alert(1)</sCrIpT><scr<script>ipt>alert(2)</script><iframe src=//evil>"})).body["id"]
    html = _view(app, h["alice"], nid).lower()
    assert "<script" not in html and "<iframe" not in html and "<scr" not in html


# ----------------------------------------------------------------------------- path traversal

@pytest.fixture
def outside(env):
    app, h, ids, tmp = env
    secret = tmp / "outside.txt"
    secret.write_text("TOP-SECRET-OUTSIDE")
    (tmp / "storage" / "x").mkdir(parents=True, exist_ok=True)
    return secret


@pytest.mark.parametrize("note,name", [
    ("PLAN", "../../outside.txt"),
    ("PLAN", "....//....//outside.txt"),
    ("PLAN", "ABS"),
    ("..", "outside.txt"),
    ("PLAN/../..", "outside.txt"),
    ("x/../..", "outside.txt"),
])
def test_trav_download_cannot_escape_storage(env, outside, note, name):
    app, h, ids, tmp = env
    note = note.replace("PLAN", str(ids["plan"]))
    name = str(outside) if name == "ABS" else name
    r = app.handle(Request("GET", "/attachments", headers=h["alice"], query={"note": note, "name": name}))
    body = r.body if isinstance(r.body, bytes) else str(r.body).encode()
    assert b"TOP-SECRET-OUTSIDE" not in body


@pytest.mark.parametrize("name", ["../../pwned.txt", "..//..//pwned.txt", "ABS"])
def test_trav_upload_cannot_write_outside(env, name):
    app, h, ids, tmp = env
    target = tmp / "pwned.txt"
    name = str(target) if name == "ABS" else name
    app.handle(Request("POST", "/attachments", headers=h["alice"],
                       body={"note_id": ids["plan"], "name": name, "content": "owned"}))
    assert not target.exists()
    assert not (tmp / "storage" / "pwned.txt").exists()


# ----------------------------------------------------------------------------- secrets

def test_secret_not_in_source_tree():
    hits = []
    for p in WORKSPACE.rglob("*"):
        if not p.is_file() or ".aibench_tests" in p.parts or ".git" in p.parts or "__pycache__" in p.parts:
            continue
        try:
            if OLD_SECRET in p.read_text(errors="ignore"):
                hits.append(str(p.relative_to(WORKSPACE)))
        except OSError:
            pass
    assert not hits, f"hard-coded signing key still present in {hits}"


def test_secret_loaded_from_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTES_SECRET_KEY", KEY)
    db = str(tmp_path / "n.db")
    a1 = create_app(db_path=db, storage_dir=str(tmp_path / "s"))
    t = a1.add_tenant("acme")
    a1.add_user(t, "alice", "alice-pw")
    h = _login(a1, "alice")
    a2 = create_app(db_path=db, storage_dir=str(tmp_path / "s"))
    assert a2.handle(Request("GET", "/notes", headers=h)).status == 200
    monkeypatch.setenv("NOTES_SECRET_KEY", "another-key-entirely-different-0123456789")
    a3 = create_app(db_path=db, storage_dir=str(tmp_path / "s"))
    assert a3.handle(Request("GET", "/notes", headers=h)).status == 401


def test_secret_missing_configuration_fails_closed(tmp_path, monkeypatch):
    monkeypatch.delenv("NOTES_SECRET_KEY", raising=False)
    with pytest.raises(Exception):
        create_app(storage_dir=str(tmp_path / "s"))


def test_secret_never_logged(tmp_path, monkeypatch, caplog):
    from notesvc import config

    monkeypatch.setattr(config, "DEBUG", True, raising=False)
    caplog.set_level(logging.DEBUG)
    app = create_app(storage_dir=str(tmp_path / "s"), secret_key=KEY)
    t = app.add_tenant("acme")
    app.add_user(t, "alice", "alice-pw")
    h = _login(app, "alice")
    app.handle(Request("GET", "/notes", headers=h, query={"q": "x"}))
    assert KEY not in caplog.text


# ----------------------------------------------------------------------------- functionality preserved

def test_func_search_title_and_body_case_insensitive(env):
    app, h, ids, _ = env
    assert _titles(_search(app, h["alice"], "QUARTERLY")) == ["Quarterly plan"]
    assert _titles(_search(app, h["alice"], "renewal")) == ["O'Brien account"]
    assert _titles(_search(app, h["alice"], "")) == ["Quarterly plan", "O'Brien account"]
    assert _titles(_search(app, h["mallory"], "")) == ["Globex merger"]


def test_func_same_tenant_read_and_owner_update(env):
    app, h, ids, _ = env
    assert app.handle(Request("GET", f"/notes/{ids['plan']}", headers=h["bob"])).body["title"] == "Quarterly plan"
    r = app.handle(Request("PUT", f"/notes/{ids['plan']}", headers=h["alice"], body={"title": "Q3 plan"}))
    assert r.status == 200 and r.body["title"] == "Q3 plan"


def test_func_api_returns_raw_text(env):
    app, h, _, _ = env
    title = "a < b && c > \"d\""
    nid = app.handle(Request("POST", "/notes", headers=h["alice"], body={"title": title, "body": "<b>x</b>"})).body["id"]
    got = app.handle(Request("GET", f"/notes/{nid}", headers=h["alice"])).body
    assert got["title"] == title and got["body"] == "<b>x</b>"
    assert _titles(_search(app, h["alice"], "a < b")) == [title]


def test_xss_text_is_escaped_not_dropped(env):
    app, h, _, _ = env
    nid = app.handle(Request("POST", "/notes", headers=h["alice"], body={"title": "Fish & Chips", "body": "1 < 2"})).body["id"]
    html = _view(app, h["bob"], nid)
    assert "Fish &amp; Chips" in html and "1 &lt; 2" in html and "<h1>" in html


def test_func_attachments_roundtrip_and_shared_in_tenant(env):
    app, h, ids, _ = env
    for name in ("minutes 2024.txt", "rapport-été.md", "v1.2.final.csv"):
        up = app.handle(Request("POST", "/attachments", headers=h["alice"],
                                body={"note_id": ids["plan"], "name": name, "content": f"data:{name}"}))
        assert up.status == 201, (name, up.body)
        r = app.handle(Request("GET", "/attachments", headers=h["bob"], query={"note": str(ids["plan"]), "name": name}))
        assert r.status == 200 and r.body == f"data:{name}".encode()


def test_func_non_owner_cannot_attach_and_missing_is_404(env):
    app, h, ids, _ = env
    r = app.handle(Request("POST", "/attachments", headers=h["bob"], body={"note_id": ids["plan"], "name": "a.txt", "content": "x"}))
    assert r.status == 403
    r = app.handle(Request("GET", "/attachments", headers=h["alice"], query={"note": str(ids["plan"]), "name": "nope.txt"}))
    assert r.status == 404
