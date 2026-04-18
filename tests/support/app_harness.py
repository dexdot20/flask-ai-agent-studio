from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch

import request_security

from app import create_app
from db import get_db, insert_message, serialize_message_metadata
from tests.support.stream_events import build_stream_chunk, build_stream_chunk_openrouter, build_tool_call_chunk


class BaseAppRoutesTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = f"{self.temp_dir.name}/test.db"
        self.image_storage_dir = f"{self.temp_dir.name}/image-store"
        self.login_pin_patcher = patch("config.LOGIN_PIN", "")
        self.login_pin_patcher.start()
        self.app = create_app(database_path=self.db_path)
        self.app.config.update(TESTING=True)
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        self.login_pin_patcher.stop()
        self.temp_dir.cleanup()

    def _create_conversation(self, title: str = "Test Chat") -> int:
        response = self.client.post(
            "/api/conversations",
            json={"title": title, "model": "deepseek-chat"},
        )
        self.assertEqual(response.status_code, 201)
        return response.get_json()["id"]

    def assert_json_ok(self, response, status_code: int = 200) -> dict:
        self.assertEqual(response.status_code, status_code)
        payload = response.get_json()
        self.assertIsInstance(payload, dict)
        return payload

    def get_session_csrf_token(self) -> str:
        with self.client.session_transaction() as session_data:
            return str(session_data.get(request_security.CSRF_TOKEN_SESSION_KEY) or "")

    def assert_mapping_subset(self, actual: dict, expected: dict) -> None:
        self.assertIsInstance(actual, dict)
        for key, value in expected.items():
            self.assertIn(key, actual)
            self.assertEqual(actual[key], value)

    def assert_keys_present(self, actual: dict, keys: list[str]) -> None:
        self.assertIsInstance(actual, dict)
        for key in keys:
            self.assertIn(key, actual)

    def _insert_pending_clarification_assistant(
        self,
        conversation_id: int,
        *,
        text: str = "Let me clarify a few details.",
        questions: list[dict] | None = None,
    ) -> int:
        normalized_questions = questions or [
            {
                "id": "budget",
                "label": "Budget?",
                "input_type": "text",
                "required": True,
            }
        ]
        with self.app.app_context():
            with get_db() as conn:
                return insert_message(
                    conn,
                    conversation_id,
                    "assistant",
                    text,
                    metadata=serialize_message_metadata(
                        {
                            "pending_clarification": {
                                "questions": normalized_questions,
                                "submit_label": "Send answers",
                            }
                        }
                    ),
                )

    @staticmethod
    def _stream_chunk(*args, **kwargs):
        return build_stream_chunk(*args, **kwargs)

    @staticmethod
    def _stream_chunk_openrouter(*args, **kwargs):
        return build_stream_chunk_openrouter(*args, **kwargs)

    @staticmethod
    def _tool_call_chunk(*args, **kwargs):
        return build_tool_call_chunk(*args, **kwargs)
