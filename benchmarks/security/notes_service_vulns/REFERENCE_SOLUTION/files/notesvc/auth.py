"""Password hashing and signed session tokens."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time

log = logging.getLogger("notesvc.auth")

TOKEN_TTL_SECONDS = 8 * 3600


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000)
    return digest.hex(), salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    candidate, _ = hash_password(password, salt)
    return hmac.compare_digest(candidate, password_hash)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class TokenSigner:
    def __init__(self, secret_key: str):
        self._key = secret_key.encode()

    def issue(self, user_id: int, tenant_id: int, now: float | None = None) -> str:
        payload = {"uid": user_id, "tid": tenant_id, "exp": int((now or time.time()) + TOKEN_TTL_SECONDS)}
        body = _b64(json.dumps(payload, separators=(",", ":")).encode())
        log.debug("issuing token for uid=%s", user_id)
        sig = _b64(hmac.new(self._key, body.encode(), hashlib.sha256).digest())
        return f"{body}.{sig}"

    def verify(self, token: str, now: float | None = None) -> dict | None:
        try:
            body, sig = token.split(".", 1)
        except ValueError:
            return None
        expected = _b64(hmac.new(self._key, body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(expected, sig):
            return None
        payload = json.loads(_unb64(body))
        if payload.get("exp", 0) < (now or time.time()):
            return None
        return payload
