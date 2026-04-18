from __future__ import annotations

import sqlite3
from unittest.mock import patch

import pytest

from app import create_app
from db import get_db


@pytest.fixture
def app(tmp_path):
    with patch("config.LOGIN_PIN", ""):
        app_instance = create_app(database_path=str(tmp_path / "test.db"))
    app_instance.config.update(TESTING=True)
    return app_instance


def test_get_db_reuses_single_connection_per_app_context(app) -> None:
    with app.app_context():
        first = get_db()
        second = get_db()
        assert first is second


def test_cached_connection_closes_on_app_context_teardown(app) -> None:
    with app.app_context():
        conn = get_db()
        conn.execute("SELECT 1")

    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")

    with app.app_context():
        fresh = get_db()
        fresh.execute("SELECT 1")
        assert fresh is not conn
