"""Compact signed access tokens: ``b64(header).b64(payload).b64(signature)``.

Tokens are issued by the login service and verified by every API. Only HS256 tokens signed with
the service key may be accepted. ``exp`` (UNIX seconds) is mandatory; expired tokens are invalid.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

from authkit.encoding import b64d, b64e
from authkit.errors import InvalidToken

DEFAULT_TTL = 3600
ALGORITHM = "HS256"


class TokenService:
    def __init__(self, key: bytes, ttl_seconds: int = DEFAULT_TTL, clock=time.time):
        if len(key) < 32:
            raise ValueError("signing key must be at least 32 bytes")
        self._key = key
        self._ttl = ttl_seconds
        self._clock = clock

    def _sign(self, signing_input: bytes) -> str:
        return b64e(hmac.new(self._key, signing_input, hashlib.sha256).digest())

    def issue(self, subject: str, roles: list[str] | None = None, **claims: Any) -> str:
        header = {"alg": ALGORITHM, "typ": "AKT"}
        payload = {"sub": subject, "roles": roles or [], "iat": int(self._clock()),
                   "exp": int(self._clock()) + self._ttl, **claims}
        signing_input = f"{b64e(json.dumps(header).encode())}.{b64e(json.dumps(payload).encode())}"
        return f"{signing_input}.{self._sign(signing_input.encode())}"

    def verify(self, token: str) -> dict[str, Any]:
        """Return the payload of a valid token or raise InvalidToken."""
        try:
            h, p, s = token.split(".")
            header = json.loads(b64d(h))
        except (ValueError, json.JSONDecodeError) as e:
            raise InvalidToken("malformed token") from e
        # The algorithm is fixed by the server, never chosen by the token.
        if not isinstance(header, dict) or header.get("alg") != ALGORITHM:
            raise InvalidToken("unsupported algorithm")
        if not hmac.compare_digest(s.encode(), self._sign(f"{h}.{p}".encode()).encode()):
            raise InvalidToken("bad signature")
        try:
            payload = json.loads(b64d(p))
        except (ValueError, json.JSONDecodeError) as e:
            raise InvalidToken("malformed payload") from e
        exp = payload.get("exp") if isinstance(payload, dict) else None
        if not isinstance(exp, (int, float)) or isinstance(exp, bool):
            raise InvalidToken("missing expiry")
        if exp <= self._clock():
            raise InvalidToken("token expired")
        return payload
