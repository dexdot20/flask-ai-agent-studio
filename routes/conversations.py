from __future__ import annotations

from datetime import datetime
import json
import os
import re

from flask import Response, current_app, jsonify, request

from canvas_service import (
    build_html_download,
    build_markdown_download,
    build_pdf_download,
    clear_canvas,
    create_canvas_document,
    create_canvas_runtime_state,
    delete_canvas_document,
    find_latest_canvas_document,
    find_latest_canvas_state,
    get_canvas_runtime_active_document_id,
    get_canvas_runtime_documents,
    rewrite_canvas_document,
)
from conversation_cleanup_service import (
    delete_conversation_workspace,
    purge_conversation_rag_sources,
    rollback_conversation_branch,
)
from conversation_export import (
    build_conversation_docx_download,
    build_conversation_json_download,
    build_conversation_markdown_download,
    build_conversation_pdf_download,
)
from config import (
    CONVERSATION_MEMORY_ENABLED,
    RAG_DISABLED_FEATURE_ERROR,
    RAG_ENABLED,
    RAG_SEARCH_DEFAULT_TOP_K,
)
from db import (
    create_persona,
    delete_persona,
    delete_conversation_file_assets,
    delete_conversation_memory_entry,
    delete_persona_memory_entry,
    delete_conversation_image_assets,
    delete_conversation_video_assets,
    extract_message_attachments,
    extract_sub_agent_traces,
    get_app_settings,
    get_default_persona_id,
    get_persona,
    get_pruning_batch_size,
    get_pruning_token_threshold,
    get_conversation_persona,
    get_persona_memory,
    get_persona_memory_entry,
    get_rag_source_types,
    get_conversation_message_rows,
    get_conversation_messages,
    get_db,
    insert_message,
    insert_conversation_memory_entry,
    insert_persona_memory_entry,
    get_conversation_memory,
    get_conversation_memory_entry,
    list_conversation_model_invocations,
    message_row_to_dict,
    normalize_rag_source_types,
    normalize_active_tool_names,
    parse_message_metadata,
    parse_message_tool_calls,
    read_image_asset_bytes,
    revert_conversation_state_mutations,
    sanitize_edited_user_message_metadata,
    serialize_message_metadata,
    list_personas,
    update_conversation_memory_entry,
    update_persona_memory_entry,
    update_persona,
)
from doc_service import build_canvas_markdown, extract_document_text, infer_canvas_format, infer_canvas_language, read_uploaded_document
from github_import_service import import_github_repository_into_canvas
from model_registry import (
    DEEPSEEK_PROVIDER,
    apply_model_target_request_options,
    can_model_use_structured_outputs,
    get_default_chat_model_id,
    normalize_chat_parameter_overrides,
    get_model_label,
    get_operation_model,
    get_provider_client,
    resolve_model_target,
)
from prune_service import prune_message, prune_conversation_batch, score_conversation_messages_for_prune
from rag import delete_source as rag_delete_source
from rag_service import (
    delete_rag_document_record,
    ensure_supported_rag_sources,
    get_rag_document_record,
    ingest_uploaded_rag_document,
    list_rag_documents_db,
    search_knowledge_base_tool,
    sync_conversations_to_rag_background,
    sync_conversations_to_rag_safe,
    sync_conversations_to_rag,
)
from routes.request_utils import is_valid_model_id, normalize_model_id
from image_utils import extract_json_object, extract_text_from_response_content

client = get_provider_client(DEEPSEEK_PROVIDER)


def _deserialize_parameter_overrides(raw_value) -> dict | None:
    if raw_value in (None, ""):
        return None
    try:
        return normalize_chat_parameter_overrides(raw_value)
    except ValueError:
        return None


def _sanitize_download_filename(value: str, fallback: str = "canvas") -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip("-._")
    return normalized[:80] or fallback


def _load_conversation_payload(conv_id: int, include_private_metadata: bool = False):
    with get_db() as conn:
        conversation = conn.execute(
            "SELECT * FROM conversations WHERE id = ?",
            (conv_id,),
        ).fetchone()
        if not conversation:
            return None, None
        messages = [
            message_row_to_dict(message, include_private_metadata=include_private_metadata)
            for message in get_conversation_message_rows(conn, conv_id)
        ]
    return conversation, messages


def _normalize_export_reasoning_map(value) -> dict[int, str]:
    source = value if isinstance(value, dict) else {}
    cleaned: dict[int, str] = {}
    for raw_message_id, raw_reasoning in list(source.items())[:500]:
        try:
            message_id = int(raw_message_id)
        except (TypeError, ValueError):
            continue
        if message_id <= 0:
            continue
        reasoning_text = str(raw_reasoning or "").strip()
        if not reasoning_text:
            continue
        cleaned[message_id] = reasoning_text[:20_000]
    return cleaned


def _apply_export_reasoning_map(messages: list[dict] | None, reasoning_by_message_id: dict[int, str]) -> list[dict]:
    if not reasoning_by_message_id:
        return list(messages or [])

    merged_messages = []
    for message in messages or []:
        if not isinstance(message, dict):
            continue

        next_message = dict(message)
        role = str(next_message.get("role") or "").strip()
        message_id = int(next_message.get("id") or 0)
        fallback_reasoning = reasoning_by_message_id.get(message_id, "")
        metadata = next_message.get("metadata") if isinstance(next_message.get("metadata"), dict) else {}

        if role == "assistant" and fallback_reasoning and not str(metadata.get("reasoning_content") or "").strip():
            next_metadata = dict(metadata)
            next_metadata["reasoning_content"] = fallback_reasoning
            next_message["metadata"] = next_metadata

        merged_messages.append(next_message)

    return merged_messages


def _load_conversation_memory_payload(conv_id: int, limit: int = 200) -> dict:
    memory_entries = get_conversation_memory(conv_id, limit=limit)
    return {
        "conversation_memory_enabled": CONVERSATION_MEMORY_ENABLED,
        "memory": memory_entries,
        "memory_count": len(memory_entries),
    }


def _load_persona_memory_payload(persona_id: int, limit: int = 200) -> dict:
    memory_entries = get_persona_memory(persona_id, limit=limit)
    return {
        "persona_id": persona_id,
        "persona_memory": memory_entries,
        "persona_memory_count": len(memory_entries),
    }


def _build_persona_response_payload(**extra) -> dict:
    return {
        "personas": list_personas(),
        "default_persona_id": get_default_persona_id(),
        **extra,
    }


