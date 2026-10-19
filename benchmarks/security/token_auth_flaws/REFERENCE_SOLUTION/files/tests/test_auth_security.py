"""Regression tests for the authkit security review."""

import base64
import hashlib
import json
import pickle

import pytest

from authkit import InvalidToken, SessionCodec, TokenService, UserStore, authenticate
from authkit.encoding import b64e

KEY = b"r" * 32


def test_unsigned_alg_none_token_rejected():
    forged = ".".join([b64e(json.dumps({"alg": "none"}).encode()), b64e(json.dumps({"sub": "root", "exp": 9e12}).encode()), ""])
    with pytest.raises(InvalidToken):
        TokenService(KEY).verify(forged)


def test_expired_token_rejected():
    now = [1_000_000.0]
    ts = TokenService(KEY, ttl_seconds=60, clock=lambda: now[0])
    tok = ts.issue("alice")
    now[0] += 61
    with pytest.raises(InvalidToken):
        ts.verify(tok)


class Boom:
    def __reduce__(self):
        return (pytest.fail, ("pickle payload executed",))


def test_session_cookie_never_unpickles_attacker_data():
    body = base64.b64encode(pickle.dumps(Boom()))
    with pytest.raises(InvalidToken):
        SessionCodec(KEY).loads(f"{body.decode()}.{'0' * 64}")


def test_new_hashes_are_salted():
    store = UserStore()
    from authkit import register

    register(store, "a", "password-123")
    register(store, "b", "password-123")
    assert store.get("a") != store.get("b")
    assert store.get("a") != hashlib.sha1(b"password-123").hexdigest()


def test_legacy_hash_upgraded_on_login():
    store = UserStore({"old": hashlib.sha1(b"legacy-pass").hexdigest()})
    assert authenticate(store, "old", "legacy-pass")
    assert store.get("old") != hashlib.sha1(b"legacy-pass").hexdigest()
    assert authenticate(store, "old", "legacy-pass")
