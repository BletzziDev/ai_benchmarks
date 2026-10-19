"""Password storage.

``UserStore`` maps usernames to stored password hashes. The production store was migrated from
the old PHP app and still contains hashes in that format; those users must keep being able to
log in.

Formats:
  * current: ``pbkdf2_sha256$<iterations>$<salt hex>$<hash hex>``
  * legacy (read-only): unsalted SHA-1 hex digest; upgraded transparently on successful login.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 200_000
_LEGACY_RE = re.compile(r"^[0-9a-f]{40}$")


class UserStore:
    """In-memory stand-in for the users table: username -> stored hash string."""

    def __init__(self, initial: dict[str, str] | None = None):
        self.hashes: dict[str, str] = dict(initial or {})

    def get(self, username: str) -> str | None:
        return self.hashes.get(username)

    def set(self, username: str, stored_hash: str) -> None:
        self.hashes[username] = stored_hash


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"{ALGORITHM}${ITERATIONS}${salt.hex()}${digest.hex()}"


def is_legacy_hash(stored_hash: str) -> bool:
    return bool(_LEGACY_RE.match(stored_hash))


def verify_password(password: str, stored_hash: str) -> bool:
    if is_legacy_hash(stored_hash):
        candidate = hashlib.sha1(password.encode()).hexdigest()
        return hmac.compare_digest(candidate, stored_hash)
    try:
        algorithm, iterations, salt_hex, digest_hex = stored_hash.split("$")
        if algorithm != ALGORITHM:
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations))
    except ValueError:
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


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
    if not verify_password(password, stored):
        return False
    if is_legacy_hash(stored):
        store.set(username, hash_password(password))  # transparent upgrade of legacy hashes
    return True
