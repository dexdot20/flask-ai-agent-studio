from datetime import timedelta
from threading import Lock

from flask import Flask

import config


_RAG_STARTUP_SYNC_LOCK = Lock()


def _sync_rag_on_startup() -> None:
    if not config.RAG_ENABLED:
        return
    from rag_service import sync_conversations_to_rag_safe

    sync_conversations_to_rag_safe()


def create_app(database_path: str | None = None, *, load_persisted_runtime_settings: bool = True) -> Flask:
    resolved_database_path = str(database_path or config.DB_PATH).strip() or config.DB_PATH
    if load_persisted_runtime_settings:
        config.apply_persisted_runtime_settings(resolved_database_path)
        config.propagate_runtime_settings_to_loaded_modules()

    from db import configure_db_path, initialize_database
    from routes import (
        install_auth_guard,
        register_auth_routes,
        register_chat_routes,
        register_conversation_routes,
        register_page_routes,
    )

    resolved_database_path = configure_db_path(resolved_database_path)

    app = Flask(__name__)
    app.config["DATABASE_PATH"] = resolved_database_path
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=config.LOGIN_REMEMBER_SESSION_DAYS)

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
    register_auth_routes(app)
    install_auth_guard(app)
    register_page_routes(app)
    register_conversation_routes(app)
    register_chat_routes(app)

    return app


app = create_app(load_persisted_runtime_settings=False)


if __name__ == "__main__":
    from routes import preload_dependencies

    runtime_app = create_app()
    preload_dependencies(runtime_app)
    runtime_app.config["RAG_STARTUP_SYNC_DONE"] = True
    _sync_rag_on_startup()
    runtime_app.run(host="0.0.0.0", debug=True, use_reloader=False)
