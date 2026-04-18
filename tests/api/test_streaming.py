from __future__ import annotations

from unittest.mock import patch

from db import get_db
from tests.support.api_helpers import parse_ndjson


def test_chat_stream_answer_delta_and_done_are_json_events(client, create_conversation):
    conversation_id = create_conversation()
    fake_events = iter(
        [
            {"type": "answer_start"},
            {"type": "answer_delta", "text": "Merhaba "},
            {"type": "answer_delta", "text": "dünya"},
            {"type": "tool_capture", "tool_results": []},
            {"type": "done"},
        ]
    )

    with patch("routes.chat.run_agent_stream", return_value=fake_events):
        response = client.post(
            "/chat",
            json={
                "conversation_id": conversation_id,
                "model": "deepseek-chat",
                "user_content": "Selam",
                "messages": [{"role": "user", "content": "Selam"}],
            },
        )

    assert response.status_code == 200
    events = parse_ndjson(response)
    event_types = [event["type"] for event in events]
    assert "answer_delta" in event_types
    assert "done" in event_types
    assert "message_ids" in event_types


def test_chat_stream_tool_history_emits_tool_call_and_persists_rows(client, create_conversation):
    conversation_id = create_conversation()
    fake_events = iter(
        [
            {"type": "step_started", "step": 1, "max_steps": 2},
            {
                "type": "tool_history",
                "step": 1,
                "messages": [
                    {
                        "role": "assistant",
                        "content": "Önce arama yapıyorum.",
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "type": "function",
                                "function": {
                                    "name": "search_web",
                                    "arguments": '{"queries":["istanbul"]}',
                                },
                            }
                        ],
                    },
                    {
                        "role": "tool",
                        "tool_call_id": "call-1",
                        "content": '{"ok":true,"results":[{"title":"Istanbul"}]}',
                    },
                ],
            },
            {"type": "answer_start"},
            {"type": "answer_delta", "text": "Sonuçlar hazır."},
            {"type": "tool_capture", "tool_results": []},
            {"type": "done"},
        ]
    )

    with patch("routes.chat.run_agent_stream", return_value=fake_events):
        response = client.post(
            "/chat",
            json={
                "conversation_id": conversation_id,
                "model": "deepseek-chat",
                "user_content": "İstanbul nedir?",
                "messages": [{"role": "user", "content": "İstanbul nedir?"}],
            },
        )

    assert response.status_code == 200
    events = parse_ndjson(response)
    tool_history_event = next((event for event in events if event["type"] == "assistant_tool_history"), None)
    assert tool_history_event is not None
    assert len(tool_history_event["messages"]) == 2

    with get_db() as conn:
        rows = conn.execute(
            "SELECT role, content, tool_calls, tool_call_id FROM messages WHERE conversation_id = ? ORDER BY id",
            (conversation_id,),
        ).fetchall()

    assert [row["role"] for row in rows] == ["user", "assistant", "tool", "assistant"]
    assert "search_web" in str(rows[1]["tool_calls"] or "")
    assert rows[2]["tool_call_id"] == "call-1"


def test_chat_rejects_invalid_model(client, create_conversation):
    conversation_id = create_conversation()

    response = client.post(
        "/chat",
        json={
            "conversation_id": conversation_id,
            "model": "invalid-model",
            "user_content": "Selam",
            "messages": [{"role": "user", "content": "Selam"}],
        },
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "Invalid model."
