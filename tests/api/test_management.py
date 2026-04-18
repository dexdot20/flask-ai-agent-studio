from __future__ import annotations

from unittest.mock import patch

import request_security


def test_conversation_crud_flow(client, create_conversation):
    conversation_id = create_conversation()

    response = client.get("/api/conversations")
    assert response.status_code == 200
    rows = response.get_json()
    assert any(row["id"] == conversation_id for row in rows)

    response = client.patch(
        f"/api/conversations/{conversation_id}",
        json={"title": "Updated Title"},
    )
    assert response.status_code == 200
    assert response.get_json()["title"] == "Updated Title"

    response = client.get(f"/api/conversations/{conversation_id}")
    assert response.status_code == 200
    assert response.get_json()["conversation"]["id"] == conversation_id

    response = client.delete(f"/api/conversations/{conversation_id}")
    assert response.status_code == 204

    response = client.get(f"/api/conversations/{conversation_id}")
    assert response.status_code == 404


def test_persona_crud_and_conversation_persona_override(client):
    analyst_response = client.post(
        "/api/personas",
        json={
            "name": "Analyst",
            "general_instructions": "Focus on evidence.",
            "ai_personality": "Sound analytical.",
        },
    )
    assert analyst_response.status_code == 201
    analyst_persona = analyst_response.get_json()["persona"]

    teacher_response = client.post(
        "/api/personas",
        json={
            "name": "Teacher",
            "general_instructions": "Explain step by step.",
            "ai_personality": "Sound patient.",
        },
    )
    assert teacher_response.status_code == 201
    teacher_persona = teacher_response.get_json()["persona"]

    default_response = client.patch(
        "/api/settings",
        json={"default_persona_id": analyst_persona["id"]},
    )
    assert default_response.status_code == 200

    conversation_response = client.post(
        "/api/conversations",
        json={"title": "Persona Chat", "model": "deepseek-chat"},
    )
    assert conversation_response.status_code == 201
    conversation_id = conversation_response.get_json()["id"]

    override_response = client.patch(
        f"/api/conversations/{conversation_id}",
        json={"persona_id": teacher_persona["id"]},
    )
    assert override_response.status_code == 200
    assert override_response.get_json()["persona_id"] == teacher_persona["id"]

    conversation_payload = client.get(f"/api/conversations/{conversation_id}").get_json()["conversation"]
    assert conversation_payload["persona"]["id"] == teacher_persona["id"]


def test_login_pin_blocks_api_with_401(client):
    with patch("config.LOGIN_PIN", "2468"):
        response = client.get("/api/settings")

    assert response.status_code == 401
    assert response.get_json()["error"] == "Login PIN required."


def test_csrf_guard_blocks_mutation_without_token(app, client, session_csrf_token):
    previous_testing = app.config.get("TESTING", False)
    app.config["TESTING"] = False
    try:
        csrf_token = session_csrf_token
        assert csrf_token

        blocked = client.post(
            "/api/conversations",
            json={"title": "Blocked", "model": "deepseek-chat"},
            headers={"User-Agent": "Werkzeug/3.1.0"},
        )
        assert blocked.status_code == 403

        allowed = client.post(
            "/api/conversations",
            json={"title": "Allowed", "model": "deepseek-chat"},
            headers={"User-Agent": "Werkzeug/3.1.0", "X-CSRF-Token": csrf_token},
        )
        assert allowed.status_code == 201
    finally:
        app.config["TESTING"] = previous_testing


def test_rate_limit_returns_429_even_with_spoofed_forwarded_for(app, client, session_csrf_token):
    previous_testing = app.config.get("TESTING", False)
    previous_request_count = request_security._RATE_LIMIT_REQUEST_COUNT
    app.config["TESTING"] = False
    request_security._RATE_LIMIT_STATE.clear()
    request_security._RATE_LIMIT_REQUEST_COUNT = 0
    try:
        csrf_token = session_csrf_token
        assert csrf_token

        with patch("request_security._get_rate_limit_rule", return_value=("api-write", 1, 60)):
            first = client.post(
                "/api/conversations",
                json={"title": "First", "model": "deepseek-chat"},
                headers={"X-CSRF-Token": csrf_token, "X-Forwarded-For": "1.1.1.1"},
            )
            assert first.status_code == 201

            second = client.post(
                "/api/conversations",
                json={"title": "Second", "model": "deepseek-chat"},
                headers={"X-CSRF-Token": csrf_token, "X-Forwarded-For": "2.2.2.2"},
            )
            assert second.status_code == 429
            assert second.get_json()["error"] == "Too many requests. Please try again shortly."
    finally:
        request_security._RATE_LIMIT_STATE.clear()
        request_security._RATE_LIMIT_REQUEST_COUNT = previous_request_count
        app.config["TESTING"] = previous_testing


def test_update_conversation_title_rejects_blank_values(client, create_conversation):
    conversation_id = create_conversation()

    response = client.patch(
        f"/api/conversations/{conversation_id}",
        json={"title": "   "},
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "Title required."
