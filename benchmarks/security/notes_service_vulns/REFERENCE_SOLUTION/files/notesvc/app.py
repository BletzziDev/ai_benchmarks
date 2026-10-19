"""HTTP-like routing and handlers.

Access policy (product requirements):
  * every user belongs to exactly one tenant; data never crosses tenants;
  * any user may read and search the notes of their own tenant;
  * only a note's owner may update it or add attachments to it;
  * attachments are stored under ``storage_dir/<note_id>/`` and served only to users of the
    note's tenant.
"""

from __future__ import annotations

import html
import logging
import os
import re
from pathlib import Path

from notesvc import config
from notesvc.auth import TokenSigner, hash_password, verify_password
from notesvc.db import Database
from notesvc.http import Request, Response

log = logging.getLogger("notesvc")

NOTE_RE = re.compile(r"^/notes/(\d+)$")
VIEW_RE = re.compile(r"^/notes/(\d+)/view$")


class NotesApp:
    def __init__(self, db: Database, storage_dir: str, secret_key: str):
        self.db = db
        self.storage_dir = storage_dir
        self.signer = TokenSigner(secret_key)
        os.makedirs(storage_dir, exist_ok=True)

    # ------------------------------------------------------------------ admin helpers
    def add_tenant(self, name: str) -> int:
        return self.db.execute("INSERT INTO tenants (name) VALUES (?)", (name,)).lastrowid

    def add_user(self, tenant_id: int, username: str, password: str) -> int:
        h, salt = hash_password(password)
        return self.db.execute(
            "INSERT INTO users (tenant_id, username, password_hash, salt) VALUES (?, ?, ?, ?)",
            (tenant_id, username, h, salt),
        ).lastrowid

    # ------------------------------------------------------------------ dispatch
    def handle(self, req: Request) -> Response:
        try:
            if req.method == "POST" and req.path == "/login":
                return self.login(req)
            user = self._authenticate(req)
            if user is None:
                return Response.error(401, "authentication required")
            if req.method == "GET" and req.path == "/notes":
                return self.search_notes(req, user)
            if req.method == "POST" and req.path == "/notes":
                return self.create_note(req, user)
            m = NOTE_RE.match(req.path)
            if m and req.method == "GET":
                return self.get_note(int(m.group(1)), user)
            if m and req.method == "PUT":
                return self.update_note(int(m.group(1)), req, user)
            m = VIEW_RE.match(req.path)
            if m and req.method == "GET":
                return self.view_note(int(m.group(1)), user)
            if req.path == "/attachments" and req.method == "POST":
                return self.upload_attachment(req, user)
            if req.path == "/attachments" and req.method == "GET":
                return self.download_attachment(req, user)
            return Response.error(404, "not found")
        except Exception as e:  # pragma: no cover - defensive
            log.exception("unhandled error")
            return Response.error(500, f"internal error: {e}")

    def _authenticate(self, req: Request) -> dict | None:
        auth = req.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        payload = self.signer.verify(auth[len("Bearer "):])
        if payload is None:
            return None
        rows = self.db.query("SELECT id, tenant_id, username FROM users WHERE id = ?", (payload["uid"],))
        return dict(rows[0]) if rows else None

    # ------------------------------------------------------------------ handlers
    def login(self, req: Request) -> Response:
        body = req.body or {}
        rows = self.db.query("SELECT * FROM users WHERE username = ?", (body.get("username", ""),))
        if not rows or not verify_password(body.get("password", ""), rows[0]["password_hash"], rows[0]["salt"]):
            return Response.error(401, "invalid credentials")
        u = rows[0]
        return Response.json(200, {"token": self.signer.issue(u["id"], u["tenant_id"])})

    def create_note(self, req: Request, user: dict) -> Response:
        body = req.body or {}
        title, text = str(body.get("title", "")).strip(), str(body.get("body", ""))
        if not title:
            return Response.error(400, "title is required")
        nid = self.db.execute(
            "INSERT INTO notes (tenant_id, owner_id, title, body) VALUES (?, ?, ?, ?)",
            (user["tenant_id"], user["id"], title, text),
        ).lastrowid
        return Response.json(201, {"id": nid, "title": title, "body": text})

    def search_notes(self, req: Request, user: dict) -> Response:
        q = req.query.get("q", "")
        pattern = f"%{q}%"
        rows = self.db.query(
            "SELECT id, title, body FROM notes WHERE tenant_id = ? AND (title LIKE ? OR body LIKE ?) ORDER BY id",
            (user["tenant_id"], pattern, pattern),
        )
        return Response.json(200, {"results": [dict(r) for r in rows]})

    def _note(self, note_id: int, user: dict) -> dict | None:
        """The note, if it exists in the caller's tenant (other tenants' notes look nonexistent)."""
        rows = self.db.query("SELECT * FROM notes WHERE id = ? AND tenant_id = ?", (note_id, user["tenant_id"]))
        return dict(rows[0]) if rows else None

    def get_note(self, note_id: int, user: dict) -> Response:
        note = self._note(note_id, user)
        if note is None:
            return Response.error(404, "note not found")
        return Response.json(200, {"id": note["id"], "title": note["title"], "body": note["body"]})

    def update_note(self, note_id: int, req: Request, user: dict) -> Response:
        note = self._note(note_id, user)
        if note is None:
            return Response.error(404, "note not found")
        if note["owner_id"] != user["id"]:
            return Response.error(403, "only the owner can update this note")
        body = req.body or {}
        title = str(body.get("title", note["title"]))
        text = str(body.get("body", note["body"]))
        self.db.execute("UPDATE notes SET title = ?, body = ? WHERE id = ?", (title, text, note_id))
        return Response.json(200, {"id": note_id, "title": title, "body": text})

    def view_note(self, note_id: int, user: dict) -> Response:
        note = self._note(note_id, user)
        if note is None:
            return Response.error(404, "note not found")
        title, body = html.escape(note["title"], quote=True), html.escape(note["body"], quote=True)
        markup = (
            "<!doctype html><html><head>"
            f"<meta name=\"description\" content=\"{title}\">"
            f"<title>{title}</title></head><body>"
            f"<h1>{title}</h1><article>{body}</article>"
            "</body></html>"
        )
        return Response.html(200, markup)

    def upload_attachment(self, req: Request, user: dict) -> Response:
        body = req.body or {}
        try:
            note = self._note(int(body.get("note_id", 0)), user)
        except (TypeError, ValueError):
            note = None
        if note is None:
            return Response.error(404, "note not found")
        if note["owner_id"] != user["id"]:
            return Response.error(403, "only the owner can add attachments")
        name = str(body.get("name", ""))
        content = str(body.get("content", "")).encode()
        path = self._attachment_path(note["id"], name)
        if path is None or len(content) > config.MAX_ATTACHMENT_BYTES:
            return Response.error(400, "invalid attachment")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        self.db.execute("INSERT INTO attachments (note_id, name) VALUES (?, ?)", (note["id"], name))
        return Response.json(201, {"note_id": note["id"], "name": name, "size": len(content)})

    def download_attachment(self, req: Request, user: dict) -> Response:
        try:
            note = self._note(int(req.query.get("note", "")), user)
        except ValueError:
            note = None
        name = req.query.get("name", "")
        path = self._attachment_path(note["id"], name) if note else None
        registered = note is not None and self.db.query(
            "SELECT 1 FROM attachments WHERE note_id = ? AND name = ?", (note["id"], name))
        if path is None or not registered or not path.is_file():
            return Response.error(404, "attachment not found")
        return Response(200, path.read_bytes(), {"Content-Type": "application/octet-stream"})

    def _attachment_path(self, note_id: int, name: str) -> Path | None:
        """Resolve an attachment name inside the note's folder; None for anything that escapes it."""
        if not name or name in (".", "..") or "/" in name or "\\" in name or "\x00" in name:
            return None
        folder = (Path(self.storage_dir) / str(note_id)).resolve()
        path = (folder / name).resolve()
        return path if path.parent == folder else None


def create_app(db_path: str = ":memory:", storage_dir: str = "storage", secret_key: str | None = None) -> NotesApp:
    key = secret_key or config.load_secret_key()
    if config.DEBUG:
        log.debug("starting notes app storage=%s", storage_dir)
    return NotesApp(Database(db_path), storage_dir, key)
