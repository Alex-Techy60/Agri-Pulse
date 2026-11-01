"""Sign in with Google: session cookie, owner scoping and failure paths. No network: Google's verifier is replaced."""
import time

import pytest
from fastapi.testclient import TestClient

from app.auth import google as auth
from app.core.config import get_settings
from app.main import app

CLAIMS = {"sub": "1234567890", "email": "sunita@example.com", "email_verified": True, "name": "Sunita", "picture": "https://x/y.png", "iss": "accounts.google.com"}
CRED = "x" * 40


@pytest.fixture
def client(monkeypatch, tmp_path):
    import app.api.routes as routes
    from app.memory.chats import ChatStore
    store = ChatStore(tmp_path / "chats.db")  # never write test users into the real database
    monkeypatch.setattr(routes, "get_chats", lambda: store)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com")
    monkeypatch.setenv("SESSION_SECRET", "unit-test-secret")
    get_settings.cache_clear()
    monkeypatch.setattr(auth, "verify_google_credential", lambda c: CLAIMS)
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def test_config_hidden_when_not_configured(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "")
    get_settings.cache_clear()
    with TestClient(app) as c:
        assert c.get("/api/auth/config").json() == {"enabled": False, "client_id": ""}
        assert c.post("/api/auth/google", json={"credential": CRED}).status_code == 404
    get_settings.cache_clear()


def test_sign_in_sets_httponly_cookie_and_me_works(client):
    assert client.get("/api/auth/config").json()["enabled"] is True
    assert client.get("/api/auth/me").json() == {"user": None}
    r = client.post("/api/auth/google", json={"credential": CRED})
    assert r.status_code == 200 and r.json()["user"]["email"] == "sunita@example.com"
    assert "httponly" in r.headers["set-cookie"].lower() and "samesite=lax" in r.headers["set-cookie"].lower()
    assert client.get("/api/auth/me").json()["user"]["name"] == "Sunita"
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").json() == {"user": None}


def test_bad_credential_is_401_not_500(client, monkeypatch):
    def boom(_):
        raise auth.AuthError("Google sign-in could not be verified. Please try again.")
    monkeypatch.setattr(auth, "verify_google_credential", boom)
    assert client.post("/api/auth/google", json={"credential": CRED}).status_code == 401
    assert client.get("/api/auth/me").json() == {"user": None}


def test_tampered_and_expired_sessions_are_rejected(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "unit-test-secret")
    get_settings.cache_clear()
    tok = auth.make_session(CLAIMS)
    assert auth.read_session(tok)["sub"] == "1234567890"
    body, sig = tok.rsplit(".", 1)
    assert auth.read_session(body + "." + sig[:-2] + "AA") is None
    assert auth.read_session("garbage") is None and auth.read_session(None) is None
    monkeypatch.setattr(time, "time", lambda t=time.time(): t + 15 * 86400)
    assert auth.read_session(tok) is None
    get_settings.cache_clear()


def test_signed_in_chats_follow_the_account_not_the_browser(client):
    client.post("/api/auth/google", json={"credential": CRED})
    body = {"message": "hello", "session_id": "a" * 16, "profile": {}}
    client.post("/api/chat", json=body, headers={"X-Client-Id": "a" * 48})
    from_other_browser = client.get("/api/chats", headers={"X-Client-Id": "b" * 48}).json()["chats"]
    assert [c["id"] for c in from_other_browser] == ["a" * 16]  # same account, different browser
    anon = TestClient(app)
    assert anon.get("/api/chats", headers={"X-Client-Id": "b" * 48}).json()["chats"] == []


