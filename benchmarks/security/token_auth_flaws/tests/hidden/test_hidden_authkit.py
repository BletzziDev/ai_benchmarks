# AIBENCH-CANARY: 5c2a7e91-token-auth-flaws-hidden — this file must never be shown to evaluated models.
"""Hidden tests for security/token_auth_flaws.

Groups: test_alg_ (algorithm confusion / unsigned tokens / malformed input), test_exp_ (expiry),
test_timing_ (constant-time comparisons, observed by spying on compare_digest), test_pickle_
(insecure deserialization), test_pw_ (password hashing + legacy migration), test_func_.
"""

import base64
import hashlib
import hmac
import importlib
import inspect
import json
import os
import pickle
import secrets
import sys

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from authkit import InvalidToken, SessionCodec, TokenService, UserStore, authenticate, hash_password, register, verify_password
from authkit.encoding import b64e

KEY = b"hidden-key-0123456789abcdef0123456789"


def craft(header, payload, key=KEY, sig=None):
    h = b64e(json.dumps(header).encode())
    p = b64e(json.dumps(payload).encode())
    if sig is None:
        sig = b64e(hmac.new(key, f"{h}.{p}".encode(), hashlib.sha256).digest())
    return f"{h}.{p}.{sig}"


FUTURE = 4_000_000_000


# ----------------------------------------------------------------------------- algorithm

@pytest.mark.parametrize("alg", ["none", "None", "NONE", "nOnE", "", None])
def test_alg_unsigned_tokens_rejected(alg):
    header = {"typ": "AKT"} if alg is None else {"alg": alg, "typ": "AKT"}
    with pytest.raises(InvalidToken):
        TokenService(KEY).verify(craft(header, {"sub": "root", "roles": ["admin"], "exp": FUTURE}, sig=""))


def test_alg_none_rejected_even_with_valid_mac():
    tok = craft({"alg": "none", "typ": "AKT"}, {"sub": "root", "exp": FUTURE})
    with pytest.raises(InvalidToken):
        TokenService(KEY).verify(tok)


def test_alg_other_algorithms_rejected():
    for alg in ("HS512", "RS256", "hs256"):
        with pytest.raises(InvalidToken):
            TokenService(KEY).verify(craft({"alg": alg, "typ": "AKT"}, {"sub": "x", "exp": FUTURE}))


@settings(max_examples=300, deadline=None, derandomize=True, database=None)
@given(st.one_of(st.text(max_size=80), st.lists(st.text(alphabet="abcXYZ012-_=", max_size=20), min_size=1, max_size=4).map(".".join)))
def test_alg_malformed_input_raises_invalid_token_only(s):
    try:
        TokenService(KEY).verify(s)
    except InvalidToken:
        pass


def test_alg_non_object_header_and_payload():
    for header, payload in (([1, 2], {"exp": FUTURE}), ("HS256", {"exp": FUTURE}), ({"alg": "HS256"}, [1]), ({"alg": "HS256"}, "x")):
        with pytest.raises(InvalidToken):
            TokenService(KEY).verify(craft(header, payload))


# ----------------------------------------------------------------------------- expiry

def test_exp_expired_token_rejected():
    now = [1_700_000_000.0]
    ts = TokenService(KEY, ttl_seconds=300, clock=lambda: now[0])
    tok = ts.issue("alice")
    now[0] += 299
    assert ts.verify(tok)["sub"] == "alice"
    now[0] += 2
    with pytest.raises(InvalidToken):
        ts.verify(tok)


def test_exp_missing_or_non_numeric_rejected():
    ts = TokenService(KEY)
    for payload in ({"sub": "x"}, {"sub": "x", "exp": "4000000000"}, {"sub": "x", "exp": None}):
        with pytest.raises(InvalidToken):
            ts.verify(craft({"alg": "HS256", "typ": "AKT"}, payload))


def test_exp_long_expired_crafted_token_rejected():
    with pytest.raises(InvalidToken):
        TokenService(KEY).verify(craft({"alg": "HS256", "typ": "AKT"}, {"sub": "x", "exp": 1_000_000_000}))


