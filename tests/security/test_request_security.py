from __future__ import annotations

from collections import deque

import pytest
from flask import Flask, jsonify, session

import request_security


@pytest.fixture
def security_app():
    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.config.update(TESTING=False)
    request_security.install_request_security(app)

    @app.get("/csrf-token")
    def csrf_token_route():
        return request_security.get_csrf_token()

    @app.get("/api/ping")
    def ping():
        return jsonify({"ok": True})

    @app.post("/api/items")
    def api_items():
        return jsonify({"ok": True})

    @app.post("/submit")
    def submit():
        return "ok"

    return app


@pytest.fixture(autouse=True)
def reset_rate_limit_state():
    request_security._RATE_LIMIT_STATE.clear()
    request_security._RATE_LIMIT_REQUEST_COUNT = 0
    yield
    request_security._RATE_LIMIT_STATE.clear()
    request_security._RATE_LIMIT_REQUEST_COUNT = 0


def test_get_csrf_token_reuses_existing_session_token(security_app):
    with security_app.test_request_context("/"):
        first = request_security.get_csrf_token()

        assert first
        assert session.modified is True

        session.modified = False
        second = request_security.get_csrf_token()

        assert second == first
        assert session.modified is False



def test_rotate_csrf_token_replaces_existing_token(security_app):
    with security_app.test_request_context("/"):
        first = request_security.get_csrf_token()
        session.modified = False

        rotated = request_security.rotate_csrf_token()

        assert rotated
        assert rotated != first
        assert session[request_security.CSRF_TOKEN_SESSION_KEY] == rotated
        assert session.modified is True



def test_safe_methods_bypass_csrf_protection(security_app):
    client = security_app.test_client()

    response = client.get("/api/ping")

    assert response.status_code == 200
    assert response.get_json() == {"ok": True}



def test_api_post_requires_header_csrf_token(security_app):
    client = security_app.test_client()
    token = client.get("/csrf-token").get_data(as_text=True)

    blocked = client.post("/api/items", json={"name": "blocked"})
    allowed = client.post("/api/items", json={"name": "allowed"}, headers={request_security.CSRF_HEADER_NAME: token})

    assert blocked.status_code == 403
    assert blocked.get_json()["error"] == "Security check failed. Refresh the page and try again."
    assert allowed.status_code == 200
    assert allowed.get_json() == {"ok": True}



def test_non_api_post_accepts_form_csrf_token(security_app):
    client = security_app.test_client()
    token = client.get("/csrf-token").get_data(as_text=True)

    blocked = client.post("/submit", data={"value": "blocked"})
    allowed = client.post("/submit", data={"value": "allowed", "csrf_token": token})

    assert blocked.status_code == 403
    assert "Security check failed" in blocked.get_data(as_text=True)
    assert allowed.status_code == 200
    assert allowed.get_data(as_text=True) == "ok"



def test_prune_rate_limit_state_removes_only_stale_buckets():
    request_security._RATE_LIMIT_STATE.update(
        {
            ("stale", "login"): deque([10.0]),
            ("fresh", "chat"): deque([299.5]),
            ("empty", "api-write"): deque(),
        }
    )

    request_security._prune_rate_limit_state(310.0)

    assert ("stale", "login") not in request_security._RATE_LIMIT_STATE
    assert ("empty", "api-write") not in request_security._RATE_LIMIT_STATE
    assert ("fresh", "chat") in request_security._RATE_LIMIT_STATE



def test_enforce_rate_limit_uses_unknown_bucket_when_remote_addr_missing(security_app, monkeypatch):
    monkeypatch.setattr(request_security, "_get_rate_limit_rule", lambda: ("chat", 1, 60))

    with security_app.test_request_context("/chat", method="POST"):
        first = request_security.enforce_rate_limit()
    with security_app.test_request_context("/chat", method="POST"):
        second = request_security.enforce_rate_limit()

    assert first is None
    assert second.status_code == 429
    assert ("unknown", "chat") in request_security._RATE_LIMIT_STATE



def test_enforce_rate_limit_keeps_bucket_names_isolated_for_same_client(security_app, monkeypatch):
    rules = iter([("login", 1, 60), ("settings", 1, 60), ("login", 1, 60)])
    monkeypatch.setattr(request_security, "_get_rate_limit_rule", lambda: next(rules))
    environ = {"REMOTE_ADDR": "203.0.113.10"}

    with security_app.test_request_context("/login", method="POST", environ_base=environ):
        first_login = request_security.enforce_rate_limit()
    with security_app.test_request_context("/api/settings", method="PATCH", environ_base=environ):
        first_settings = request_security.enforce_rate_limit()
    with security_app.test_request_context("/login", method="POST", environ_base=environ):
        second_login = request_security.enforce_rate_limit()

    assert first_login is None
    assert first_settings is None
    assert second_login.status_code == 429
    assert ("203.0.113.10", "login") in request_security._RATE_LIMIT_STATE
    assert ("203.0.113.10", "settings") in request_security._RATE_LIMIT_STATE


def test_request_client_identifier_prefers_access_route(security_app):
    previous_trust_proxy = request_security.config.TRUST_PROXY_HEADERS
    request_security.config.TRUST_PROXY_HEADERS = True
    try:
        with security_app.test_request_context(
            "/chat",
            method="POST",
            environ_base={"REMOTE_ADDR": "203.0.113.44"},
            headers={"X-Forwarded-For": "198.51.100.5, 203.0.113.44"},
        ):
            identifier = request_security._get_request_client_identifier()
    finally:
        request_security.config.TRUST_PROXY_HEADERS = previous_trust_proxy

    assert identifier == "198.51.100.5"


def test_enforce_rate_limit_uses_redis_backend_when_available(security_app, monkeypatch):
    class _FakeRedis:
        def __init__(self):
            self._rows: dict[str, dict[str, float]] = {}

        def zremrangebyscore(self, key, min_score, max_score):
            bucket = self._rows.setdefault(key, {})
            stale_members = [member for member, score in bucket.items() if float(score) <= float(max_score)]
            for member in stale_members:
                bucket.pop(member, None)

        def zcard(self, key):
            return len(self._rows.setdefault(key, {}))

        def zrange(self, key, start, stop, withscores=False):
            del start, stop
            bucket = self._rows.setdefault(key, {})
            ordered = sorted(bucket.items(), key=lambda item: item[1])
            if not ordered:
                return []
            member, score = ordered[0]
            if withscores:
                return [(member, score)]
            return [member]

        def zadd(self, key, mapping):
            bucket = self._rows.setdefault(key, {})
            for member, score in dict(mapping or {}).items():
                bucket[str(member)] = float(score)

        def expire(self, key, ttl_seconds):
            del key, ttl_seconds
            return True

    fake_redis = _FakeRedis()
    monkeypatch.setattr(request_security, "_get_rate_limit_rule", lambda: ("chat", 1, 60))
    monkeypatch.setattr(request_security, "_get_redis_rate_limit_client", lambda: fake_redis)

    with security_app.test_request_context("/chat", method="POST", environ_base={"REMOTE_ADDR": "203.0.113.12"}):
        first = request_security.enforce_rate_limit()
    with security_app.test_request_context("/chat", method="POST", environ_base={"REMOTE_ADDR": "203.0.113.12"}):
        second = request_security.enforce_rate_limit()

    assert first is None
    assert second.status_code == 429
    assert request_security._RATE_LIMIT_STATE == {}
