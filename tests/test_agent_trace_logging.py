from __future__ import annotations

import json
import pathlib

import agent


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
ENV_EXAMPLE_PATH = REPO_ROOT / ".env.example"


class _ListLogger:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)


def test_trace_agent_event_includes_raw_payload_when_enabled(monkeypatch) -> None:
    logger = _ListLogger()
    monkeypatch.setattr(agent, "AGENT_TRACE_LOG_ENABLED", True)
    monkeypatch.setattr(agent, "AGENT_TRACE_LOG_INCLUDE_RAW", True)
    monkeypatch.setattr(agent, "_get_agent_trace_logger", lambda: logger)

    agent._trace_agent_event(
        "demo_event",
        trace_id="trace-1",
        content_excerpt="short",
        raw_fields={
            "content": "FULL CONTENT",
            "nested": {"alpha": [1, 2, 3]},
        },
    )

    assert len(logger.messages) == 1
    payload = json.loads(logger.messages[0])
    assert payload["event"] == "demo_event"
    assert payload["trace_id"] == "trace-1"
    assert payload["raw"]["content"] == "FULL CONTENT"
    assert payload["raw"]["nested"]["alpha"] == [1, 2, 3]


def test_trace_agent_event_is_silent_when_disabled(monkeypatch) -> None:
    logger = _ListLogger()
    monkeypatch.setattr(agent, "AGENT_TRACE_LOG_ENABLED", False)
    monkeypatch.setattr(agent, "AGENT_TRACE_LOG_INCLUDE_RAW", True)
    monkeypatch.setattr(agent, "_get_agent_trace_logger", lambda: logger)

    agent._trace_agent_event("disabled_event", raw_fields={"content": "ignored"})

    assert logger.messages == []


def test_append_model_invocation_log_traces_raw_request_and_response_without_sink(monkeypatch) -> None:
    logger = _ListLogger()
    monkeypatch.setattr(agent, "AGENT_TRACE_LOG_ENABLED", True)
    monkeypatch.setattr(agent, "AGENT_TRACE_LOG_INCLUDE_RAW", True)
    monkeypatch.setattr(agent, "_get_agent_trace_logger", lambda: logger)

    agent._append_model_invocation_log(
        None,
        agent_context={"source_message_id": 17, "sub_agent_depth": 1},
        step=2,
        call_type="agent_step",
        retry_reason=None,
        model_target={"api_model": "demo-model", "record": {"provider": "demo-provider"}},
        request_payload={"messages": [{"role": "user", "content": "hello"}]},
        response_summary={"status": "ok", "content_text": "world"},
        operation="chat",
        response_status="ok",
    )

    assert len(logger.messages) == 1
    payload = json.loads(logger.messages[0])
    assert payload["event"] == "model_invocation_recorded"
    assert payload["provider"] == "demo-provider"
    assert payload["api_model"] == "demo-model"
    assert payload["raw"]["request_payload"]["messages"][0]["content"] == "hello"
    assert payload["raw"]["response_summary"]["content_text"] == "world"


def test_trace_agent_stream_payload_logs_event_type_and_full_payload(monkeypatch) -> None:
    logger = _ListLogger()
    monkeypatch.setattr(agent, "AGENT_TRACE_LOG_ENABLED", True)
    monkeypatch.setattr(agent, "AGENT_TRACE_LOG_INCLUDE_RAW", True)
    monkeypatch.setattr(agent, "_get_agent_trace_logger", lambda: logger)

    agent.trace_agent_stream_payload(
        "chat_stream_chunk",
        payload={"type": "answer_delta", "text": "Merhaba"},
        conversation_id=42,
        stream_request_id="run-42",
        step=3,
    )

    assert len(logger.messages) == 1
    payload = json.loads(logger.messages[0])
    assert payload["event"] == "chat_stream_chunk"
    assert payload["event_type"] == "answer_delta"
    assert payload["conversation_id"] == 42
    assert payload["raw"]["payload"]["text"] == "Merhaba"


def test_env_example_documents_trace_logging_flags() -> None:
    env_example = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")

    assert "AGENT_TRACE_LOG_ENABLED" in env_example
    assert "AGENT_TRACE_LOG_INCLUDE_RAW" in env_example