def _parse_truthy_form_value(value, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_optional_int(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resolve_initial_conversation_title(
    data: dict,
    persona_id: int | None,
) -> tuple[str, str, bool]:
    title_provided = "title" in data
    raw_title = str(data.get("title") or "").strip()[:120]
    normalized_title = raw_title or "New Chat"

    if title_provided and normalized_title and normalized_title != "New Chat":
        return normalized_title, "manual", True

    if persona_id is not None:
        persona = get_persona(persona_id)
        persona_name = str((persona or {}).get("name") or "").strip()[:120]
        if persona_name:
            return persona_name, "persona", False

    return "New Chat", "system", False


def _parse_message_id_list(raw_value, *, limit: int = 50) -> list[int] | None:
    if not isinstance(raw_value, list):
        return None

    normalized_ids: list[int] = []
    seen_ids: set[int] = set()
    for raw_message_id in raw_value:
        try:
            message_id = int(raw_message_id)
        except (TypeError, ValueError):
            return None
        if message_id <= 0 or message_id in seen_ids:
            continue
        normalized_ids.append(message_id)
        seen_ids.add(message_id)
        if len(normalized_ids) > limit:
            return None
    return normalized_ids


def _mark_sub_agent_trace_canvas_saved(
    conn,
    *,
    conversation_id: int,
    assistant_message_id: int | None,
    trace_index: int | None,
    canvas_document: dict,
) -> bool:
    if assistant_message_id is None or trace_index is None or trace_index < 0:
        return False

    row = conn.execute(
        """SELECT id, conversation_id, role, metadata, deleted_at
           FROM messages WHERE id = ?""",
        (assistant_message_id,),
    ).fetchone()
    if not row or row["deleted_at"] is not None:
        return False
    if int(row["conversation_id"] or 0) != conversation_id:
        return False
    if str(row["role"] or "").strip() != "assistant":
        return False

    metadata = parse_message_metadata(row["metadata"])
    sub_agent_traces = extract_sub_agent_traces(metadata)
    if trace_index >= len(sub_agent_traces):
        return False

    updated_trace = dict(sub_agent_traces[trace_index])
    updated_trace["canvas_saved"] = True
    updated_trace["canvas_document_id"] = str(canvas_document.get("id") or "").strip()
    updated_trace["canvas_document_title"] = str(canvas_document.get("title") or "").strip()
    sub_agent_traces[trace_index] = updated_trace
    metadata["sub_agent_traces"] = sub_agent_traces

    conn.execute(
        "UPDATE messages SET metadata = ? WHERE id = ?",
        (serialize_message_metadata(metadata), assistant_message_id),
    )
    return True


def _build_sub_agent_canvas_content(title: str, trace: dict | None, fallback_content: str = "") -> str:
    cleaned_title = str(title or "Research").strip() or "Research"
    sections = [f"# {cleaned_title}", ""]

    summary = str(trace.get("summary") or "").strip() if isinstance(trace, dict) else ""
    if summary:
        sections.extend(["## Summary", "", summary, ""])
    else:
        fallback_note = str(trace.get("fallback_note") or "").strip() if isinstance(trace, dict) else ""
        if fallback_note:
            sections.extend(["## Note", "", fallback_note, ""])
        else:
            error_text = str(trace.get("error") or "").strip() if isinstance(trace, dict) else ""
            if error_text:
                sections.extend(["## Error", "", error_text, ""])

    cleaned_content = "\n".join(sections).strip()
    if cleaned_content:
        return cleaned_content
    return str(fallback_content or "").strip()


def _parse_rag_source_type_filter(raw_value):
    if raw_value is None:
        return None, []

    if isinstance(raw_value, list):
        values = raw_value
    elif isinstance(raw_value, str):
        stripped = raw_value.strip()
        if not stripped:
            values = []
        else:
            try:
                parsed = json.loads(stripped)
            except Exception:
                parsed = [part.strip() for part in stripped.split(",") if part.strip()]
            values = parsed if isinstance(parsed, list) else [stripped]
    else:
        values = [raw_value]

    incoming = []
    for value in values:
        raw_text = str(value or "").strip().lower()
        if not raw_text:
            continue
        if "," in raw_text:
            incoming.extend(part.strip() for part in raw_text.split(",") if part.strip())
        else:
            incoming.append(raw_text)
    normalized = normalize_rag_source_types(incoming)
    invalid = [value for value in incoming if value not in normalized]
    return normalized, invalid


def _normalize_upload_metadata_title(raw_title: str) -> str:
    text = re.sub(r"\s+", " ", str(raw_title or "").replace("\n", " ")).strip()
    if not text:
                return ""
    text = re.sub(r"^[\s\-*>#`\"'“”‘’\[\](){}:;,.!?]+", "", text)
    text = re.sub(r"[\s\-*>#`\"'“”‘’\[\](){}:;,.!?]+$", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:80]


def _normalize_upload_metadata_description(raw_description: str) -> str:
    text = re.sub(r"\s+", " ", str(raw_description or "").replace("\n", " ")).strip()
    return text[:280]


def _build_upload_metadata_fallback(filename: str, source_name: str, text: str) -> tuple[str, str]:
    stem = os.path.splitext(os.path.basename(filename or "").strip())[0].strip()
    fallback_title = (
        _normalize_upload_metadata_title(source_name)
        or _normalize_upload_metadata_title(stem.replace("_", " ").replace("-", " "))
        or "Imported document"
    )
    snippet = ""
    for paragraph in re.split(r"\n{2,}", str(text or "").strip()):
        paragraph = re.sub(r"\s+", " ", paragraph).strip()
        if paragraph:
            snippet = paragraph
            break
    if snippet:
        snippet = snippet[:220].rstrip()
        if len(snippet) == 220:
            snippet += "…"
    fallback_description = snippet or f"Document imported from {os.path.basename(filename or 'uploaded file') or 'uploaded file'}."
    return fallback_title, fallback_description


def _generate_upload_metadata_suggestion(filename: str, mime_type: str, text: str, source_name: str = "", description: str = "") -> dict:
    cleaned_filename = os.path.basename(str(filename or "uploaded.txt").strip()) or "uploaded.txt"
    cleaned_source_name = _normalize_upload_metadata_title(source_name)
    cleaned_description = _normalize_upload_metadata_description(description)
    cleaned_text = re.sub(r"\n{3,}", "\n\n", str(text or "").strip())
    excerpt_limit = 14000
    excerpt = cleaned_text[:excerpt_limit]
    excerpt_truncated = len(cleaned_text) > excerpt_limit

    prompt = [
        {
            "role": "system",
            "content": (
                "You generate concise metadata for a knowledge base upload. "
                "Return ONLY valid JSON with keys title and description. "
                "Title must be 3-8 words, specific, and have no trailing punctuation. "
                "Description must be 1-2 sentences, under 280 characters, and explain what the document is useful for. "
                "Match the document language when clear. Do not mention that you are an AI."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Filename: {cleaned_filename}\n"
                f"Mime type: {mime_type or 'text/plain'}\n"
                f"User title hint: {cleaned_source_name or '(none)'}\n"
                f"User description hint: {cleaned_description or '(none)'}\n"
                f"Content truncated: {'yes' if excerpt_truncated else 'no'}\n\n"
                f"Document content:\n{excerpt or '(no extracted text available)'}"
            ),
        },
    ]

    used_ai = False
    raw_output = ""
    try:
        settings = get_app_settings()
        model_id = get_operation_model(
            "upload_metadata",
            settings,
            fallback_model_id=get_default_chat_model_id(settings),
        )
        target = resolve_model_target(model_id, settings)
        request_kwargs = {
            "model": target["api_model"],
            "messages": prompt,
            "temperature": 0.2,
        }
        if can_model_use_structured_outputs(model_id, settings):
            request_kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "upload_metadata",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "title": {
                                "type": "string",
                                "description": "Concise 3-8 word document title without trailing punctuation.",
                            },
                            "description": {
                                "type": "string",
                                "description": "One or two short sentences under 280 characters describing the document's value.",
                            },
                        },
                        "required": ["title", "description"],
                        "additionalProperties": False,
                    },
                },
            }

        request_kwargs = apply_model_target_request_options(request_kwargs, target)
        response = target["client"].chat.completions.create(**request_kwargs)
        used_ai = True
        choice = response.choices[0] if getattr(response, "choices", None) else None
        message = getattr(choice, "message", None) if choice else None
        raw_output = extract_text_from_response_content(getattr(message, "content", ""))
    except Exception:
        used_ai = False
        model_id = get_default_chat_model_id(get_app_settings())

    parsed = extract_json_object(raw_output) if raw_output else {}
    title = _normalize_upload_metadata_title(parsed.get("title") or "")
    description_text = _normalize_upload_metadata_description(parsed.get("description") or "")

    fallback_title, fallback_description = _build_upload_metadata_fallback(cleaned_filename, cleaned_source_name, cleaned_text)
    if not title:
        title = fallback_title
    if not description_text:
        description_text = fallback_description

    return {
        "title": title,
        "description": description_text,
        "used_ai": used_ai,
        "model": model_id,
    }


