from datetime import timedelta
from threading import Lock

from flask import Flask, redirect, request
from werkzeug.middleware.proxy_fix import ProxyFix

import config
from logging_config import configure_logging, get_logger
from request_security import install_request_security


_RAG_STARTUP_SYNC_LOCK = Lock()
_logger = get_logger(__name__)


def _sync_rag_on_startup() -> None:
    if not config.RAG_ENABLED:
        return
    from rag_service import sync_conversations_to_rag_safe

    _logger.info("Starting RAG conversation sync...")
    sync_conversations_to_rag_safe()


def create_app(database_path: str | None = None, *, load_persisted_runtime_settings: bool = True) -> Flask:
    configure_logging()

    _logger.info("=" * 60)
    _logger.info("Application starting...")
    _logger.info("=" * 60)

    resolved_database_path = str(database_path or config.DB_PATH).strip() or config.DB_PATH
    if load_persisted_runtime_settings:
        config.apply_persisted_runtime_settings(resolved_database_path)
        config.propagate_runtime_settings_to_loaded_modules()
        _logger.info("Runtime settings loaded from database")

    from db import close_db_connection, configure_db_path, initialize_database
    from routes import (
        register_activity_routes,
        install_auth_guard,
        register_auth_routes,
        register_chat_routes,
        register_conversation_routes,
        register_page_routes,
    )

    resolved_database_path = configure_db_path(resolved_database_path)
    _logger.info("Database path: %s", resolved_database_path)

    app = Flask(__name__)
    app.config["DATABASE_PATH"] = resolved_database_path
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=config.LOGIN_REMEMBER_SESSION_DAYS)
    app.config["PREFERRED_URL_SCHEME"] = config.PREFERRED_URL_SCHEME
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = config.SESSION_COOKIE_SECURE

    _logger.info("Session cookie secure: %s", config.SESSION_COOKIE_SECURE)

    if config.TRUST_PROXY_HEADERS:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
        _logger.info("Proxy headers trust enabled")

    if config.SECURITY_HSTS_ENABLED:
        hsts_directives = [f"max-age={config.SECURITY_HSTS_MAX_AGE}"]
        if config.SECURITY_HSTS_INCLUDE_SUBDOMAINS:
            hsts_directives.append("includeSubDomains")
        if config.SECURITY_HSTS_PRELOAD:
            hsts_directives.append("preload")
        hsts_value = "; ".join(hsts_directives)

        @app.after_request
        def _inject_hsts_header(response):
            if request.is_secure:
                response.headers.setdefault("Strict-Transport-Security", hsts_value)
            return response
        _logger.info("HSTS enabled: %s", hsts_value)

    if config.FORCE_HTTPS:
        @app.before_request
        def _enforce_https():
            if request.is_secure:
                return None
            secure_url = request.url.replace("http://", "https://", 1)
            return redirect(secure_url, code=308)
        _logger.info("HTTPS enforcement enabled")

    @app.after_request
    def _inject_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: blob:; "
                "font-src 'self' data:; "
                "connect-src 'self'"
            ),
        )
        return response

    @app.before_request
    def _sync_rag_once_before_request():
        if app.config.get("RAG_STARTUP_SYNC_DONE"):
            return None

        with _RAG_STARTUP_SYNC_LOCK:
            if app.config.get("RAG_STARTUP_SYNC_DONE"):
                return None
            app.config["RAG_STARTUP_SYNC_DONE"] = True

        _sync_rag_on_startup()

    initialize_database()

    @app.teardown_appcontext
    def _close_db_on_teardown(_exception=None):
        close_db_connection()

    register_auth_routes(app)
    install_auth_guard(app)
    install_request_security(app)
    register_page_routes(app)
    register_conversation_routes(app)
    register_chat_routes(app)
    register_activity_routes(app)

    _logger.info("All routes registered successfully")
    _logger.info("Application startup complete")
    _logger.info("=" * 60)

    return app


app = create_app()


if __name__ == "__main__":
    from routes import preload_dependencies

    _logger.info("Running in standalone mode...")
    runtime_app = create_app()
    preload_dependencies(runtime_app)
    runtime_app.config["RAG_STARTUP_SYNC_DONE"] = True
    _sync_rag_on_startup()
    _logger.info("Starting Flask server on 0.0.0.0:5000")
    runtime_app.run(host="0.0.0.0", debug=False, use_reloader=False)
