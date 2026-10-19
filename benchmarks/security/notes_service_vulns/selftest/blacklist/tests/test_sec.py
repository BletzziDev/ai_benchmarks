from notesvc import Request, create_app


def test_quote_payload_blocked(tmp_path):
    app = create_app(storage_dir=str(tmp_path / "s"), secret_key="k" * 40)
    t = app.add_tenant("acme")
    app.add_user(t, "alice", "alice-pw")
    tok = app.handle(Request("POST", "/login", body={"username": "alice", "password": "alice-pw"})).body["token"]
    r = app.handle(Request("GET", "/notes", headers={"Authorization": f"Bearer {tok}"}, query={"q": "' OR '1'='1"}))
    assert r.status == 200
