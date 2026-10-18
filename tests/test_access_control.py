"""#13 — optional access control for server deployments."""
import pytest
from fastapi.testclient import TestClient

import access
import app as app_module

TOKEN = "s3cret-token-0123456789abcdef"


@pytest.fixture(autouse=True)
def _fresh_throttle():
    access._failures.clear()
    yield
    access._failures.clear()


@pytest.fixture
def served(monkeypatch):
    monkeypatch.setenv("SHEPHERD_ACCESS_TOKEN", TOKEN)
    monkeypatch.delenv("SHEPHERD_TRUSTED_ORIGINS", raising=False)
    return TestClient(app_module.app, follow_redirects=False)


def test_without_a_token_nothing_is_gated(monkeypatch):
    monkeypatch.delenv("SHEPHERD_ACCESS_TOKEN", raising=False)
    c = TestClient(app_module.app, follow_redirects=False)
    assert c.get("/api/version").status_code == 200


def test_api_requires_authentication(served):
    r = served.get("/api/version")
    assert r.status_code == 401 and r.json() == {"error": "authentication required"}
    assert served.post("/api/profiles/switch", json={"id": "x"}).status_code == 401


def test_browser_navigation_redirects_to_login(served):
    r = served.get("/")
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_bearer_token_authorises(served):
    ok = served.get("/api/version", headers={"Authorization": f"Bearer {TOKEN}"})
    bad = served.get("/api/version", headers={"Authorization": "Bearer nope"})
    assert ok.status_code == 200 and bad.status_code == 401


def test_login_sets_an_httponly_strict_cookie_that_works(served):
    wrong = served.post("/login", data={"token": "nope"})
    assert wrong.status_code == 401 and "shepherd_session" not in wrong.headers.get("set-cookie", "")
    r = served.post("/login", data={"token": TOKEN})
    assert r.status_code == 303 and r.headers["location"] == "/"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert TOKEN not in r.headers["set-cookie"]          # derived value, never the token
    served.cookies.set("shepherd_session", access.session_value(TOKEN))
    assert served.get("/api/version").status_code == 200


def test_forwarding_headers_do_not_bypass_the_gate(served):
    r = served.get("/api/version", headers={"X-Forwarded-For": "127.0.0.1", "X-Real-IP": "127.0.0.1",
                                            "Forwarded": "for=127.0.0.1"})
    assert r.status_code == 401


def test_identity_headers_from_an_oidc_proxy_do_not_authenticate(served):
    # A proxy in front (Pocket ID, oauth2-proxy) identifies the rider with headers;
    # the app trusts only the bearer token the proxy injects (docs/SERVER.md).
    ident = {"X-Forwarded-User": "isaac", "Remote-User": "isaac", "X-Forwarded-Proto": "https"}
    assert served.get("/api/version", headers=ident).status_code == 401
    ok = served.get("/api/version", headers={**ident, "Authorization": f"Bearer {TOKEN}"})
    assert ok.status_code == 200


def test_healthz_is_open(served):
    assert served.get("/healthz").json() == {"ok": True}


def test_trusted_origin_is_exact(monkeypatch, served):
    served.cookies.set("shepherd_session", access.session_value(TOKEN))
    body = {"id": "does-not-exist"}
    evil = served.post("/api/profiles/switch", json=body, headers={"Origin": "https://train.example.com"})
    assert evil.status_code == 403
    monkeypatch.setenv("SHEPHERD_TRUSTED_ORIGINS", "https://train.example.com")
    ok = served.post("/api/profiles/switch", json=body, headers={"Origin": "https://train.example.com"})
    assert ok.status_code != 403
    other = served.post("/api/profiles/switch", json=body, headers={"Origin": "https://train.example.com.evil.io"})
    assert other.status_code == 403


def test_server_mode_without_a_token_refuses_to_start(monkeypatch):
    monkeypatch.setenv("SHEPHERD_SERVER_MODE", "1")
    monkeypatch.delenv("SHEPHERD_ACCESS_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="refusing to start"):
        with TestClient(app_module.app):
            pass


def test_server_mode_with_a_token_starts(monkeypatch):
    monkeypatch.setenv("SHEPHERD_SERVER_MODE", "1")
    monkeypatch.setenv("SHEPHERD_ACCESS_TOKEN", TOKEN)
    with TestClient(app_module.app) as c:
        assert c.get("/healthz").status_code == 200


def test_server_mode_refuses_a_short_token(monkeypatch):
    monkeypatch.setenv("SHEPHERD_SERVER_MODE", "1")
    monkeypatch.setenv("SHEPHERD_ACCESS_TOKEN", "short")
    with pytest.raises(RuntimeError, match="shorter than"):
        with TestClient(app_module.app):
            pass


def test_repeated_wrong_logins_are_throttled(served):
    for _ in range(access.MAX_FAILURES):
        assert served.post("/login", data={"token": "nope"}).status_code == 401
    r = served.post("/login", data={"token": "nope"})
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0
    # even the right token waits out the lockout
    assert served.post("/login", data={"token": TOKEN}).status_code == 429


def test_repeated_wrong_bearer_tokens_are_throttled(served):
    bad = {"Authorization": "Bearer nope"}
    for _ in range(access.MAX_FAILURES):
        assert served.get("/api/version", headers=bad).status_code == 401
    assert served.get("/api/version", headers=bad).status_code == 429


def test_throttle_lifts_after_the_window():
    for _ in range(access.MAX_FAILURES):
        access.record_failure("c", now=100.0)
    assert access.retry_after("c", now=101.0) > 0
    assert access.retry_after("c", now=100.0 + access.FAILURE_WINDOW + 1) == 0


def test_a_good_login_clears_the_failures(served):
    for _ in range(access.MAX_FAILURES - 1):
        served.post("/login", data={"token": "nope"})
    assert served.post("/login", data={"token": TOKEN}).status_code == 303
    assert not access._failures


def test_an_expired_cookie_is_rejected(served):
    import time
    old = access.session_value(TOKEN, issued_at=time.time() - access.SESSION_MAX_AGE - 5)
    served.cookies.set("shepherd_session", old)
    assert served.get("/api/version").status_code == 401


def test_a_forged_or_old_format_cookie_is_rejected(served):
    for bad in ("x", "1.0.deadbeef", access.session_value(TOKEN).split(".")[0] + ".00"):
        served.cookies.set("shepherd_session", bad)
        assert served.get("/api/version").status_code == 401


def test_sign_out_everywhere_revokes_old_cookies(served):
    old = access.session_value(TOKEN)
    served.cookies.set("shepherd_session", old)
    assert served.get("/api/version").status_code == 200
    assert served.post("/api/logout-everywhere").status_code == 200
    assert served.get("/api/version").status_code == 401           # the copied cookie is dead
    fresh = served.post("/login", data={"token": TOKEN})
    assert fresh.status_code == 303
    served.cookies.set("shepherd_session", access.session_value(TOKEN))
    assert served.get("/api/version").status_code == 200
