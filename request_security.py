from __future__ import annotations

import logging
import secrets
import time
from collections import deque
from threading import Lock

from flask import current_app, jsonify, request, session

import config

try:
    import redis
except Exception:  # pragma: no cover - optional runtime dependency
    redis = None


CSRF_TOKEN_SESSION_KEY = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
_SAFE_HTTP_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
_RATE_LIMIT_LOCK = Lock()
_RATE_LIMIT_STATE: dict[tuple[str, str], deque[float]] = {}
_RATE_LIMIT_CLEANUP_INTERVAL = 128
_RATE_LIMIT_MAX_WINDOW_SECONDS = 300
_RATE_LIMIT_REQUEST_COUNT = 0
_RATE_LIMIT_REDIS_LOCK = Lock()
_RATE_LIMIT_REDIS_CLIENT = None
_RATE_LIMIT_REDIS_INITIALIZED = False
LOGGER = logging.getLogger(__name__)


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
    if not bool(getattr(config, "TRUST_PROXY_HEADERS", False)):
        return str(request.remote_addr or "unknown").strip() or "unknown"

    access_route = getattr(request, "access_route", None) or []
    for entry in access_route:
        normalized = str(entry or "").strip()
        if normalized:
            return normalized
    return str(request.remote_addr or "unknown").strip() or "unknown"


def _build_rate_limit_response(retry_after: int):
    response = jsonify({"error": "Too many requests. Please try again shortly."})
    response.status_code = 429
    response.headers["Retry-After"] = str(max(1, int(retry_after or 1)))
    return response


def _get_redis_rate_limit_client():
    global _RATE_LIMIT_REDIS_CLIENT, _RATE_LIMIT_REDIS_INITIALIZED

    if _RATE_LIMIT_REDIS_INITIALIZED:
        return _RATE_LIMIT_REDIS_CLIENT

    with _RATE_LIMIT_REDIS_LOCK:
        if _RATE_LIMIT_REDIS_INITIALIZED:
            return _RATE_LIMIT_REDIS_CLIENT

        _RATE_LIMIT_REDIS_INITIALIZED = True
        redis_url = str(getattr(config, "SECURITY_RATE_LIMIT_REDIS_URL", "") or "").strip()
        if not getattr(config, "SECURITY_RATE_LIMIT_REDIS_ENABLED", False) or not redis_url:
            return None
        if redis is None:
            LOGGER.warning("Redis-backed rate limiting is enabled but redis package is unavailable; using in-memory fallback.")
            return None

        try:
            client = redis.Redis.from_url(redis_url, decode_responses=True)
            client.ping()
        except Exception:
            LOGGER.exception("Failed to initialize Redis rate-limit backend; using in-memory fallback.")
            return None

        _RATE_LIMIT_REDIS_CLIENT = client
        return _RATE_LIMIT_REDIS_CLIENT


def _enforce_rate_limit_with_redis(bucket_name: str, limit: int, window_seconds: int, client_id: str):
    client = _get_redis_rate_limit_client()
    if client is None:
        return None, False

    now = time.time()
    cutoff = now - window_seconds
    bucket_key = f"rate-limit:{bucket_name}:{client_id}"

    try:
        client.zremrangebyscore(bucket_key, 0, cutoff)
        current_count = int(client.zcard(bucket_key) or 0)
        if current_count >= limit:
            oldest = client.zrange(bucket_key, 0, 0, withscores=True)
            if oldest:
                oldest_timestamp = float(oldest[0][1])
                retry_after = max(1, int(window_seconds - (now - oldest_timestamp)))
            else:
                retry_after = window_seconds
            return _build_rate_limit_response(retry_after), True

        token = f"{now:.6f}:{secrets.token_hex(6)}"
        client.zadd(bucket_key, {token: now})
        client.expire(bucket_key, max(10, window_seconds + 5))
        return None, True
    except Exception:
        LOGGER.exception("Redis rate-limit check failed; using in-memory fallback for this request.")
        return None, False


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
    client_id = _get_request_client_identifier()

    redis_response, redis_handled = _enforce_rate_limit_with_redis(
        bucket_name,
        limit,
        window_seconds,
        client_id,
    )
    if redis_handled:
        return redis_response

    now = time.monotonic()
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
            return _build_rate_limit_response(retry_after)

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