# ----------------------------------------------------------------------------- timing

@pytest.fixture
def spy(monkeypatch):
    calls = []
    orig = hmac.compare_digest

    def spy_fn(a, b):
        calls.append((a, b))
        return orig(a, b)

    monkeypatch.setattr(hmac, "compare_digest", spy_fn)
    monkeypatch.setattr(secrets, "compare_digest", spy_fn)
    saved = {k: v for k, v in sys.modules.items() if k == "authkit" or k.startswith("authkit.")}
    for k in saved:
        del sys.modules[k]
    mod = importlib.import_module("authkit")
    yield mod, calls
    for k in [k for k in sys.modules if k == "authkit" or k.startswith("authkit.")]:
        del sys.modules[k]
    sys.modules.update(saved)


def test_timing_token_signature_compared_in_constant_time(spy):
    mod, calls = spy
    ts = mod.TokenService(KEY)
    tok = ts.issue("alice")
    calls.clear()
    ts.verify(tok)
    assert calls, "token signature not compared with compare_digest"
    h, p, s = tok.split(".")
    calls.clear()
    with pytest.raises(mod.InvalidToken):
        ts.verify(f"{h}.{p}.{s[:-4]}AAAA")
    assert calls


def test_timing_session_mac_compared_in_constant_time(spy):
    mod, calls = spy
    c = mod.SessionCodec(KEY)
    cookie = c.dumps({"u": 1})
    calls.clear()
    c.loads(cookie)
    assert calls, "session MAC not compared with compare_digest"


def test_timing_password_hashes_compared_in_constant_time(spy):
    mod, calls = spy
    calls.clear()
    mod.verify_password("legacy-pass", hashlib.sha1(b"legacy-pass").hexdigest())
    assert calls, "legacy hash not compared with compare_digest"
    stored = mod.hash_password("new-password-1")
    calls.clear()
    mod.verify_password("new-password-1", stored)
    assert calls, "password hash not compared with compare_digest"


# ----------------------------------------------------------------------------- insecure deserialization

class _Payload:
    def __init__(self, marker):
        self.marker = marker

    def __reduce__(self):
        return (os.makedirs, (self.marker,))


def _pickle_cookie(marker, key=None):
    body = base64.b64encode(pickle.dumps(_Payload(marker)))
    mac = hmac.new(key, body, hashlib.sha256).hexdigest() if key else "0" * 64
    return f"{body.decode()}.{mac}"


def test_pickle_unsigned_payload_not_executed(tmp_path):
    marker = str(tmp_path / "pwned-unsigned")
    with pytest.raises(InvalidToken):
        SessionCodec(KEY).loads(_pickle_cookie(marker))
    assert not os.path.exists(marker)


def test_pickle_correctly_signed_payload_not_executed(tmp_path):
    marker = str(tmp_path / "pwned-signed")
    try:
        SessionCodec(KEY).loads(_pickle_cookie(marker, KEY))
    except InvalidToken:
        pass
    assert not os.path.exists(marker), "cookie data is still deserialized with pickle"


def test_pickle_urlsafe_variant_not_executed(tmp_path):
    marker = str(tmp_path / "pwned-urlsafe")
    body = base64.urlsafe_b64encode(pickle.dumps(_Payload(marker)))
    mac = hmac.new(KEY, body, hashlib.sha256).hexdigest()
    try:
        SessionCodec(KEY).loads(f"{body.decode()}.{mac}")
    except InvalidToken:
        pass
    assert not os.path.exists(marker)


# ----------------------------------------------------------------------------- password storage

def test_pw_new_hashes_salted_and_not_sha1():
    a, b = hash_password("same-password"), hash_password("same-password")
    assert a != b
    assert hashlib.sha1(b"same-password").hexdigest() not in (a, b)
    assert verify_password("same-password", a) and not verify_password("other-password", a)


