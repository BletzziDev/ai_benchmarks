"""Password storage.

``UserStore`` maps usernames to stored password hashes. The production store was migrated from
the old PHP app and still contains hashes in that format; those users must keep being able to
log in.
"""

from __future__ import annotations

import hashlib


class UserStore:
    """In-memory stand-in for the users table: username -> stored hash string."""

    def __init__(self, initial: dict[str, str] | None = None):
        self.hashes: dict[str, str] = dict(initial or {})

    def get(self, username: str) -> str | None:
        return self.hashes.get(username)

    def set(self, username: str, stored_hash: str) -> None:
        self.hashes[username] = stored_hash


def hash_password(password: str) -> str:
    return hashlib.sha1(password.encode()).hexdigest()


def verify_password(password: str, stored_hash: str) -> bool:
    return hash_password(password) == stored_hash


def register(store: UserStore, username: str, password: str) -> None:
    if store.get(username) is not None:
        raise ValueError("user exists")
    if len(password) < 8:
        raise ValueError("password too short")
    store.set(username, hash_password(password))


def authenticate(store: UserStore, username: str, password: str) -> bool:
    stored = store.get(username)
    if stored is None:
        return False
    return verify_password(password, stored)
