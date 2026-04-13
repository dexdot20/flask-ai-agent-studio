from __future__ import annotations

import secrets
import time
from collections import deque
from threading import Lock

from flask import current_app, jsonify, request, session


CSRF_TOKEN_SESSION_KEY = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
_SAFE_HTTP_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
_RATE_LIMIT_LOCK = Lock()
_RATE_LIMIT_STATE: dict[tuple[str, str], deque[float]] = {}
_RATE_LIMIT_CLEANUP_INTERVAL = 128
_RATE_LIMIT_MAX_WINDOW_SECONDS = 300
_RATE_LIMIT_REQUEST_COUNT = 0


def get_csrf_token() -> str:
    token = str(session.get(CSRF_TOKEN_SESSION_KEY) or "").strip()
    if token:
        return token

    token = secrets.token_urlsafe(32)
    session[CSRF_TOKEN_SESSION_KEY] = token
    session.modified = True
    return token


def rotate_csrf_token() -> str:
    token = secrets.token_urlsafe(32)
    session[CSRF_TOKEN_SESSION_KEY] = token
    session.modified = True
    return token


def _is_testing_request() -> bool:
    return bool(current_app.testing or current_app.config.get("TESTING"))


def _requires_csrf_protection() -> bool:
    if request.method.upper() in _SAFE_HTTP_METHODS:
        return False
    if request.endpoint in {None, "static"}:
        return False
    return True


def validate_csrf_request():
    if _is_testing_request() or not _requires_csrf_protection():
        return None

    expected_token = str(session.get(CSRF_TOKEN_SESSION_KEY) or "").strip()
    provided_token = str(
        request.headers.get(CSRF_HEADER_NAME)
        or request.form.get("csrf_token")
        or ""
    ).strip()
    if expected_token and provided_token and secrets.compare_digest(expected_token, provided_token):
        return None

    if request.path.startswith("/api/") or request.path == "/chat":
        return jsonify({"error": "Security check failed. Refresh the page and try again."}), 403
    return "Security check failed. Refresh the page and try again.", 403


def _get_rate_limit_rule() -> tuple[str, int, int] | None:
    method = request.method.upper()
    path = request.path

    if path == "/login" and method == "POST":
        return "login", 10, 300
    if path == "/chat" and method == "POST":
        return "chat", 30, 60
    if path == "/api/fix-text" and method == "POST":
        return "fix-text", 60, 60
    if path.startswith("/api/rag/"):
        return "rag", 60, 60
    if path == "/api/settings" and method == "PATCH":
        return "settings", 30, 60
    if path.startswith("/api/") and method in {"POST", "PATCH", "DELETE"}:
        return "api-write", 180, 60
    return None


def _get_request_client_identifier() -> str:
    return str(request.remote_addr or "unknown").strip() or "unknown"


def _prune_rate_limit_state(now: float) -> None:
    stale_cutoff = now - _RATE_LIMIT_MAX_WINDOW_SECONDS
    stale_keys = [
        key
        for key, bucket in _RATE_LIMIT_STATE.items()
        if not bucket or bucket[-1] <= stale_cutoff
    ]
    for key in stale_keys:
        _RATE_LIMIT_STATE.pop(key, None)


def enforce_rate_limit():
    global _RATE_LIMIT_REQUEST_COUNT

    if _is_testing_request():
        return None

    rule = _get_rate_limit_rule()
    if rule is None:
        return None

    bucket_name, limit, window_seconds = rule
    now = time.monotonic()
    client_id = _get_request_client_identifier()
    bucket_key = (client_id, bucket_name)

    with _RATE_LIMIT_LOCK:
        _RATE_LIMIT_REQUEST_COUNT += 1
        if _RATE_LIMIT_REQUEST_COUNT % _RATE_LIMIT_CLEANUP_INTERVAL == 0:
            _prune_rate_limit_state(now)

        bucket = _RATE_LIMIT_STATE.setdefault(bucket_key, deque())
        cutoff = now - window_seconds
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()

        if len(bucket) >= limit:
            retry_after = max(1, int(window_seconds - (now - bucket[0]))) if bucket else window_seconds
            response = jsonify({"error": "Too many requests. Please try again shortly."})
            response.status_code = 429
            response.headers["Retry-After"] = str(retry_after)
            return response

        bucket.append(now)

    return None


def install_request_security(app) -> None:
    @app.context_processor
    def _inject_csrf_token() -> dict[str, str]:
        return {"csrf_token": get_csrf_token()}

    @app.before_request
    def _enforce_request_security():
        csrf_response = validate_csrf_request()
        if csrf_response is not None:
            return csrf_response

        rate_limit_response = enforce_rate_limit()
        if rate_limit_response is not None:
            return rate_limit_response

        return None
