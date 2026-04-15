from __future__ import annotations

from unittest.mock import patch

import config
from app import create_app


def _create_test_app(
    tmp_path,
    *,
    force_https: bool = False,
    session_cookie_secure: bool = False,
    hsts_enabled: bool = False,
):
    database_path = str(tmp_path / "transport-security-test.db")
    with patch.object(config, "FORCE_HTTPS", force_https), patch.object(
        config, "SESSION_COOKIE_SECURE", session_cookie_secure
    ), patch.object(config, "SECURITY_HSTS_ENABLED", hsts_enabled), patch.object(
        config, "SECURITY_HSTS_MAX_AGE", 31_536_000
    ), patch.object(
        config, "SECURITY_HSTS_INCLUDE_SUBDOMAINS", True
    ), patch.object(
        config, "SECURITY_HSTS_PRELOAD", False
    ), patch.object(
        config, "TRUST_PROXY_HEADERS", False
    ), patch.object(
        config, "PREFERRED_URL_SCHEME", "https" if force_https else "http"
    ):
        app = create_app(database_path=database_path, load_persisted_runtime_settings=False)

    app.testing = True
    app.config["TESTING"] = True
    return app


def test_force_https_redirects_insecure_requests(tmp_path):
    app = _create_test_app(tmp_path, force_https=True, session_cookie_secure=True)
    client = app.test_client()

    response = client.get("/", base_url="http://localhost")

    assert response.status_code == 308
    assert response.headers["Location"].startswith("https://localhost/")


def test_force_https_allows_already_secure_requests(tmp_path):
    app = _create_test_app(tmp_path, force_https=True, session_cookie_secure=True)
    client = app.test_client()

    response = client.get("/", base_url="https://localhost")

    assert response.status_code in {200, 302}


def test_hsts_header_is_set_for_secure_requests(tmp_path):
    app = _create_test_app(tmp_path, hsts_enabled=True)
    client = app.test_client()

    response = client.get("/", base_url="https://localhost")

    assert response.status_code in {200, 302}
    assert "Strict-Transport-Security" in response.headers
    assert "max-age=31536000" in response.headers["Strict-Transport-Security"]


def test_session_cookie_secure_flag_can_be_enabled(tmp_path):
    app = _create_test_app(tmp_path, session_cookie_secure=True)

    assert app.config["SESSION_COOKIE_SECURE"] is True
