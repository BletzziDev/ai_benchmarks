import pytest

from authkit import InvalidToken, SessionCodec, TokenService, UserStore, authenticate, register

KEY = b"k" * 32


def test_token_roundtrip():
    ts = TokenService(KEY)
    claims = ts.verify(ts.issue("alice", ["admin"], tenant="acme"))
    assert claims["sub"] == "alice" and claims["roles"] == ["admin"] and claims["tenant"] == "acme"


def test_tampered_token_rejected():
    ts = TokenService(KEY)
    h, p, s = ts.issue("alice").split(".")
    with pytest.raises(InvalidToken):
        ts.verify(f"{h}.{p}.{s[:-2]}xx")


def test_short_key_rejected():
    with pytest.raises(ValueError):
        TokenService(b"short")


def test_session_roundtrip():
    c = SessionCodec(KEY)
    data = {"user": "alice", "cart": [1, 2], "admin": False}
    assert c.loads(c.dumps(data)) == data


def test_session_tamper_rejected():
    c = SessionCodec(KEY)
    cookie = c.dumps({"user": "alice"})
    with pytest.raises(InvalidToken):
        c.loads(cookie[:-3] + "abc")


def test_register_and_authenticate():
    store = UserStore()
    register(store, "alice", "correct horse")
    assert authenticate(store, "alice", "correct horse")
    assert not authenticate(store, "alice", "wrong")
    assert not authenticate(store, "nobody", "x")
