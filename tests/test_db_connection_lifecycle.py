from __future__ import annotations

import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from app import create_app
from db import get_db


class DbConnectionLifecycleTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = f"{self.temp_dir.name}/test.db"
        self.login_pin_patcher = patch("config.LOGIN_PIN", "")
        self.login_pin_patcher.start()
        self.app = create_app(database_path=self.db_path)
        self.app.config.update(TESTING=True)

    def tearDown(self) -> None:
        self.login_pin_patcher.stop()
        self.temp_dir.cleanup()

    def test_get_db_reuses_single_connection_per_app_context(self) -> None:
        with self.app.app_context():
            first = get_db()
            second = get_db()
            self.assertIs(first, second)

    def test_cached_connection_closes_on_app_context_teardown(self) -> None:
        with self.app.app_context():
            conn = get_db()
            conn.execute("SELECT 1")

        with self.assertRaises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

        with self.app.app_context():
            fresh = get_db()
            fresh.execute("SELECT 1")
            self.assertIsNot(fresh, conn)
