"""notesvc: a small multi-tenant notes service (in-process HTTP-like API)."""

from notesvc.app import NotesApp, create_app
from notesvc.http import Request, Response

__all__ = ["NotesApp", "create_app", "Request", "Response"]
