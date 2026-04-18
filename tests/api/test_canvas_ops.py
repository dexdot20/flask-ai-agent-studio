from __future__ import annotations

import io

import pdfplumber

from canvas_service import find_latest_canvas_documents
from db import get_db, insert_message, serialize_message_metadata


def _seed_canvas_document(app, conversation_id: int, document_id: str = "canvas-edit") -> None:
    metadata = serialize_message_metadata(
        {
            "canvas_documents": [
                {
                    "id": document_id,
                    "title": "Draft",
                    "format": "markdown",
                    "content": "# Draft\n\nInitial",
                }
            ]
        }
    )
    with app.app_context():
        with get_db() as conn:
            insert_message(conn, conversation_id, "assistant", "Here is the draft.", metadata=metadata)


def test_canvas_export_returns_markdown_and_pdf(app, client, create_conversation):
    conversation_id = create_conversation()
    _seed_canvas_document(app, conversation_id, document_id="canvas-export")

    markdown_response = client.get(
        f"/api/conversations/{conversation_id}/canvas/export?format=md&document_id=canvas-export"
    )
    assert markdown_response.status_code == 200
    assert markdown_response.mimetype == "text/markdown"
    assert "# Draft" in markdown_response.get_data(as_text=True)

    pdf_response = client.get(
        f"/api/conversations/{conversation_id}/canvas/export?format=pdf&document_id=canvas-export"
    )
    assert pdf_response.status_code == 200
    assert pdf_response.mimetype == "application/pdf"
    assert pdf_response.data.startswith(b"%PDF")

    with pdfplumber.open(io.BytesIO(pdf_response.data)) as pdf:
        pdf_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    assert "Draft" in pdf_text


def test_canvas_patch_updates_document_content_and_format(app, client, create_conversation):
    conversation_id = create_conversation()
    _seed_canvas_document(app, conversation_id)

    response = client.patch(
        f"/api/conversations/{conversation_id}/canvas",
        json={
            "document_id": "canvas-edit",
            "content": "print('saved')",
            "format": "code",
            "language": "python",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["document"]["format"] == "code"
    assert payload["document"]["language"] == "python"
    assert payload["document"]["content"] == "print('saved')"

    conversation_response = client.get(f"/api/conversations/{conversation_id}")
    messages = conversation_response.get_json()["messages"]
    latest_canvas = find_latest_canvas_documents(messages)
    assert latest_canvas[0]["format"] == "code"


def test_canvas_patch_returns_404_when_document_missing(client, create_conversation):
    conversation_id = create_conversation()

    response = client.patch(
        f"/api/conversations/{conversation_id}/canvas",
        json={"document_id": "missing-doc", "content": "x"},
    )

    assert response.status_code == 404
    assert response.get_json()["error"] == "Canvas document not found."