def test_login_logout_login_keeps_every_chat(client):
    """The whole point of an account: chats from before signing in, while signed in, and after signing out all end up in it."""
    browser = {"X-Client-Id": "a" * 48}
    ask = lambda sid: client.post("/api/chat", json={"message": "hello " + sid, "session_id": sid, "profile": {}}, headers=browser)
    ids = lambda: sorted(c["id"] for c in client.get("/api/chats", headers=browser).json()["chats"])

    ask("before-login-1")                                            # anonymous
    client.post("/api/auth/google", json={"credential": CRED}, headers=browser)
    assert ids() == ["before-login-1"]                               # adopted into the account at sign-in
    ask("while-in-01")                                               # signed in
    client.post("/api/auth/logout")
    assert ids() == []                                               # signed out: this browser shows only its own anonymous chats
    ask("after-out-01")                                              # anonymous again
    client.post("/api/auth/google", json={"credential": CRED}, headers=browser)
    assert ids() == ["after-out-01", "before-login-1", "while-in-01"]
    other = {"X-Client-Id": "b" * 48}                                # a second device, same account
    assert len(client.get("/api/chats", headers=other).json()["chats"]) == 3
    assert [m["role"] for m in client.get("/api/chats/while-in-01", headers=other).json()["messages"]] == ["user", "bot"]


def test_settings_are_saved_per_person_validated_and_follow_the_account(client):
    browser, other = {"X-Client-Id": "a" * 48}, {"X-Client-Id": "b" * 48}
    assert client.get("/api/settings", headers=browser).json() == {"settings": {}}
    body = {"lang": "mr", "speak": True, "rate": 1.25, "profile": {"place": "Nashik, Maharashtra", "crop": "Onion", "evil": "x", "sowing_date": "  "}}
    assert client.put("/api/settings", json=body, headers=browser).json() == {"saved": True}
    got = client.get("/api/settings", headers=browser).json()["settings"]
    assert got == {"lang": "mr", "speak": True, "rate": 1.25, "profile": {"place": "Nashik, Maharashtra"}}  # unknown/blank fields dropped, and crop/sowing date are no longer profile fields
    client.put("/api/settings", json={"lang": "xx", "rate": 1}, headers=other)
    assert "lang" not in client.get("/api/settings", headers=other).json()["settings"]  # unknown language refused
    assert client.put("/api/settings", json={"rate": 99}, headers=other).status_code == 422
    client.post("/api/auth/google", json={"credential": CRED}, headers=browser)  # sign in: browser settings move to the account
    assert client.get("/api/settings", headers={"X-Client-Id": "c" * 48}).json()["settings"]["lang"] == "mr"
    assert client.put("/api/settings", json={"lang": "hi"}, headers=browser).status_code == 200


def _real_verifier(monkeypatch, fake):
    """Use the real verify_google_credential but replace Google's library call, so we see exactly how it is called."""
    from google.oauth2 import id_token
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com")
    get_settings.cache_clear()
    monkeypatch.setattr(id_token, "verify_oauth2_token", fake)


def test_small_clock_drift_does_not_block_sign_in(monkeypatch):
    seen = {}
    def fake(token, request, audience, clock_skew_in_seconds=0):
        seen["skew"] = clock_skew_in_seconds
        return CLAIMS
    _real_verifier(monkeypatch, fake)
    assert auth.verify_google_credential(CRED)["sub"] == CLAIMS["sub"]
    assert seen["skew"] >= 30  # a laptop clock 16 s behind Google made fresh tokens look "used too early"
    get_settings.cache_clear()


def test_rejection_log_names_clock_problems_but_never_quotes_the_token(monkeypatch, caplog):
    secret_token = "eyJ-secret-token-" + "a" * 30
    def early(*a, **k):
        raise ValueError("Token used too early, 100 < 120. Check that your computer's clock is set correctly.")
    def malformed(*a, **k):
        raise ValueError(f"Wrong number of segments in token: {secret_token}")
    for fake in (early, malformed):
        _real_verifier(monkeypatch, fake)
        with caplog.at_level("WARNING", logger="auth"), pytest.raises(auth.AuthError):
            auth.verify_google_credential(secret_token)
    assert "used too early" in caplog.text
    assert secret_token not in caplog.text
    get_settings.cache_clear()