def test_pw_uses_slow_kdf(monkeypatch):
    seen = []
    orig_pbkdf2, orig_scrypt = hashlib.pbkdf2_hmac, hashlib.scrypt

    def pbkdf2(name, pw, salt, iterations, *a, **k):
        seen.append(("pbkdf2", iterations))
        return orig_pbkdf2(name, pw, salt, iterations, *a, **k)

    def scrypt(pw, *a, **k):
        seen.append(("scrypt", k.get("n", 0)))
        return orig_scrypt(pw, *a, **k)

    monkeypatch.setattr(hashlib, "pbkdf2_hmac", pbkdf2)
    monkeypatch.setattr(hashlib, "scrypt", scrypt)
    saved = {k: v for k, v in sys.modules.items() if k.startswith("authkit")}
    for k in saved:
        del sys.modules[k]
    try:
        importlib.import_module("authkit.passwords").hash_password("measure-me-123")
    finally:
        for k in [k for k in sys.modules if k.startswith("authkit")]:
            del sys.modules[k]
        sys.modules.update(saved)
    assert any((kind == "pbkdf2" and n >= 100_000) or (kind == "scrypt" and n >= 2**14) for kind, n in seen), seen


def test_pw_legacy_users_can_still_log_in():
    store = UserStore({"old": hashlib.sha1(b"legacy-pass-1").hexdigest()})
    assert authenticate(store, "old", "legacy-pass-1")


def test_pw_legacy_hash_upgraded_on_successful_login_only():
    legacy = hashlib.sha1(b"legacy-pass-2").hexdigest()
    store = UserStore({"old": legacy})
    assert not authenticate(store, "old", "wrong-password")
    assert store.get("old") == legacy
    assert authenticate(store, "old", "legacy-pass-2")
    upgraded = store.get("old")
    assert upgraded != legacy and len(upgraded) > 40
    assert authenticate(store, "old", "legacy-pass-2")
    assert not authenticate(store, "old", "wrong-password")


# ----------------------------------------------------------------------------- functionality

def test_func_token_claims_roundtrip():
    ts = TokenService(KEY)
    c = ts.verify(ts.issue("alice", ["admin", "billing"], tenant="acme", device="ios"))
    assert (c["sub"], c["roles"], c["tenant"], c["device"]) == ("alice", ["admin", "billing"], "acme", "ios")
    assert c["exp"] > c["iat"]


def test_func_token_rejected_with_other_key_and_tampered_payload():
    tok = TokenService(KEY).issue("alice")
    with pytest.raises(InvalidToken):
        TokenService(b"x" * 32).verify(tok)
    h, p, s = tok.split(".")
    evil = b64e(json.dumps({"sub": "root", "roles": ["admin"], "exp": FUTURE}).encode())
    with pytest.raises(InvalidToken):
        TokenService(KEY).verify(f"{h}.{evil}.{s}")


def test_func_session_roundtrip_json_types():
    c = SessionCodec(KEY)
    data = {"user": "alice", "n": 3, "cart": [1, 2, {"sku": "A"}], "admin": False, "note": None, "uni": "café"}
    assert c.loads(c.dumps(data)) == data
    with pytest.raises(InvalidToken):
        SessionCodec(b"y" * 32).loads(c.dumps(data))
    with pytest.raises(InvalidToken):
        c.loads("garbage")


def test_func_register_and_authenticate_rules():
    store = UserStore()
    register(store, "alice", "correct horse battery")
    assert authenticate(store, "alice", "correct horse battery")
    assert not authenticate(store, "alice", "Correct horse battery")
    assert not authenticate(store, "bob", "whatever")
    with pytest.raises(ValueError):
        register(store, "alice", "another password")
    with pytest.raises(ValueError):
        register(store, "carol", "short")


def test_func_public_api_signatures():
    names = lambda f: [p.name for p in inspect.signature(f).parameters.values()]
    assert names(TokenService.__init__)[:4] == ["self", "key", "ttl_seconds", "clock"]
    assert names(TokenService.issue)[:3] == ["self", "subject", "roles"]
    assert names(TokenService.verify) == ["self", "token"]
    assert names(SessionCodec.dumps) == ["self", "data"] and names(SessionCodec.loads) == ["self", "cookie"]
    assert names(authenticate) == ["store", "username", "password"]
    with pytest.raises(ValueError):
        TokenService(b"short-key")
