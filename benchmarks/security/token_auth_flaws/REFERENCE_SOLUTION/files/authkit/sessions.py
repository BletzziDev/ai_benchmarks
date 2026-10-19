"""Signed session cookies carrying a small dict of session data (JSON-serialisable values)."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from typing import Any

from authkit.errors import InvalidToken


class SessionCodec:
    def __init__(self, key: bytes):
        self._key = key

    def _mac(self, body: bytes) -> str:
        return hmac.new(self._key, body, hashlib.sha256).hexdigest()

    def dumps(self, data: dict[str, Any]) -> str:
        body = base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode())
        return f"{body.decode()}.{self._mac(body)}"

    def loads(self, cookie: str) -> dict[str, Any]:
        try:
            body_s, mac = cookie.rsplit(".", 1)
        except ValueError as e:
            raise InvalidToken("malformed session cookie") from e
        body = body_s.encode()
        # Authenticate before parsing anything the client sent.
        if not hmac.compare_digest(mac.encode(), self._mac(body).encode()):
            raise InvalidToken("bad session signature")
        try:
            data = json.loads(base64.urlsafe_b64decode(body))
        except (binascii.Error, ValueError) as e:
            raise InvalidToken("malformed session cookie") from e
        if not isinstance(data, dict):
            raise InvalidToken("bad session payload")
        return data
