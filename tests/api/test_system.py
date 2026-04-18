from __future__ import annotations

import io


def test_settings_get_and_patch_roundtrip(client):
    settings_response = client.get("/api/settings")
    assert settings_response.status_code == 200
    payload = settings_response.get_json()
    assert "activity_enabled" in payload
    assert "activity_retention_days" in payload

    patch_response = client.patch(
        "/api/settings",
        json={"activity_enabled": False, "activity_retention_days": 45},
    )
    assert patch_response.status_code == 200
    updated = patch_response.get_json()
    assert updated["activity_enabled"] is False
    assert updated["activity_retention_days"] == 45


def test_rag_endpoints_support_manual_document_ingest(client):
    list_response = client.get("/api/rag/documents")
    assert list_response.status_code == 200

    ingest_response = client.post(
        "/api/rag/ingest",
        data={
            "document": (io.BytesIO(b"Alpha\nBeta\nGamma"), "ops-notes.txt", "text/plain"),
            "source_name": "Ops Notes",
            "description": "Use when answering operations questions.",
            "auto_inject_enabled": "false",
        },
        content_type="multipart/form-data",
    )
    assert ingest_response.status_code == 201
    ingest_payload = ingest_response.get_json()
    assert ingest_payload["file_name"] == "ops-notes.txt"
    assert ingest_payload["document"]["source_type"] == "uploaded_document"
    assert ingest_payload["document"]["chunk_count"] > 0

    list_after = client.get("/api/rag/documents")
    assert list_after.status_code == 200
    documents = list_after.get_json()
    assert len(documents) == 1
    assert documents[0]["metadata"]["description"] == "Use when answering operations questions."


def test_settings_patch_rejects_invalid_activity_retention_days(client):
    response = client.patch("/api/settings", json={"activity_retention_days": 0})

    assert response.status_code == 400
    assert response.get_json()["error"] == "activity_retention_days must be between 1 and 3650."


def test_manual_summarize_returns_404_for_missing_conversation(client):
    response = client.post(
        "/api/conversations/999999/summarize",
        json={"force": True},
    )

    assert response.status_code == 404
    assert response.get_json()["error"] == "Not found."
