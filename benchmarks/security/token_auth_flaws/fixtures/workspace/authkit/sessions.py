"""Signed session cookies carrying a small dict of session data."""

from __future__ import annotations

import base64
import hashlib
import hmac
import pickle
from typing import Any

from authkit.errors import InvalidToken


class SessionCodec:
    def __init__(self, key: bytes):
        self._key = key

    def _mac(self, body: bytes) -> str:
        return hmac.new(self._key, body, hashlib.sha256).hexdigest()

    def dumps(self, data: dict[str, Any]) -> str:
        body = base64.b64encode(pickle.dumps(data))
        return f"{body.decode()}.{self._mac(body)}"

    def loads(self, cookie: str) -> dict[str, Any]:
        try:
            body_s, mac = cookie.rsplit(".", 1)
            body = body_s.encode()
            data = pickle.loads(base64.b64decode(body))
        except Exception as e:
            raise InvalidToken("malformed session cookie") from e
        if mac != self._mac(body):
            raise InvalidToken("bad session signature")
        if not isinstance(data, dict):
            raise InvalidToken("bad session payload")
        return data