def register_conversation_routes(app) -> None:
    @app.route("/api/conversations", methods=["GET"])
    def list_conversations():
        with get_db() as conn:
            rows = conn.execute(
                """
                SELECT c.id, c.title, c.title_source, c.title_overridden, c.tool_overrides, c.parameter_overrides, c.model, c.persona_id,
                                             p.name AS persona_name, c.updated_at,
                       COUNT(m.id) AS message_count
                FROM conversations c
                                    LEFT JOIN personas p ON p.id = c.persona_id
                  LEFT JOIN messages m ON m.conversation_id = c.id AND m.deleted_at IS NULL
                GROUP BY c.id
                ORDER BY c.updated_at DESC
                """
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            tool_overrides_raw = item.get("tool_overrides")
            if tool_overrides_raw:
                try:
                    item["tool_overrides"] = json.loads(tool_overrides_raw)
                except Exception:
                    item["tool_overrides"] = None
            else:
                item["tool_overrides"] = None
            item["parameter_overrides"] = _deserialize_parameter_overrides(item.get("parameter_overrides"))
            result.append(item)
        return jsonify(result)

    @app.route("/api/personas", methods=["GET"])
    def list_personas_route():
        return jsonify(_build_persona_response_payload())

    @app.route("/api/personas", methods=["POST"])
    def create_persona_route():
        data = request.get_json(silent=True) or {}
        name = data.get("name")
        general_instructions = data.get("general_instructions")
        ai_personality = data.get("ai_personality")

        if not isinstance(name, str):
            return jsonify({"error": "Persona name is required."}), 400
        if general_instructions is not None and not isinstance(general_instructions, str):
            return jsonify({"error": "general_instructions must be a string."}), 400
        if ai_personality is not None and not isinstance(ai_personality, str):
            return jsonify({"error": "ai_personality must be a string."}), 400

        try:
            persona = create_persona(
                name,
                general_instructions=general_instructions or "",
                ai_personality=ai_personality or "",
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        return jsonify(_build_persona_response_payload(persona=persona)), 201

    @app.route("/api/personas/<int:persona_id>", methods=["PATCH"])
    def update_persona_route(persona_id):
        data = request.get_json(silent=True) or {}
        if not any(key in data for key in ("name", "general_instructions", "ai_personality")):
            return jsonify({"error": "No persona fields provided."}), 400

        name = data.get("name") if "name" in data else None
        general_instructions = data.get("general_instructions") if "general_instructions" in data else None
        ai_personality = data.get("ai_personality") if "ai_personality" in data else None

        if name is not None and not isinstance(name, str):
            return jsonify({"error": "name must be a string."}), 400
        if general_instructions is not None and not isinstance(general_instructions, str):
            return jsonify({"error": "general_instructions must be a string."}), 400
        if ai_personality is not None and not isinstance(ai_personality, str):
            return jsonify({"error": "ai_personality must be a string."}), 400

        try:
            persona = update_persona(
                persona_id,
                name=name,
                general_instructions=general_instructions,
                ai_personality=ai_personality,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        if not persona:
            return jsonify({"error": "Persona not found."}), 404

        return jsonify(_build_persona_response_payload(persona=persona))

    @app.route("/api/personas/<int:persona_id>", methods=["DELETE"])
    def delete_persona_route(persona_id):
        deleted = delete_persona(persona_id)
        if not deleted:
            return jsonify({"error": "Persona not found."}), 404
        return jsonify(_build_persona_response_payload(deleted_persona_id=persona_id))

    @app.route("/api/personas/<int:persona_id>/memory", methods=["GET"])
    def list_persona_memory_route(persona_id):
        persona = get_persona(persona_id)
        if not persona:
            return jsonify({"error": "Persona not found."}), 404
        payload = _load_persona_memory_payload(persona_id)
        payload["persona"] = persona
        return jsonify(payload)

    @app.route("/api/personas/<int:persona_id>/memory", methods=["POST"])
    def create_persona_memory_route(persona_id):
        persona = get_persona(persona_id)
        if not persona:
            return jsonify({"error": "Persona not found."}), 404

        data = request.get_json(silent=True) or {}
        key = str(data.get("key") or "").strip()
        value = str(data.get("value") or "").strip()
        message_id = _parse_optional_int(data.get("message_id"))

        try:
            entry = insert_persona_memory_entry(
                persona_id,
                key,
                value,
                message_id=message_id,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        with get_db() as conn:
            conn.execute(
                "UPDATE personas SET updated_at = datetime('now') WHERE id = ?",
                (persona_id,),
            )

        payload = _load_persona_memory_payload(persona_id)
        payload.update({"entry": entry, "persona": get_persona(persona_id)})
        return jsonify(payload), 201

    @app.route("/api/personas/<int:persona_id>/memory/<int:entry_id>", methods=["PATCH"])
    def update_persona_memory_route(persona_id, entry_id):
        persona = get_persona(persona_id)
        if not persona:
            return jsonify({"error": "Persona not found."}), 404

        data = request.get_json(silent=True) or {}
        current_entry = get_persona_memory_entry(entry_id, persona_id)
        if not current_entry:
            return jsonify({"error": "Memory entry not found."}), 404

        key = str(data.get("key") or current_entry["key"]).strip()
        value = str(data.get("value") or current_entry["value"]).strip()
        message_id = _parse_optional_int(data.get("message_id"))
        if message_id is None:
            message_id = current_entry["message_id"]

        try:
            entry = update_persona_memory_entry(
                entry_id,
                persona_id,
                key,
                value,
                message_id=message_id,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        if not entry:
            return jsonify({"error": "Memory entry not found."}), 404

        with get_db() as conn:
            conn.execute(
                "UPDATE personas SET updated_at = datetime('now') WHERE id = ?",
                (persona_id,),
            )

        payload = _load_persona_memory_payload(persona_id)
        payload.update({"entry": entry, "persona": get_persona(persona_id)})
        return jsonify(payload)

    @app.route("/api/personas/<int:persona_id>/memory/<int:entry_id>", methods=["DELETE"])
    def delete_persona_memory_route(persona_id, entry_id):
        persona = get_persona(persona_id)
        if not persona:
            return jsonify({"error": "Persona not found."}), 404

        deleted = delete_persona_memory_entry(entry_id, persona_id)
        if not deleted:
            return jsonify({"error": "Memory entry not found."}), 404

        with get_db() as conn:
            conn.execute(
                "UPDATE personas SET updated_at = datetime('now') WHERE id = ?",
                (persona_id,),
            )

        payload = _load_persona_memory_payload(persona_id)
        payload.update({"deleted_entry_id": entry_id, "persona": get_persona(persona_id)})
        return jsonify(payload)

    @app.route("/api/conversations", methods=["POST"])
    def create_conversation():
        data = request.get_json(silent=True) or {}
        raw_persona_id = data.get("persona_id") if "persona_id" in data else None
        persona_id = _parse_optional_int(raw_persona_id)
        settings = get_app_settings()
        model = normalize_model_id(data.get("model"), default=get_default_chat_model_id(settings))
        if not is_valid_model_id(model):
            return jsonify({"error": "Invalid model."}), 400
        if raw_persona_id not in (None, "") and persona_id is None:
            return jsonify({"error": "persona_id must be an integer or empty."}), 400
        if persona_id is not None and get_persona(persona_id) is None:
            return jsonify({"error": "Persona not found."}), 400

        title, title_source, title_overridden = _resolve_initial_conversation_title(data, persona_id)

        with get_db() as conn:
            cursor = conn.execute(
                "INSERT INTO conversations (title, title_source, title_overridden, model, persona_id) VALUES (?, ?, ?, ?, ?)",
                (title, title_source, 1 if title_overridden else 0, model, persona_id),
            )
            conversation_id = cursor.lastrowid
        if RAG_ENABLED:
            sync_conversations_to_rag_safe(conversation_id=conversation_id)
        return jsonify({
            "id": conversation_id,
            "title": title,
            "title_source": title_source,
            "title_overridden": title_overridden,
            "model": model,
            "persona_id": persona_id,
            "model_label": get_model_label(model, settings),
        }), 201

    @app.route("/api/conversations/<int:conv_id>", methods=["GET"])
    def get_conversation(conv_id):
        conversation, messages = _load_conversation_payload(conv_id)
        if not conversation:
            return jsonify({"error": "Not found."}), 404
        settings = get_app_settings()
        conversation_payload = dict(conversation)
        conversation_payload["model_label"] = get_model_label(conversation_payload.get("model") or "", settings)
        conversation_payload["persona"] = get_conversation_persona(conv_id)
        tool_overrides_raw = conversation_payload.get("tool_overrides")
        if tool_overrides_raw:
            try:
                conversation_payload["tool_overrides"] = json.loads(tool_overrides_raw)
            except Exception:
                conversation_payload["tool_overrides"] = None
        else:
            conversation_payload["tool_overrides"] = None
        conversation_payload["parameter_overrides"] = _deserialize_parameter_overrides(
            conversation_payload.get("parameter_overrides")
        )
        return jsonify(
            {
                "conversation": conversation_payload,
                "messages": messages,
                **_load_conversation_memory_payload(conv_id),
            }
        )

    @app.route("/api/conversations/<int:conv_id>/memory", methods=["POST"])
    def create_conversation_memory_entry(conv_id):
        if not CONVERSATION_MEMORY_ENABLED:
            return jsonify({"error": "Conversation memory is disabled."}), 400

        data = request.get_json(silent=True) or {}
        conversation, _ = _load_conversation_payload(conv_id)
        if not conversation:
            return jsonify({"error": "Not found."}), 404

        entry_type = str(data.get("entry_type") or "").strip()
        key = str(data.get("key") or "").strip()
        value = str(data.get("value") or "").strip()
        message_id = _parse_optional_int(data.get("message_id"))

        try:
            entry = insert_conversation_memory_entry(
                conv_id,
                entry_type,
                key,
                value,
                message_id=message_id,
                mutation_context={"source_message_id": message_id},
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        with get_db() as conn:
            conn.execute(
                "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
                (conv_id,),
            )

        payload = _load_conversation_memory_payload(conv_id)
        payload.update({"entry": entry})
        return jsonify(payload), 201

    @app.route("/api/conversations/<int:conv_id>/memory/<int:entry_id>", methods=["PATCH"])
    def update_conversation_memory(conv_id, entry_id):
        if not CONVERSATION_MEMORY_ENABLED:
            return jsonify({"error": "Conversation memory is disabled."}), 400

        data = request.get_json(silent=True) or {}
        conversation, _ = _load_conversation_payload(conv_id)
        if not conversation:
            return jsonify({"error": "Not found."}), 404

        current_entry = get_conversation_memory_entry(entry_id, conv_id)
        if not current_entry:
            return jsonify({"error": "Memory entry not found."}), 404

        entry_type = str(data.get("entry_type") or current_entry["entry_type"]).strip()
        key = str(data.get("key") or current_entry["key"]).strip()
        value = str(data.get("value") or current_entry["value"]).strip()
        message_id = _parse_optional_int(data.get("message_id"))
        if message_id is None:
            message_id = current_entry["message_id"]

        try:
            entry = update_conversation_memory_entry(
                entry_id,
                conv_id,
                entry_type,
                key,
                value,
                message_id=message_id,
                mutation_context={"source_message_id": message_id},
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        if not entry:
            return jsonify({"error": "Memory entry not found."}), 404

        with get_db() as conn:
            conn.execute(
                "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
                (conv_id,),
            )

        payload = _load_conversation_memory_payload(conv_id)
        payload.update({"entry": entry})
        return jsonify(payload)

    @app.route("/api/conversations/<int:conv_id>/memory/<int:entry_id>", methods=["DELETE"])
    def delete_conversation_memory(conv_id, entry_id):
        if not CONVERSATION_MEMORY_ENABLED:
            return jsonify({"error": "Conversation memory is disabled."}), 400

        conversation, _ = _load_conversation_payload(conv_id)
        if not conversation:
            return jsonify({"error": "Not found."}), 404

        current_entry = get_conversation_memory_entry(entry_id, conv_id)
        deleted = delete_conversation_memory_entry(
            entry_id,
            conv_id,
            mutation_context={"source_message_id": current_entry.get("message_id") if current_entry else None},
        )
        if not deleted:
            return jsonify({"error": "Memory entry not found."}), 404

        with get_db() as conn:
            conn.execute(
                "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
                (conv_id,),
            )

        payload = _load_conversation_memory_payload(conv_id)
        payload.update({"deleted_entry_id": entry_id})
        return jsonify(payload)

    @app.route("/api/conversations/<int:conv_id>/export", methods=["GET", "POST"])
    def export_conversation(conv_id):
        format_name = str(request.args.get("format") or "md").strip().lower()
        export_request_payload = request.get_json(silent=True) if request.method == "POST" else {}
        reasoning_by_message_id = _normalize_export_reasoning_map(
            (export_request_payload or {}).get("reasoning_by_message_id")
        )
        conversation, messages = _load_conversation_payload(conv_id, include_private_metadata=True)
        if not conversation:
            return jsonify({"error": "Not found."}), 404
        messages = _apply_export_reasoning_map(messages, reasoning_by_message_id)

        base_name = _sanitize_download_filename(conversation["title"] or "conversation", fallback="conversation")
        payload_conversation = dict(conversation)
        try:
            if format_name == "md":
                payload = build_conversation_markdown_download(payload_conversation, messages)
                mime_type = "text/markdown; charset=utf-8"
                filename = f"{base_name}.md"
            elif format_name == "json":
                payload = build_conversation_json_download(
                    payload_conversation,
                    messages,
                    list_conversation_model_invocations(conv_id),
                )
                mime_type = "application/json; charset=utf-8"
                filename = f"{base_name}.json"
            elif format_name == "docx":
                payload = build_conversation_docx_download(payload_conversation, messages)
                mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                filename = f"{base_name}.docx"
            elif format_name == "pdf":
                payload = build_conversation_pdf_download(payload_conversation, messages)
                mime_type = "application/pdf"
                filename = f"{base_name}.pdf"
            else:
                return jsonify({"error": "format must be md, json, docx, or pdf."}), 400
        except Exception:
            app.logger.exception("Failed to export conversation %s as %s", conv_id, format_name)
            return jsonify({"error": "Conversation export failed."}), 500

        return Response(
            payload,
            content_type=mime_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )

    @app.route("/api/conversations/<int:conv_id>/canvas/export", methods=["GET"])
    def export_canvas_document(conv_id):
        format_name = str(request.args.get("format") or "md").strip().lower()
        document_id = str(request.args.get("document_id") or "").strip() or None

        conversation, messages = _load_conversation_payload(conv_id)
        if not conversation:
            return jsonify({"error": "Not found."}), 404

        document = find_latest_canvas_document(messages, document_id=document_id)
        if not document:
            return jsonify({"error": "Canvas document not found."}), 404

        base_name = _sanitize_download_filename(document.get("title") or conversation["title"] or "canvas")
        try:
            if format_name == "md":
                payload = build_markdown_download(document)
                mime_type = "text/markdown; charset=utf-8"
                filename = f"{base_name}.md"
            elif format_name == "html":
                payload = build_html_download(document)
                mime_type = "text/html; charset=utf-8"
                filename = f"{base_name}.html"
            elif format_name == "pdf":
                payload = build_pdf_download(document)
                mime_type = "application/pdf"
                filename = f"{base_name}.pdf"
            else:
                return jsonify({"error": "format must be md, html, or pdf."}), 400
        except Exception:
            app.logger.exception("Failed to export canvas document %s as %s for conversation %s", document_id, format_name, conv_id)
            return jsonify({"error": "Export failed due to an internal error."}), 500

        return Response(
            payload,
            content_type=mime_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    @app.route("/api/conversations/<int:conv_id>/images/<image_id>", methods=["GET"])
    def get_conversation_image_asset(conv_id, image_id):
        conversation, _ = _load_conversation_payload(conv_id)
        if not conversation:
            return jsonify({"error": "Not found."}), 404

        asset, image_bytes = read_image_asset_bytes(image_id, conversation_id=conv_id)
        if not asset or not image_bytes:
            return jsonify({"error": "Image asset not found."}), 404

        return Response(
            image_bytes,
            content_type=str(asset.get("mime_type") or "image/jpeg").strip() or "image/jpeg",
            headers={
                "Content-Disposition": f'inline; filename="{_sanitize_download_filename(asset.get("filename") or image_id, fallback="image")}"',
                "Cache-Control": "private, max-age=3600",
            },
        )

    @app.route("/api/conversations/<int:conv_id>/canvas", methods=["DELETE"])
    def delete_canvas(conv_id):
        clear_all = str(request.args.get("clear_all") or "").strip().lower() in {"1", "true", "yes", "on"}
        document_id = str(request.args.get("document_id") or "").strip() or None
        document_path = str(request.args.get("document_path") or "").strip() or None

        conversation, messages = _load_conversation_payload(conv_id)
        if not conversation:
            return jsonify({"error": "Not found."}), 404

        latest_canvas_state = find_latest_canvas_state(messages)
        runtime_state = create_canvas_runtime_state(
            latest_canvas_state.get("documents"),
            active_document_id=latest_canvas_state.get("active_document_id"),
        )
        current_documents = get_canvas_runtime_documents(runtime_state)
        if not current_documents:
            return jsonify({"error": "Canvas document not found."}), 404

        try:
            if clear_all:
                result = clear_canvas(runtime_state)
            else:
                result = delete_canvas_document(runtime_state, document_id=document_id, document_path=document_path)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 404

        next_documents = get_canvas_runtime_documents(runtime_state)
        metadata = serialize_message_metadata(
            {
                "canvas_documents": next_documents,
                "active_document_id": get_canvas_runtime_active_document_id(runtime_state),
                "canvas_viewports": runtime_state.get("viewports") if isinstance(runtime_state.get("viewports"), dict) else {},
                "canvas_cleared": not next_documents,
            }
        )

        with get_db() as conn:
            insert_message(
                conn,
                conv_id,
                "tool",
                "",
                metadata=metadata,
            )
            conn.execute(
                "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
                (conv_id,),
            )

        if RAG_ENABLED:
            if current_app.testing:
                sync_conversations_to_rag_safe(conversation_id=conv_id)
            else:
                sync_conversations_to_rag_background(current_app._get_current_object(), conversation_id=conv_id)

        _, updated_messages = _load_conversation_payload(conv_id)
        active_document_id = get_canvas_runtime_active_document_id(runtime_state)
        return jsonify(
            {
                "cleared": not next_documents,
                "documents": next_documents,
                "active_document_id": active_document_id,
                "remaining_count": len(next_documents),
                "deleted_document_id": result.get("deleted_id"),
                "messages": updated_messages,
            }
        )

    @app.route("/api/conversations/<int:conv_id>/canvas", methods=["POST"])
    def create_canvas(conv_id):
        uploaded_file = None
        if request.mimetype and request.mimetype.startswith("multipart/form-data"):
            data = request.form or {}
            uploaded_file = request.files.get("file")
        else:
            data = request.get_json(silent=True) or {}

        title = str(data.get("title") or "Canvas").strip() or "Canvas"
        content = str(data.get("content") or "")
        format_name = str(data.get("format") or "").strip() or ""
        language = str(data.get("language") or "").strip() or None
        path = str(data.get("path") or "").strip() or None
        role = str(data.get("role") or "").strip() or None
        project_id = str(data.get("project_id") or "").strip() or None
        workspace_id = str(data.get("workspace_id") or "").strip() or None
        summary = str(data.get("summary") or "").strip() or None
        source_assistant_message_id = _parse_optional_int(data.get("source_assistant_message_id"))
        source_sub_agent_trace_index = _parse_optional_int(data.get("source_sub_agent_trace_index"))

        if uploaded_file and getattr(uploaded_file, "filename", ""):
            try:
                filename, mime_type, doc_bytes = read_uploaded_document(uploaded_file)
                extracted_text = extract_document_text(doc_bytes, mime_type)
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            title = os.path.basename(str(data.get("title") or filename).strip()) or filename
            path = str(data.get("path") or path or filename).strip() or filename
            resolved_format = format_name or infer_canvas_format(title)
            resolved_language = language if language is not None else infer_canvas_language(title)
            if resolved_format == "markdown" and mime_type == "application/pdf":
                content = extracted_text
            else:
                content = build_canvas_markdown(title, extracted_text) if resolved_format == "markdown" else extracted_text
            format_name = resolved_format
            language = resolved_language
        else:
            format_name = format_name or "markdown"

        conversation, messages = _load_conversation_payload(conv_id)
        if not conversation:
            return jsonify({"error": "Not found."}), 404

        source_sub_agent_trace = None
        if source_assistant_message_id is not None and source_sub_agent_trace_index is not None:
            source_message = next(
                (
                    message
                    for message in messages
                    if message.get("id") == source_assistant_message_id and str(message.get("role") or "").strip() == "assistant"
                ),
                None,
            )
            if source_message:
                sub_agent_traces = extract_sub_agent_traces(source_message.get("metadata"))
                if 0 <= source_sub_agent_trace_index < len(sub_agent_traces):
                    source_sub_agent_trace = sub_agent_traces[source_sub_agent_trace_index]

        if source_sub_agent_trace is not None:
            content = _build_sub_agent_canvas_content(title, source_sub_agent_trace, fallback_content=content)

        latest_canvas_state = find_latest_canvas_state(messages)
        runtime_state = create_canvas_runtime_state(
            latest_canvas_state.get("documents"),
            active_document_id=latest_canvas_state.get("active_document_id"),
        )

        try:
            document = create_canvas_document(
                runtime_state,
                title=title,
                content=content,
                format_name=format_name,
                language_name=language,
                path=path,
                role=role,
                summary=summary,
                project_id=project_id,
                workspace_id=workspace_id,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        next_documents = get_canvas_runtime_documents(runtime_state)
        metadata = serialize_message_metadata(
            {
                "canvas_documents": next_documents,
                "active_document_id": get_canvas_runtime_active_document_id(runtime_state),
                "canvas_viewports": runtime_state.get("viewports") if isinstance(runtime_state.get("viewports"), dict) else {},
                "canvas_cleared": not next_documents,
            }
        )

        saved_sub_agent_trace = False
        with get_db() as conn:
            insert_message(
                conn,
                conv_id,
                "tool",
                "",
                metadata=metadata,
            )
            saved_sub_agent_trace = _mark_sub_agent_trace_canvas_saved(
                conn,
                conversation_id=conv_id,
                assistant_message_id=source_assistant_message_id,
                trace_index=source_sub_agent_trace_index,
                canvas_document=document,
            )
            conn.execute(
                "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
                (conv_id,),
            )

        if RAG_ENABLED:
            sync_conversations_to_rag_safe(conversation_id=conv_id)

        _, updated_messages = _load_conversation_payload(conv_id)
        return jsonify(
            {
                "document": document,
                "documents": next_documents,
                "active_document_id": document.get("id"),
                "messages": updated_messages,
                "saved_sub_agent_trace": saved_sub_agent_trace,
            }
        ), 201

    @app.route("/api/conversations/<int:conv_id>/canvas/import-github", methods=["POST"])
    def import_github_canvas(conv_id):
        data = request.get_json(silent=True) or {}
        url = str(data.get("url") or "").strip()
        if not url:
            return jsonify({"error": "GitHub repository URL is required."}), 400

        conversation, messages = _load_conversation_payload(conv_id)
        if not conversation:
            return jsonify({"error": "Not found."}), 404

        latest_canvas_state = find_latest_canvas_state(messages)
        runtime_state = create_canvas_runtime_state(
            latest_canvas_state.get("documents"),
            active_document_id=latest_canvas_state.get("active_document_id"),
        )

        try:
            import_result = import_github_repository_into_canvas(runtime_state, url)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        next_documents = get_canvas_runtime_documents(runtime_state)
        metadata = serialize_message_metadata(
            {
                "canvas_documents": next_documents,
                "active_document_id": get_canvas_runtime_active_document_id(runtime_state),
                "canvas_viewports": runtime_state.get("viewports") if isinstance(runtime_state.get("viewports"), dict) else {},
                "canvas_cleared": not next_documents,
            }
        )

        with get_db() as conn:
            insert_message(
                conn,
                conv_id,
                "tool",
                "",
                metadata=metadata,
            )
            conn.execute(
                "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
                (conv_id,),
            )

        if RAG_ENABLED:
            sync_conversations_to_rag_safe(conversation_id=conv_id)

        _, updated_messages = _load_conversation_payload(conv_id)
        return jsonify(
            {
                "documents": next_documents,
                "active_document_id": get_canvas_runtime_active_document_id(runtime_state),
                "imported_count": int(import_result.get("imported_count") or 0),
                "created_count": int(import_result.get("created_count") or 0),
                "updated_count": int(import_result.get("updated_count") or 0),
                "primary_document_path": str(import_result.get("primary_document_path") or "").strip() or None,
                "project_id": str(import_result.get("project_id") or "").strip() or None,
                "workspace_id": str(import_result.get("workspace_id") or "").strip() or None,
                "source_url": str(import_result.get("source_url") or "").strip() or url,
                "messages": updated_messages,
            }
        ), 201

    @app.route("/api/conversations/<int:conv_id>/canvas", methods=["PATCH"])
    def update_canvas(conv_id):
        data = request.get_json(silent=True) or {}
        document_id = str(data.get("document_id") or "").strip() or None
        document_path = str(data.get("document_path") or "").strip() or None
        content = data.get("content")
        title = data.get("title")
        format_name = data.get("format")
        language = data.get("language")

        if content is None and title is None and format_name is None and language is None:
            return jsonify({"error": "Provide at least one canvas field to update."}), 400

        conversation, messages = _load_conversation_payload(conv_id)
        if not conversation:
            return jsonify({"error": "Not found."}), 404

        latest_canvas_state = find_latest_canvas_state(messages)
        runtime_state = create_canvas_runtime_state(
            latest_canvas_state.get("documents"),
            active_document_id=latest_canvas_state.get("active_document_id"),
        )
        current_documents = get_canvas_runtime_documents(runtime_state)
        if not current_documents:
            return jsonify({"error": "Canvas document not found."}), 404

        try:
            active_document = find_latest_canvas_document(messages, document_id=document_id, document_path=document_path)
            if not active_document:
                return jsonify({"error": "Canvas document not found."}), 404
            result = rewrite_canvas_document(
                runtime_state,
                content=active_document.get("content") if content is None else str(content),
                document_id=document_id,
                document_path=document_path,
                title=title,
                format_name=format_name,
                language_name=language,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        next_documents = get_canvas_runtime_documents(runtime_state)
        metadata = serialize_message_metadata(
            {
                "canvas_documents": next_documents,
                "active_document_id": get_canvas_runtime_active_document_id(runtime_state),
                "canvas_viewports": runtime_state.get("viewports") if isinstance(runtime_state.get("viewports"), dict) else {},
                "canvas_cleared": not next_documents,
            }
        )

        with get_db() as conn:
            insert_message(
                conn,
                conv_id,
                "tool",
                "",
                metadata=metadata,
            )
            conn.execute(
                "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
                (conv_id,),
            )

        if RAG_ENABLED:
            sync_conversations_to_rag_safe(conversation_id=conv_id)

        _, updated_messages = _load_conversation_payload(conv_id)
        return jsonify(
            {
                "document": result,
                "documents": next_documents,
                "active_document_id": result.get("id"),
                "messages": updated_messages,
            }
        )

    @app.route("/api/messages/<int:message_id>/prune", methods=["POST"])
    def prune_conversation_message(message_id):
        data = request.get_json(silent=True) or {}
        conversation_id_raw = data.get("conversation_id")
        conversation_id = None
        if conversation_id_raw not in (None, ""):
            try:
                conversation_id = int(conversation_id_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "conversation_id must be an integer."}), 400

        with get_db() as conn:
            row = conn.execute(
                "SELECT conversation_id, metadata FROM messages WHERE id = ? AND deleted_at IS NULL",
                (message_id,),
            ).fetchone()
            if not row:
                return jsonify({"error": "Message not found."}), 404

            if conversation_id is not None and int(row["conversation_id"] or 0) != conversation_id:
                return jsonify({"error": "Message does not belong to the provided conversation."}), 400

            metadata = parse_message_metadata(row["metadata"])
            if metadata.get("is_pruned") is True:
                updated_row = conn.execute(
                    """SELECT id, position, role, content, metadata, tool_calls, tool_call_id,
                              prompt_tokens, completion_tokens, total_tokens, created_at, deleted_at
                       FROM messages WHERE id = ?""",
                    (message_id,),
                ).fetchone()
                return jsonify({"message": message_row_to_dict(updated_row), "pruned": False, "skipped": True})

        try:
            pruned_message = prune_message(message_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        if not pruned_message:
            return jsonify({"error": "Message could not be pruned."}), 400

        with get_db() as conn:
            conn.execute(
                "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
                (pruned_message["conversation_id"],),
            )

        if RAG_ENABLED:
            sync_conversations_to_rag_safe(conversation_id=pruned_message["conversation_id"])

        return jsonify({"message": pruned_message, "pruned": True})

    @app.route("/api/messages/<int:message_id>", methods=["PATCH"])
    def update_conversation_message(message_id):
        data = request.get_json(silent=True) or {}
        if "content" not in data:
            return jsonify({"error": "content is required."}), 400

        conversation_id_raw = data.get("conversation_id")
        conversation_id = None
        if conversation_id_raw not in (None, ""):
            try:
                conversation_id = int(conversation_id_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "conversation_id must be an integer."}), 400

        normalized_content = str(data.get("content") or "").replace("\r\n", "\n")

        with get_db() as conn:
            row = conn.execute(
                """SELECT id, conversation_id, role, content, metadata, tool_calls, tool_call_id,
                          prompt_tokens, completion_tokens, total_tokens, deleted_at
                   FROM messages WHERE id = ?""",
                (message_id,),
            ).fetchone()
            if not row or row["deleted_at"] is not None:
                return jsonify({"error": "Message not found."}), 404

            row_conversation_id = int(row["conversation_id"] or 0)
            if conversation_id is not None and row_conversation_id != conversation_id:
                return jsonify({"error": "Message does not belong to the provided conversation."}), 400

            role = str(row["role"] or "").strip()
            if role not in {"user", "assistant"}:
                return jsonify({"error": "Only user and assistant messages can be edited."}), 400

            if role == "assistant" and parse_message_tool_calls(row["tool_calls"]):
                return jsonify({"error": "Assistant tool-call messages cannot be edited."}), 400

            metadata = parse_message_metadata(row["metadata"])
            updated_metadata = metadata
            if role == "user":
                metadata_payload = data.get("metadata") if "metadata" in data else metadata
                updated_metadata = sanitize_edited_user_message_metadata(metadata_payload)

            if not normalized_content.strip() and (role != "user" or not updated_metadata):
                return jsonify({"error": "Message content cannot be empty."}), 400

            conn.execute(
                "UPDATE messages SET content = ?, metadata = ? WHERE id = ?",
                (normalized_content, serialize_message_metadata(updated_metadata), message_id),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
                (row_conversation_id,),
            )
            updated_row = conn.execute(
                """SELECT id, position, role, content, metadata, tool_calls, tool_call_id,
                          prompt_tokens, completion_tokens, total_tokens, created_at, deleted_at
                   FROM messages WHERE id = ?""",
                (message_id,),
            ).fetchone()

        if RAG_ENABLED:
            sync_conversations_to_rag_safe(conversation_id=row_conversation_id)

        return jsonify({"updated": True, "message": message_row_to_dict(updated_row)})

    @app.route("/api/messages/<int:message_id>", methods=["DELETE"])
    def delete_conversation_message(message_id):
        data = request.get_json(silent=True) or {}
        conversation_id_raw = data.get("conversation_id")
        conversation_id = None
        if conversation_id_raw not in (None, ""):
            try:
                conversation_id = int(conversation_id_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "conversation_id must be an integer."}), 400

        with get_db() as conn:
            row = conn.execute(
                """SELECT id, conversation_id, role, tool_calls, deleted_at
                   FROM messages WHERE id = ?""",
                (message_id,),
            ).fetchone()
            if not row or row["deleted_at"] is not None:
                return jsonify({"error": "Message not found."}), 404

            row_conversation_id = int(row["conversation_id"] or 0)
            if conversation_id is not None and row_conversation_id != conversation_id:
                return jsonify({"error": "Message does not belong to the provided conversation."}), 400

            role = str(row["role"] or "").strip()
            if role not in {"user", "assistant"}:
                return jsonify({"error": "Only user and assistant messages can be deleted."}), 400

            if role == "assistant" and parse_message_tool_calls(row["tool_calls"]):
                return jsonify({"error": "Assistant tool-call messages cannot be deleted."}), 400

        branch_cleanup = rollback_conversation_branch(
            row_conversation_id,
            message_id,
            include_anchor=True,
        )

        with get_db() as conn:
            conn.execute(
                "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
                (row_conversation_id,),
            )

        if RAG_ENABLED:
            sync_conversations_to_rag_safe(conversation_id=row_conversation_id, force=True)

        _, updated_messages = _load_conversation_payload(row_conversation_id)
        return jsonify(
            {
                "deleted": True,
                "message_id": message_id,
                "conversation_id": row_conversation_id,
                "deleted_message_ids": branch_cleanup.get("deleted_message_ids") or [message_id],
                "messages": updated_messages,
            }
        )

    @app.route("/api/conversations/<int:conv_id>/prune-batch", methods=["POST"])
    def prune_conversation_batch_route(conv_id):
        with get_db() as conn:
            conv = conn.execute(
                "SELECT id FROM conversations WHERE id = ?", (conv_id,)
            ).fetchone()
            if not conv:
                return jsonify({"error": "Not found."}), 404

        data = request.get_json(silent=True) or {}
        try:
            count = max(1, min(50, int(data.get("count", 1))))
        except (TypeError, ValueError):
            return jsonify({"error": "count must be an integer between 1 and 50."}), 400

        pruned_count = prune_conversation_batch(conv_id, count)
        messages = get_conversation_messages(conv_id)

        if RAG_ENABLED:
            sync_conversations_to_rag_safe(conversation_id=conv_id)

        return jsonify({"pruned_count": pruned_count, "messages": messages})

    @app.route("/api/conversations/<int:conv_id>/prune-scores", methods=["POST"])
    def prune_conversation_scores_route(conv_id):
        with get_db() as conn:
            conv = conn.execute("SELECT id FROM conversations WHERE id = ?", (conv_id,)).fetchone()
            if not conv:
                return jsonify({"error": "Not found."}), 404

        settings = get_app_settings()
        scores = score_conversation_messages_for_prune(conv_id)
        prunable_token_count = sum(max(0, int(score.get("estimated_tokens") or 0)) for score in scores)

        return jsonify(
            {
                "scores": scores,
                "prunable_message_count": len(scores),
                "prunable_token_count": prunable_token_count,
                "threshold": get_pruning_token_threshold(settings),
                "batch_size": get_pruning_batch_size(settings),
                "rag_enabled": RAG_ENABLED,
            }
        )

    @app.route("/api/conversations/<int:conv_id>/prune-selected", methods=["POST"])
    def prune_selected_conversation_messages_route(conv_id):
        with get_db() as conn:
            conv = conn.execute("SELECT id FROM conversations WHERE id = ?", (conv_id,)).fetchone()
            if not conv:
                return jsonify({"error": "Not found."}), 404

        data = request.get_json(silent=True) or {}
        message_ids = _parse_message_id_list(data.get("message_ids"), limit=50)
        if not message_ids:
            return jsonify({"error": "message_ids must be a non-empty list of up to 50 integer ids."}), 400

        scored_messages = score_conversation_messages_for_prune(conv_id, message_ids)
        scored_by_id = {
            int(score.get("id") or 0): score
            for score in scored_messages
            if int(score.get("id") or 0) > 0
        }
        missing_ids = [message_id for message_id in message_ids if message_id not in scored_by_id]
        if missing_ids:
            return jsonify({"error": "One or more selected messages cannot be pruned.", "message_ids": missing_ids}), 400

        pruned_count = 0
        results = []
        for message_id in sorted(message_ids, key=lambda value: int(scored_by_id[value].get("position") or 0)):
            try:
                pruned_message = prune_message(message_id)
                results.append({"id": message_id, "pruned": True, "message": pruned_message})
                pruned_count += 1
            except ValueError as exc:
                results.append({"id": message_id, "pruned": False, "error": str(exc)})
            except Exception:
                current_app.logger.exception("Failed to prune selected message %s in conversation %s.", message_id, conv_id)
                results.append({"id": message_id, "pruned": False, "error": "Message could not be pruned."})

        if pruned_count:
            with get_db() as conn:
                conn.execute(
                    "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
                    (conv_id,),
                )

        messages = get_conversation_messages(conv_id)
        if RAG_ENABLED:
            sync_conversations_to_rag_safe(conversation_id=conv_id)

        return jsonify({"pruned_count": pruned_count, "results": results, "messages": messages})

    @app.route("/api/conversations/<int:conv_id>", methods=["DELETE"])
    def delete_conversation(conv_id):
        with get_db() as conn:
            conversation = conn.execute("SELECT id FROM conversations WHERE id = ?", (conv_id,)).fetchone()
            if not conversation:
                return jsonify({"error": "Not found."}), 404

        revert_conversation_state_mutations(conv_id)
        try:
            purge_conversation_rag_sources(conv_id, include_archived=True)
        except Exception:
            current_app.logger.exception("Conversation RAG cleanup failed for conversation_id=%s", conv_id)
        delete_conversation_image_assets(conv_id)
        delete_conversation_file_assets(conv_id)
        delete_conversation_video_assets(conv_id)
        delete_conversation_workspace(conv_id)
        with get_db() as conn:
            conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
        return "", 204

    @app.route("/api/conversations/<int:conv_id>", methods=["PATCH"])
    def update_conversation(conv_id):
        data = request.get_json(silent=True) or {}
        title_provided = "title" in data
        persona_provided = "persona_id" in data
        tool_overrides_provided = "tool_overrides" in data
        parameter_overrides_provided = "parameter_overrides" in data
        if not title_provided and not persona_provided and not tool_overrides_provided and not parameter_overrides_provided:
            return jsonify({"error": "Provide title, persona_id, tool_overrides, and/or parameter_overrides."}), 400

        title = None
        if title_provided:
            title = (data.get("title") or "").strip()[:120]
            if not title:
                return jsonify({"error": "Title required."}), 400

        raw_persona_id = data.get("persona_id") if persona_provided else None
        persona_id = _parse_optional_int(raw_persona_id) if persona_provided else None
        if persona_provided and raw_persona_id not in (None, "") and persona_id is None:
            return jsonify({"error": "persona_id must be an integer or empty."}), 400
        if persona_provided and persona_id is not None and get_persona(persona_id) is None:
            return jsonify({"error": "Persona not found."}), 400

        next_tool_overrides = None
        if tool_overrides_provided:
            raw_tool_overrides = data.get("tool_overrides")
            if raw_tool_overrides is None:
                next_tool_overrides = None
            elif isinstance(raw_tool_overrides, list):
                normalized = normalize_active_tool_names(raw_tool_overrides)
                next_tool_overrides = json.dumps(normalized) if normalized else None
            else:
                return jsonify({"error": "tool_overrides must be a list or null."}), 400

        next_parameter_overrides = None
        if parameter_overrides_provided:
            try:
                normalized_parameter_overrides = normalize_chat_parameter_overrides(data.get("parameter_overrides"))
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            next_parameter_overrides = (
                json.dumps(normalized_parameter_overrides, ensure_ascii=False)
                if normalized_parameter_overrides
                else None
            )

        with get_db() as conn:
            conversation = conn.execute(
                "SELECT id, title, title_source, title_overridden, persona_id, tool_overrides, parameter_overrides FROM conversations WHERE id = ?",
                (conv_id,),
            ).fetchone()
            if not conversation:
                return jsonify({"error": "Not found."}), 404

            next_persona_id = persona_id if persona_provided else conversation["persona_id"]

            if title_provided:
                next_title = title
                next_title_source = "manual"
                next_title_overridden = 1
            else:
                next_title = str(conversation["title"] or "New Chat").strip() or "New Chat"
                next_title_source = str(conversation["title_source"] or "system").strip() or "system"
                next_title_overridden = int(conversation["title_overridden"] or 0)

                if persona_provided and next_title_overridden == 0:
                    if next_persona_id is not None:
                        persona = get_persona(next_persona_id)
                        persona_name = str((persona or {}).get("name") or "").strip()[:120]
                        if persona_name:
                            next_title = persona_name
                            next_title_source = "persona"
                    elif next_title_source == "persona":
                        next_title = "New Chat"
                        next_title_source = "system"

            conn.execute(
                """
                UPDATE conversations
                   SET title = ?,
                       title_source = ?,
                       title_overridden = ?,
                       persona_id = ?,
                       updated_at = datetime('now')
                 WHERE id = ?
                """,
                (next_title, next_title_source, next_title_overridden, next_persona_id, conv_id),
            )
            if tool_overrides_provided:
                conn.execute(
                    "UPDATE conversations SET tool_overrides = ? WHERE id = ?",
                    (next_tool_overrides, conv_id),
                )
            if parameter_overrides_provided:
                conn.execute(
                    "UPDATE conversations SET parameter_overrides = ? WHERE id = ?",
                    (next_parameter_overrides, conv_id),
                )
        if RAG_ENABLED:
            sync_conversations_to_rag_safe(conversation_id=conv_id)
        response_tool_overrides = None
        if tool_overrides_provided:
            response_tool_overrides = next_tool_overrides
            if response_tool_overrides:
                try:
                    response_tool_overrides = json.loads(response_tool_overrides)
                except Exception:
                    response_tool_overrides = None
        response_parameter_overrides = None
        if parameter_overrides_provided:
            response_parameter_overrides = _deserialize_parameter_overrides(next_parameter_overrides)
        return jsonify({
            "id": conv_id,
            "title": next_title,
            "title_source": next_title_source,
            "title_overridden": bool(next_title_overridden),
            "persona_id": int(next_persona_id) if next_persona_id is not None else None,
            "tool_overrides": response_tool_overrides,
            "parameter_overrides": response_parameter_overrides,
        })

    @app.route("/api/rag/documents", methods=["GET"])
    def list_rag_documents():
        if not RAG_ENABLED:
            return jsonify({"error": RAG_DISABLED_FEATURE_ERROR}), 410
        return jsonify(list_rag_documents_db())

    @app.route("/api/rag/search", methods=["GET"])
    def rag_search():
        if not RAG_ENABLED:
            return jsonify({"error": RAG_DISABLED_FEATURE_ERROR}), 410
        query = (request.args.get("q") or "").strip()
        category = (request.args.get("category") or "").strip() or None
        raw_source_types = request.args.getlist("source_type") or request.args.get("source_types")
        try:
            top_k = int(request.args.get("top_k") or RAG_SEARCH_DEFAULT_TOP_K)
        except (TypeError, ValueError):
            top_k = RAG_SEARCH_DEFAULT_TOP_K
        top_k = max(1, min(100, top_k))
        try:
            min_similarity = request.args.get("min_similarity")
            min_similarity = float(min_similarity) if min_similarity not in (None, "") else None
        except (TypeError, ValueError):
            return jsonify({"error": "min_similarity must be a number between 0.0 and 1.0."}), 400
        if min_similarity is not None and not (0.0 <= min_similarity <= 1.0):
            return jsonify({"error": "min_similarity must be a number between 0.0 and 1.0."}), 400

        selected_source_types, invalid_source_types = _parse_rag_source_type_filter(raw_source_types)
        if invalid_source_types:
            return jsonify({"error": "source_types contains unsupported source types."}), 400

        allowed_source_types = selected_source_types
        if raw_source_types is None:
            allowed_source_types = get_rag_source_types()

        try:
            return jsonify(
                search_knowledge_base_tool(
                    query,
                    category=category,
                    top_k=top_k,
                    allowed_source_types=allowed_source_types,
                    min_similarity=min_similarity,
                )
            )
        except Exception:
            current_app.logger.exception("Knowledge base search failed for query=%s", query)
            return jsonify({"error": "Knowledge base search failed."}), 500

    @app.route("/api/rag/ingest", methods=["POST"])
    def ingest_rag_document():
        if not RAG_ENABLED:
            return jsonify({"error": RAG_DISABLED_FEATURE_ERROR}), 410

        source_name = ""
        description = ""
        auto_inject_enabled = True
        text = ""
        filename = "uploaded.txt"
        mime_type = "text/plain"

        try:
            if request.mimetype and request.mimetype.startswith("multipart/form-data"):
                uploaded_document = request.files.get("document")
                source_name = str(request.form.get("source_name") or "").strip()
                description = str(request.form.get("description") or "").strip()
                auto_inject_enabled = _parse_truthy_form_value(
                    request.form.get("auto_inject_enabled"),
                    default=True,
                )
                raw_text = request.form.get("text")

                if uploaded_document and getattr(uploaded_document, "filename", ""):
                    filename, mime_type, doc_bytes = read_uploaded_document(uploaded_document)
                    text = extract_document_text(doc_bytes, mime_type)
                else:
                    text = str(raw_text or "")
                    filename = os.path.basename(str(request.form.get("filename") or "uploaded.txt").strip()) or "uploaded.txt"
                    mime_type = "text/plain"
            else:
                data = request.get_json(silent=True) or {}
                source_name = str(data.get("source_name") or "").strip()
                description = str(data.get("description") or "").strip()
                auto_inject_enabled = _parse_truthy_form_value(data.get("auto_inject_enabled"), default=True)
                text = str(data.get("text") or "")
                filename = os.path.basename(str(data.get("filename") or "uploaded.txt").strip()) or "uploaded.txt"
                mime_type = str(data.get("mime_type") or "text/plain").strip() or "text/plain"
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        if not text.strip():
            return jsonify({"error": "Provide a document upload or non-empty text."}), 400

        try:
            document = ingest_uploaded_rag_document(
                filename,
                text,
                source_name=source_name or None,
                description=description,
                auto_inject_enabled=auto_inject_enabled,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception:
            current_app.logger.exception("RAG document ingestion failed for filename=%s", filename)
            return jsonify({"error": "Document ingestion failed."}), 500

        return jsonify(
            {
                "document": document,
                "file_name": filename,
                "mime_type": mime_type,
                "text_length": len(text),
            }
        ), 201

    @app.route("/api/rag/upload-metadata", methods=["POST"])
    def suggest_rag_upload_metadata():
        if not RAG_ENABLED:
            return jsonify({"error": RAG_DISABLED_FEATURE_ERROR}), 410

        try:
            uploaded_document = request.files.get("document")
            if not uploaded_document or not getattr(uploaded_document, "filename", ""):
                return jsonify({"error": "Choose a document to analyze."}), 400

            source_name = str(request.form.get("source_name") or "").strip()
            description = str(request.form.get("description") or "").strip()
            filename, mime_type, doc_bytes = read_uploaded_document(uploaded_document)
            text = extract_document_text(doc_bytes, mime_type)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        suggestion = _generate_upload_metadata_suggestion(
            filename,
            mime_type,
            text,
            source_name=source_name,
            description=description,
        )
        return jsonify(suggestion)

    @app.route("/api/rag/sync-conversations", methods=["POST"])
    def sync_rag_conversations():
        if not RAG_ENABLED:
            return jsonify({"error": RAG_DISABLED_FEATURE_ERROR}), 410
        data = request.get_json(silent=True) or {}
        raw_conversation_id = data.get("conversation_id")

        try:
            conversation_id = int(raw_conversation_id) if raw_conversation_id not in (None, "", "all") else None
        except (TypeError, ValueError):
            return jsonify({"error": "conversation_id must be an integer or 'all'."}), 400

        try:
            ensure_supported_rag_sources(force=True)
            synced = sync_conversations_to_rag(conversation_id=conversation_id, force=True)
        except Exception:
            current_app.logger.exception("Conversation-to-RAG sync failed for conversation_id=%s", conversation_id)
            return jsonify({"error": "Conversation sync failed."}), 500

        return jsonify({"count": len(synced), "documents": synced})

    @app.route("/api/rag/documents/<source_key>", methods=["DELETE"])
    def delete_rag_document(source_key):
        if not RAG_ENABLED:
            return jsonify({"error": RAG_DISABLED_FEATURE_ERROR}), 410
        row = get_rag_document_record(source_key)
        if not row:
            return jsonify({"error": "Not found."}), 404

        try:
            deleted_chunks = rag_delete_source(source_key)
        except Exception:
            current_app.logger.exception("RAG source deletion failed for source_key=%s", source_key)
            return jsonify({"error": "Knowledge base deletion failed."}), 500

        delete_rag_document_record(source_key)
        return jsonify(
            {
                "source_key": source_key,
                "source_name": row["source_name"],
                "deleted_chunks": deleted_chunks,
            }
        )
