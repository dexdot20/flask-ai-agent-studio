from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from datetime import datetime

from canvas_service import (
    build_canvas_project_manifest,
    extract_canvas_documents,
    get_canvas_document_capabilities,
    get_canvas_document_canvas_mode,
    get_canvas_document_content_mode,
    is_canvas_document_editable,
    scale_canvas_char_limit,
)
from config import (
    CANVAS_PROMPT_CODE_LINE_MAX_CHARS as CANVAS_PROMPT_DEFAULT_CODE_LINE_MAX_CHARS,
    CANVAS_PROMPT_DEFAULT_MAX_CHARS,
    CANVAS_PROMPT_DEFAULT_MAX_LINES,
    CANVAS_PROMPT_DEFAULT_MAX_TOKENS,
    CANVAS_PROMPT_TEXT_LINE_MAX_CHARS as CANVAS_PROMPT_DEFAULT_TEXT_LINE_MAX_CHARS,
    CLARIFICATION_DEFAULT_MAX_QUESTIONS,
    CLARIFICATION_QUESTION_LIMIT_MAX,
    CLARIFICATION_QUESTION_LIMIT_MIN,
    DEFAULT_MAX_PARALLEL_TOOLS,
    MAX_PARALLEL_TOOLS_MAX,
    MAX_PARALLEL_TOOLS_MIN,
    RAG_ENABLED,
    SCRATCHPAD_DEFAULT_SECTION,
    SCRATCHPAD_SECTION_METADATA,
    SCRATCHPAD_SECTION_ORDER,
)
from db import (
    extract_clarification_response,
    extract_message_attachments,
    extract_pending_clarification,
    extract_sub_agent_traces,
    parse_message_metadata,
    parse_message_tool_calls,
    read_image_asset_bytes,
)
from tool_registry import resolve_runtime_tool_names

SUMMARY_LABEL = "Conversation summary (generated from deleted messages):"
MODEL_SUMMARY_LABEL = "Conversation summary:"
CANVAS_PROMPT_MAX_CHARS = CANVAS_PROMPT_DEFAULT_MAX_CHARS
CANVAS_PROMPT_MAX_LINES = CANVAS_PROMPT_DEFAULT_MAX_LINES
CANVAS_PROMPT_MAX_TOKENS = CANVAS_PROMPT_DEFAULT_MAX_TOKENS
CANVAS_PROMPT_CODE_LINE_MAX_CHARS = CANVAS_PROMPT_DEFAULT_CODE_LINE_MAX_CHARS
CANVAS_PROMPT_TEXT_LINE_MAX_CHARS = CANVAS_PROMPT_DEFAULT_TEXT_LINE_MAX_CHARS
PARALLEL_SAFE_READ_ONLY_TOOL_NAMES = (
    # Web / fetch
    "search_web",
    "fetch_url",
    "search_news_ddgs",
    "search_news_google",
    "image_explain",
    # RAG / memory reads
    "search_knowledge_base",
    "search_tool_memory",
    "read_scratchpad",
    # Workspace reads
    "read_file",
    "list_dir",
    "search_files",
    "validate_project_workspace",
    # Canvas inspection (non-mutating)
    "expand_canvas_document",
    "scroll_canvas_document",
    "search_canvas_document",
    "preview_canvas_changes",
)

_CLARIFICATION_QA_LINE_RE = re.compile(r"^\s*(?:(?:Q|A)\s*:\s*.*|-\s*.+?\s*→\s*.+)$", re.IGNORECASE)


def extract_freeform_clarification_user_content(content: str) -> str:
    lines: list[str] = []
    for raw_line in str(content or "").splitlines():
        if _CLARIFICATION_QA_LINE_RE.match(raw_line.strip()):
            continue
        lines.append(raw_line.rstrip())
    return "\n".join(lines).strip()


def _normalize_pending_clarification_payload(payload: dict | None) -> dict | None:
    if not isinstance(payload, dict):
        return None
    return extract_pending_clarification({"pending_clarification": payload})


def _build_clarification_option_summary(question: dict) -> str:
    options = question.get("options") if isinstance(question.get("options"), list) else []
    labels = [
        str(option.get("label") or "").strip()
        for option in options
        if isinstance(option, dict) and str(option.get("label") or "").strip()
    ]
    if not labels:
        return ""
    return " | ".join(labels[:8])


def _build_pending_clarification_message_content(payload: dict | None) -> str:
    normalized_payload = _normalize_pending_clarification_payload(payload)
    if not isinstance(normalized_payload, dict):
        return ""

    questions = normalized_payload.get("questions") if isinstance(normalized_payload.get("questions"), list) else []
    if not questions:
        return ""

    intro = str(normalized_payload.get("intro") or "").strip()
    lines = [intro or "Before I answer, I need a few details."]
    lines.append("Please answer this question:" if len(questions) == 1 else "Please answer these questions:")

    for index, question in enumerate(questions, start=1):
        label = str(question.get("label") or f"Question {index}").strip() or f"Question {index}"
        question_line = f"{index}. {label}"
        if question.get("required") is False:
            question_line += " (optional)"
        option_summary = _build_clarification_option_summary(question)
        if option_summary:
            question_line += f" Options: {option_summary}."
        lines.append(question_line)

    return "\n".join(lines).strip()


def _build_clarification_response_message_content(
    content: str,
    clarification_response: dict | None,
    *,
    clarification_questions: list[dict] | None = None,
) -> str:
    """Build the user-message content that the model sees for a clarification answer.

    When structured answers are available, always generate a clean answer-centric
    format from the structured data — regardless of what the frontend sent as raw
    content — so the model never sees Q:/A: prefixes that resemble new questions.
    Any freeform text the user typed alongside the UI answers is preserved at the top.
    """
    normalized_content = str(content or "").strip()
    response = clarification_response if isinstance(clarification_response, dict) else {}
    answers = response.get("answers") if isinstance(response.get("answers"), dict) else {}
    if not answers:
        return normalized_content

    # Preserve freeform text the user typed alongside the structured answers.
    freeform_content = extract_freeform_clarification_user_content(normalized_content)

    normalized_questions = clarification_questions if isinstance(clarification_questions, list) else []
    question_lookup: dict[str, str] = {}
    ordered_question_ids: list[str] = []
    for question in normalized_questions:
        if not isinstance(question, dict):
            continue
        question_id = str(question.get("id") or "").strip()
        if not question_id:
            continue
        question_lookup[question_id] = str(question.get("label") or "").strip() or question_id
        ordered_question_ids.append(question_id)

    lines: list[str] = []
    emitted_question_ids: set[str] = set()
    for question_id in ordered_question_ids:
        answer = answers.get(question_id)
        if not isinstance(answer, dict):
            continue
        display = str(answer.get("display") or "").strip()
        if not display:
            continue
        label = question_lookup.get(question_id) or question_id
        lines.append(f"- {label} → {display}")
        emitted_question_ids.add(question_id)

    for question_id, answer in answers.items():
        normalized_question_id = str(question_id or "").strip()
        if not normalized_question_id or normalized_question_id in emitted_question_ids:
            continue
        if not isinstance(answer, dict):
            continue
        display = str(answer.get("display") or "").strip()
        if not display:
            continue
        label = question_lookup.get(normalized_question_id) or normalized_question_id
        lines.append(f"- {label} → {display}")

    answer_block = "\n".join(lines).strip()
    if freeform_content and answer_block:
        return f"{freeform_content}\n\n{answer_block}"
    return answer_block or freeform_content


def _format_summary_message_for_model(content: str, metadata: dict | None = None) -> str:
    normalized_content = str(content or "").strip()
    if normalized_content.lower().startswith(SUMMARY_LABEL.lower()):
        normalized_content = normalized_content[len(SUMMARY_LABEL):].strip()

    summary_prefix = MODEL_SUMMARY_LABEL
    summary_level = int(metadata.get("summary_level") or 0) if isinstance(metadata, dict) else 0
    summary_source = str(metadata.get("summary_source") or "").strip().lower() if isinstance(metadata, dict) else ""
    if summary_source == "summary_history" or summary_level > 1:
        summary_prefix = "Conversation summary of earlier summaries:"

    if normalized_content:
        return f"{summary_prefix}\n\n{normalized_content}"
    return summary_prefix
CANVAS_MUTATING_TOOL_NAMES = {
    "create_canvas_document",
    "rewrite_canvas_document",
    "batch_canvas_edits",
    "transform_canvas_lines",
    "update_canvas_metadata",
    "replace_canvas_lines",
    "insert_canvas_lines",
    "delete_canvas_lines",
    "delete_canvas_document",
    "clear_canvas",
}
# Tools whose results may still be inputs for other calls in the same batch;
# they are parallel-safe among themselves but must not be batched with any
# call that depends on their output.
DEPENDENT_TOOL_NAMES = (
    "search_knowledge_base",
    "search_tool_memory",
)

HISTORICAL_CONTEXT_INJECTION_STRIP_HEADINGS = {
    "## Clarification Response",
    "## Double-Check Protocol",
    "## Tool Memory",
    "## Knowledge Base",
    "## User Profile",
    "## Scratchpad (AI Persistent Memory)",
    "## Conversation Memory",
    "## Conversation Memory Priority",
    "## Canvas File Set Summary",
    "## Canvas Workspace Summary",
    "## Canvas Editing Guidance",
    "## Code Document Rules",
    "## Active Canvas Document",
    "## Ignored Canvas Documents",
    "## Pinned Canvas Viewports",
    "## Conversation Summaries",
    "## Tool Execution History",
    "## Active Tools This Turn",
    "## Current Date and Time",
}


def _normalize_runtime_scratchpad_sections(
    scratchpad_sections: dict | None = None,
    scratchpad: str = "",
) -> dict[str, str]:
    normalized = {section_id: "" for section_id in SCRATCHPAD_SECTION_ORDER}
    if isinstance(scratchpad_sections, dict):
        for section_id in SCRATCHPAD_SECTION_ORDER:
            normalized[section_id] = str(scratchpad_sections.get(section_id) or "").strip()

    legacy_text = str(scratchpad or "").strip()
    if legacy_text and not normalized[SCRATCHPAD_DEFAULT_SECTION]:
        normalized[SCRATCHPAD_DEFAULT_SECTION] = legacy_text

    return {section_id: str(normalized.get(section_id) or "").strip() for section_id in SCRATCHPAD_SECTION_ORDER}


def _iter_non_empty_scratchpad_sections(scratchpad_sections: dict[str, str]) -> list[tuple[str, str]]:
    return [
        (section_id, str(scratchpad_sections.get(section_id) or "").strip())
        for section_id in SCRATCHPAD_SECTION_ORDER
        if str(scratchpad_sections.get(section_id) or "").strip()
    ]


def _format_conversation_memory_timestamp(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "--:--"
    try:
        normalized = text.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).astimezone().strftime("%H:%M")
    except ValueError:
        return text[11:16] if len(text) >= 16 else "--:--"


def _normalize_conversation_memory_entries(entries) -> list[dict]:
    normalized_entries: list[dict] = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        entry_type = str(entry.get("entry_type") or "").strip().lower()
        key = str(entry.get("key") or "").strip()
        value = str(entry.get("value") or "").strip()
        created_at = str(entry.get("created_at") or "").strip()
        try:
            entry_id = int(entry.get("id"))
        except (TypeError, ValueError):
            entry_id = None
        if not entry_type or not key or not value:
            continue
        normalized_entries.append(
            {
                "id": entry_id,
                "entry_type": entry_type,
                "key": key,
                "value": value,
                "created_at": created_at,
            }
        )
    return normalized_entries


def _normalize_persona_memory_entries(entries) -> list[dict]:
    normalized_entries: list[dict] = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("key") or "").strip()
        value = str(entry.get("value") or "").strip()
        created_at = str(entry.get("created_at") or "").strip()
        try:
            entry_id = int(entry.get("id"))
        except (TypeError, ValueError):
            entry_id = None
        if not key or not value:
            continue
        normalized_entries.append(
            {
                "id": entry_id,
                "key": key,
                "value": value,
                "created_at": created_at,
            }
        )
    return normalized_entries


def build_conversation_memory_section(entries) -> list[str]:
    normalized_entries = _normalize_conversation_memory_entries(entries)
    if not normalized_entries:
        return []

    # Deduplicate: for the same (entry_type, key) pair, keep only the latest
    # entry (last in list order, which corresponds to the highest DB id /
    # most recent created_at).  This prevents the prompt from carrying stale
    # values when a memory key has been updated multiple times.
    seen: dict[tuple[str, str], int] = {}
    for index, entry in enumerate(normalized_entries):
        seen[(entry["entry_type"], entry["key"])] = index
    normalized_entries = [entry for index, entry in enumerate(normalized_entries) if seen.get((entry["entry_type"], entry["key"])) == index]

    parts = [
        "## Conversation Memory",
        "*Use this as the primary durable working memory for this chat. It survives prompt compaction, summarization, and pruning, so prefer saving chat-specific details here instead of the scratchpad unless they are clearly general cross-conversation memory.*\n",
    ]
    for entry in normalized_entries:
        entry_id = entry.get("id")
        entry_prefix = f"#{entry_id}" if isinstance(entry_id, int) and entry_id > 0 else "#?"
        parts.append(
            f"- {entry_prefix} [{entry['entry_type']}] {_format_conversation_memory_timestamp(entry.get('created_at'))} - {entry['key']}: {entry['value']}"
        )
    parts.append("")
    return parts


def build_persona_memory_section(entries) -> list[str]:
    normalized_entries = _normalize_persona_memory_entries(entries)
    if not normalized_entries:
        return []

    seen: dict[str, int] = {}
    for index, entry in enumerate(normalized_entries):
        seen[entry["key"]] = index
    normalized_entries = [entry for index, entry in enumerate(normalized_entries) if seen.get(entry["key"]) == index]

    parts = [
        "## Persona Memory",
        "*Shared durable memory for the currently active persona. It persists across conversations that use this same persona. Prefer saving stable persona-scoped facts here rather than chat-only details.*\n",
    ]
    for entry in normalized_entries:
        entry_id = entry.get("id")
        entry_prefix = f"#{entry_id}" if isinstance(entry_id, int) and entry_id > 0 else "#?"
        parts.append(
            f"- {entry_prefix} {_format_conversation_memory_timestamp(entry.get('created_at'))} - {entry['key']}: {entry['value']}"
        )
    parts.append("")
    return parts


def _build_image_policy_payload(active_tool_names: list[str]) -> dict | None:
    if "image_explain" not in set(active_tool_names or []):
        return None
    return {
        "tool": "image_explain",
        "guidance": "Use for follow-up questions about a stored prior image. Send the question in English. Ask for clarification if multiple earlier images could match.",
    }


def _build_clarification_policy_payload(active_tool_names: list[str], clarification_max_questions: int | None = None) -> dict | None:
    if "ask_clarifying_question" not in set(active_tool_names or []):
        return None
    return {
        "tool": "ask_clarifying_question",
        "guidance": (
            "If a good answer depends on missing requirements, ask for clarification instead of guessing. "
            "If the user explicitly asks you to ask questions first, you MUST emit an actual ask_clarifying_question tool call — "
            "outlining questions in your reasoning/thinking without emitting the call is not sufficient, "
            "and conversation memory entries or prior chat mentions do NOT satisfy this requirement. "
            "After you ask clarifying questions, wait for the user's reply before continuing. "
            "If the Clarification Response section is already present for this turn, that reply has already arrived; continue the task instead of calling ask_clarifying_question again. "
            "Conversation memory entries and ordinary prior messages are NOT Clarification Responses — they do not release you from asking questions the user has explicitly requested."
        ),
    }


def format_knowledge_base_auto_context(retrieved_context) -> str:
    normalized = str(retrieved_context or "").strip()
    if isinstance(retrieved_context, str):
        return normalized
    if not isinstance(retrieved_context, dict):
        return normalized

    matches = retrieved_context.get("matches") if isinstance(retrieved_context.get("matches"), list) else []
    if not matches:
        return ""

    query = str(retrieved_context.get("query") or "").strip()
    sections: list[str] = []
    if query:
        sections.append(f"Auto-injected query: {query}")

    for index, match in enumerate(matches, start=1):
        if not isinstance(match, dict):
            continue
        source_name = str(match.get("source_name") or match.get("source") or f"Match {index}").strip() or f"Match {index}"
        similarity = match.get("similarity")
        excerpt = str(match.get("text") or match.get("excerpt") or "").strip()
        block_parts = [f"Source: {source_name}"]
        if isinstance(similarity, (int, float)):
            block_parts.append(f"Similarity: {float(similarity):.2f}")
        if excerpt:
            block_parts.append(excerpt)
        sections.append("\n".join(block_parts))

    return "\n\n".join(section for section in sections if section).strip()


def _build_knowledge_base_payload(retrieved_context, active_tool_names: list[str]) -> dict | None:
    if not RAG_ENABLED:
        return None

    search_enabled = "search_knowledge_base" in set(active_tool_names or [])
    if not retrieved_context and not search_enabled:
        return None

    payload = {}
    if retrieved_context:
        formatted_context = format_knowledge_base_auto_context(retrieved_context)
        if formatted_context:
            payload["auto_injected_context"] = formatted_context
    if search_enabled:
        payload["guidance"] = "Use retrieved context directly when sufficient, and avoid redundant knowledge-base searches."
    return payload or None


def _build_tool_memory_payload(tool_memory_context, active_tool_names: list[str]) -> dict | None:
    search_enabled = "search_tool_memory" in set(active_tool_names or [])
    if not tool_memory_context and not search_enabled:
        return None

    payload = {}
    if tool_memory_context:
        payload["auto_injected_context"] = tool_memory_context
    if search_enabled:
        payload["guidance"] = (
            "Tool Memory stores results from previous web searches, news lookups, and URL fetches. "
            "BEFORE repeating any web request, check Tool Memory first by calling search_tool_memory with a relevant query. "
            "Use remembered results when they answer the question adequately. "
            "Only perform a new web request when no matching memory exists or the stored data is clearly outdated for the question at hand."
        )
    return payload or None


def _normalize_clarification_rounds(
    clarification_response: dict | None,
    all_clarification_rounds: list[dict] | None = None,
) -> list[dict]:
    # Only inject clarification context when the current turn actually carries a
    # clarification response.  Historical rounds (all_clarification_rounds) may
    # supplement the current round with earlier Q/A, but they must never be
    # injected on their own — those answers were already consumed by earlier
    # turns and re-injecting them on every subsequent non-clarification turn
    # misleads the model into treating the current user message as a
    # clarification response.
    current_has_clarification = (
        isinstance(clarification_response, dict)
        and isinstance(clarification_response.get("answers"), dict)
        and bool(clarification_response["answers"])
    )
    if not current_has_clarification:
        return []

    normalized_rounds: list[dict] = []
    raw_rounds = all_clarification_rounds if isinstance(all_clarification_rounds, list) else []
    if not raw_rounds:
        raw_rounds = [clarification_response] if isinstance(clarification_response, dict) else []

    for round_payload in raw_rounds[:10]:
        if not isinstance(round_payload, dict):
            continue

        answers = round_payload.get("answers") if isinstance(round_payload.get("answers"), dict) else {}
        normalized_answers: dict[str, dict[str, str]] = {}
        for key, value in list(answers.items())[:10]:
            key_text = str(key or "").strip()[:80]
            if not key_text or not isinstance(value, dict):
                continue
            display = str(value.get("display") or "").strip()[:500]
            if not display:
                continue
            normalized_answers[key_text] = {"display": display}
        if not normalized_answers:
            continue

        questions = round_payload.get("questions") if isinstance(round_payload.get("questions"), list) else []
        normalized_questions: list[dict] = []
        for question in questions[:CLARIFICATION_QUESTION_LIMIT_MAX]:
            if not isinstance(question, dict):
                continue
            question_id = str(question.get("id") or "").strip()[:80]
            question_text = str(question.get("label") or question.get("text") or "").strip()[:300]
            if not question_id and not question_text:
                continue
            normalized_question: dict[str, str] = {}
            if question_id:
                normalized_question["id"] = question_id
            if question_text:
                normalized_question["text"] = question_text
            normalized_questions.append(normalized_question)

        normalized_rounds.append(
            {
                "questions": normalized_questions,
                "answers": normalized_answers,
            }
        )

    return normalized_rounds


def _build_clarification_response_payload(
    clarification_response: dict | None,
    *,
    all_clarification_rounds: list[dict] | None = None,
) -> dict | None:
    rounds = _normalize_clarification_rounds(clarification_response, all_clarification_rounds)
    if not rounds:
        return None

    rendered_rounds: list[str] = []
    multiple_rounds = len(rounds) > 1
    for round_index, round_payload in enumerate(rounds, start=1):
        if multiple_rounds:
            rendered_rounds.append(f"Round {round_index}")

        questions = round_payload.get("questions") if isinstance(round_payload.get("questions"), list) else []
        answers = round_payload.get("answers") if isinstance(round_payload.get("answers"), dict) else {}
        consumed_answer_ids: set[str] = set()

        for question in questions:
            if not isinstance(question, dict):
                continue
            question_id = str(question.get("id") or "").strip()
            answer = answers.get(question_id) if question_id else None
            if not isinstance(answer, dict):
                continue
            question_text = str(question.get("text") or question_id or "Answer").strip()
            rendered_rounds.append(f"- {question_text} → {str(answer.get('display') or '').strip()}")
            consumed_answer_ids.add(question_id)

        for answer_id, answer in answers.items():
            if answer_id in consumed_answer_ids or not isinstance(answer, dict):
                continue
            fallback_question = str(answer_id or "Answer").strip().replace("_", " ")
            rendered_rounds.append(f"- {fallback_question} → {str(answer.get('display') or '').strip()}")

        if multiple_rounds and round_index < len(rounds):
            rendered_rounds.append("")

    return {
        "guidance": (
            "CRITICAL: The latest user message is NOT a new question or request — it is the user's direct response to your earlier clarification questions. "
            "The clarification answers below capture the answered rounds for this conversation. "
            "Accept these answers at face value and proceed immediately to the task. "
            "Do not verify them against conversation memory, do not save them to conversation memory, "
            "do not reinterpret them as retrieved knowledge-base content, "
            "and do not ask the same questions again unless the user changes the requirements or explicitly asks to revisit them. "
            "Do not re-list, re-display, or re-render the clarification questions in your response text — in any format. "
            "Proceed directly to the task solution using these answers. "
            "Do NOT call ask_clarifying_question again — all required information has been collected in the clarification round above. "
            "Calling it again in this turn would be an error."
        ),
        "formatted_answers": "\n".join(rendered_rounds).strip(),
    }


def normalize_chat_messages(messages) -> list[dict]:
    normalized = []
    allowed_roles = {"user", "assistant", "system", "tool", "summary"}

    for message in messages or []:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "").strip()
        if role not in allowed_roles:
            continue
        content = message.get("content")
        if content is None:
            content = ""
        if not isinstance(content, str):
            content = str(content)
        normalized.append(
            {
                "id": str(message.get("id") or "").strip() or None,
                "role": role,
                "content": content,
                "metadata": parse_message_metadata(message.get("metadata")),
                "tool_calls": parse_message_tool_calls(message.get("tool_calls")),
                "tool_call_id": str(message.get("tool_call_id") or "").strip() or None,
            }
        )

    return normalized


def _normalize_canvas_document_name(value: str | None) -> str:
    return os.path.basename(str(value or "").strip()).casefold()


def _normalize_canvas_document_stem(value: str | None) -> str:
    normalized_name = _normalize_canvas_document_name(value)
    if not normalized_name:
        return ""
    stem, _separator, _suffix = normalized_name.rpartition(".")
    return stem or normalized_name


def _extract_document_context_body(context_block: str | None) -> str:
    normalized = str(context_block or "").strip()
    if not normalized:
        return ""

    lines = normalized.splitlines()
    if lines and lines[0].startswith("[Uploaded document:"):
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines = lines[1:]
    return "\n".join(lines).strip()


def _build_canvas_document_lookup(canvas_documents) -> dict[str, list[str]]:
    documents = extract_canvas_documents({"canvas_documents": canvas_documents or []})
    lookup: dict[str, list[str]] = {}
    for document in documents:
        normalized_content = str(document.get("content") or "").strip().casefold()
        if not normalized_content:
            continue
        for candidate in (
            _normalize_canvas_document_name(document.get("title")),
            _normalize_canvas_document_name(document.get("path")),
            _normalize_canvas_document_stem(document.get("title")),
            _normalize_canvas_document_stem(document.get("path")),
        ):
            if not candidate:
                continue
            lookup.setdefault(candidate, []).append(normalized_content)
    return lookup


def _clip_canvas_preview_line(
    line: str,
    *,
    format_name: str | None = None,
    code_line_max_chars: int | None = None,
    text_line_max_chars: int | None = None,
) -> tuple[str, bool]:
    normalized_format = str(format_name or "").strip().lower()
    code_limit = max(40, int(code_line_max_chars or CANVAS_PROMPT_CODE_LINE_MAX_CHARS))
    text_limit = max(40, int(text_line_max_chars or CANVAS_PROMPT_TEXT_LINE_MAX_CHARS))
    max_chars = code_limit if normalized_format == "code" else text_limit
    if len(line) <= max_chars:
        return line, False
    return line[: max_chars - 2].rstrip() + "..", True


def _build_full_canvas_preview_lines_if_fit(
    all_lines: list[str],
    *,
    max_lines: int,
    max_chars: int,
    max_tokens: int,
) -> list[str] | None:
    if len(all_lines) > max_lines:
        return None

    numbered_lines = [f"{index}: {line}" for index, line in enumerate(all_lines, start=1)]
    preview_text = "\n".join(numbered_lines)
    if len(preview_text) > max_chars:
        return None
    if max_tokens > 0 and len(preview_text.encode("utf-8")) > max_tokens * 2:
        return None
    return numbered_lines


def _document_attachment_is_represented_in_canvas(attachment: dict, canvas_document_lookup: dict[str, list[str]]) -> bool:
    if not canvas_document_lookup:
        return False

    candidate_names = [
        _normalize_canvas_document_name(attachment.get("file_name")),
        _normalize_canvas_document_stem(attachment.get("file_name")),
    ]
    candidate_names = [name for name in candidate_names if name]
    if not candidate_names:
        return False

    candidate_contents: list[str] = []
    for candidate_name in candidate_names:
        candidate_contents.extend(canvas_document_lookup.get(candidate_name) or [])
    if not candidate_contents:
        return False

    body_excerpt = _extract_document_context_body(attachment.get("file_context_block"))
    if not body_excerpt:
        return True

    normalized_excerpt = body_excerpt[:500].casefold()
    return any(normalized_excerpt in content for content in candidate_contents)


def build_user_message_for_model(
    content: str,
    metadata: dict | None = None,
    *,
    canvas_documents: list[dict] | None = None,
    clarification_questions: list[dict] | None = None,
) -> str:
    content = (content or "").strip()
    metadata = metadata if isinstance(metadata, dict) else {}

    clarification_response = extract_clarification_response(metadata)
    clarification_answers = clarification_response.get("answers") if isinstance(clarification_response, dict) else {}
    if isinstance(clarification_answers, dict) and clarification_answers:
        content = _build_clarification_response_message_content(
            content,
            clarification_response,
            clarification_questions=clarification_questions,
        )

    attachments = extract_message_attachments(metadata)
    canvas_document_lookup = _build_canvas_document_lookup(canvas_documents)
    file_context_blocks = []
    video_context_blocks = []
    vision_attachments = []
    visual_document_notices = []
    direct_image_notices = []
    for attachment in attachments:
        if attachment.get("kind") == "document":
            if str(attachment.get("submission_mode") or "").strip().lower() == "visual":
                file_name = str(attachment.get("file_name") or "PDF").strip() or "PDF"
                page_image_ids = attachment.get("visual_page_image_ids") if isinstance(attachment.get("visual_page_image_ids"), list) else []
                try:
                    page_count = max(0, int(attachment.get("visual_page_count") or len(page_image_ids) or 0))
                except (TypeError, ValueError):
                    page_count = len(page_image_ids)
                try:
                    total_page_count = max(page_count, int(attachment.get("visual_total_page_count") or 0))
                except (TypeError, ValueError):
                    total_page_count = page_count
                if page_count <= 0 and total_page_count > 0:
                    visual_document_notices.append(
                        f"Uploaded PDF for visual analysis: {file_name}. PDF has {total_page_count} pages, but no rendered page images are currently attached below."
                    )
                elif page_count <= 0:
                    visual_document_notices.append(
                        f"Uploaded PDF for visual analysis: {file_name}. No rendered page images are currently attached below."
                    )
                elif total_page_count > page_count:
                    visual_document_notices.append(
                        f"Uploaded PDF for visual analysis: {file_name}. PDF has {total_page_count} pages; only the first {page_count} page{'s are' if page_count != 1 else ' is'} attached as image input below."
                    )
                else:
                    visual_document_notices.append(
                        f"Uploaded PDF for visual analysis: {file_name}. {page_count} page{'s are' if page_count != 1 else ' is'} attached as image input below."
                    )

                failed_pages = [
                    int(page_number)
                    for page_number in (attachment.get("visual_failed_pages") or [])
                    if isinstance(page_number, int) or str(page_number).isdigit()
                ]
                if failed_pages:
                    failed_page_labels = ", ".join(str(page_number) for page_number in failed_pages[:10])
                    if len(failed_pages) > 10:
                        failed_page_labels += ", ..."
                    visual_document_notices.append(
                        f"Warning: Visual rendering skipped PDF page(s) {failed_page_labels}. Analyze only the attached rendered pages."
                    )
                continue
            context_block = str(attachment.get("file_context_block") or "").strip()
            if _document_attachment_is_represented_in_canvas(attachment, canvas_document_lookup):
                continue
            if context_block and context_block not in file_context_blocks:
                file_context_blocks.append(context_block)
            continue

        if attachment.get("kind") == "video":
            context_block = str(attachment.get("transcript_context_block") or "").strip()
            if context_block and context_block not in video_context_blocks:
                video_context_blocks.append(context_block)
            continue

        image_id = str(attachment.get("image_id") or "").strip()
        image_name = str(attachment.get("image_name") or "").strip()
        analysis_method = str(attachment.get("analysis_method") or "").strip().lower()
        ocr_text = str(attachment.get("ocr_text") or "").strip()
        vision_summary = str(attachment.get("vision_summary") or "").strip()
        assistant_guidance = str(attachment.get("assistant_guidance") or "").strip()
        key_points = attachment.get("key_points") if isinstance(attachment.get("key_points"), list) else []
        if analysis_method == "llm_direct":
            direct_label = image_name or (f"image_id={image_id}" if image_id else "uploaded image")
            direct_notice = f"Uploaded image for direct multimodal analysis: {direct_label}. The original image is attached below."
            if direct_notice not in direct_image_notices:
                direct_image_notices.append(direct_notice)
            continue
        has_vision = image_id or image_name or ocr_text or vision_summary or assistant_guidance or key_points
        if has_vision:
            vision_attachments.append(attachment)

    if not file_context_blocks and not video_context_blocks and not vision_attachments and not visual_document_notices and not direct_image_notices:
        return content

    parts = []
    if content:
        parts.append(content)

    parts.extend(file_context_blocks)
    parts.extend(video_context_blocks)
    parts.extend(visual_document_notices)
    parts.extend(direct_image_notices)

    for index, attachment in enumerate(vision_attachments, start=1):
        image_id = str(attachment.get("image_id") or "").strip()
        image_name = str(attachment.get("image_name") or "").strip()
        ocr_text = str(attachment.get("ocr_text") or "").strip()
        vision_summary = str(attachment.get("vision_summary") or "").strip()
        assistant_guidance = str(attachment.get("assistant_guidance") or "").strip()
        key_points = attachment.get("key_points") if isinstance(attachment.get("key_points"), list) else []

        heading = "[Image attachment context]"
        if len(vision_attachments) > 1:
            heading = f"{heading} Attachment {index}"
        vision_parts = [heading]
        if image_id:
            reference_label = f"Stored image reference: image_id={image_id}"
            if image_name:
                reference_label += f", file={image_name}"
            vision_parts.append(reference_label)
        elif image_name:
            vision_parts.append(f"Uploaded image: {image_name}")
        if vision_summary:
            vision_parts.append(f"Visual summary: {vision_summary}")
        if key_points:
            vision_parts.append("Key observations:\n- " + "\n- ".join(str(point) for point in key_points))
        if ocr_text:
            vision_parts.append("OCR text:\n" + ocr_text)
        if assistant_guidance:
            vision_parts.append("Answering guidance: " + assistant_guidance)
        parts.append("\n\n".join(vision_parts))

    return "\n\n".join(parts)


def _build_visual_document_api_blocks(metadata: dict | None, *, warning_messages: list[str] | None = None) -> list[dict]:
    attachments = extract_message_attachments(metadata)
    blocks: list[dict] = []
    for attachment in attachments:
        if attachment.get("kind") != "document":
            continue
        if str(attachment.get("submission_mode") or "").strip().lower() != "visual":
            continue
        file_name = str(attachment.get("file_name") or "PDF").strip() or "PDF"
        image_ids = attachment.get("visual_page_image_ids") if isinstance(attachment.get("visual_page_image_ids"), list) else []
        page_numbers = [
            int(page_number)
            for page_number in (attachment.get("visual_page_numbers") or [])
            if isinstance(page_number, int) or str(page_number).isdigit()
        ]
        missing_pages: list[int] = []
        for index, image_id in enumerate(image_ids, start=1):
            mapped_page_number = page_numbers[index - 1] if index - 1 < len(page_numbers) else index
            asset, image_bytes = read_image_asset_bytes(str(image_id or "").strip())
            if not asset or not image_bytes:
                missing_pages.append(mapped_page_number)
                continue
            mime_type = str(asset.get("mime_type") or "image/jpeg").strip() or "image/jpeg"
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")
            blocks.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{image_b64}"},
                }
            )
        if missing_pages and warning_messages is not None:
            page_list = ", ".join(str(page_number) for page_number in missing_pages[:10])
            if len(missing_pages) > 10:
                page_list += ", ..."
            warning_messages.append(
                f"Warning: One or more visual PDF preview images for {file_name} were unavailable at request time (page(s): {page_list}). Analyze only the attached page images."
            )
    return blocks


def _build_direct_image_api_blocks(metadata: dict | None) -> list[dict]:
    attachments = extract_message_attachments(metadata)
    blocks: list[dict] = []
    for attachment in attachments:
        if attachment.get("kind") != "image":
            continue
        if str(attachment.get("analysis_method") or "").strip().lower() != "llm_direct":
            continue
        image_id = str(attachment.get("image_id") or "").strip()
        asset, image_bytes = read_image_asset_bytes(image_id)
        if not asset or not image_bytes:
            continue
        mime_type = str(asset.get("mime_type") or "image/jpeg").strip() or "image/jpeg"
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        blocks.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{image_b64}"},
            }
        )
    return blocks


def build_user_message_for_api(
    content: str,
    metadata: dict | None = None,
    *,
    canvas_documents: list[dict] | None = None,
    clarification_questions: list[dict] | None = None,
) -> str | list[dict]:
    text_content = build_user_message_for_model(
        content,
        metadata,
        canvas_documents=canvas_documents,
        clarification_questions=clarification_questions,
    )
    visual_warning_messages: list[str] = []
    visual_blocks = [
        *_build_direct_image_api_blocks(metadata),
        *_build_visual_document_api_blocks(metadata, warning_messages=visual_warning_messages),
    ]
    prompt_text = str(text_content or "").strip() or "Analyze the attached visual inputs carefully."
    if visual_warning_messages:
        prompt_text = "\n\n".join([prompt_text, *visual_warning_messages])
    if not visual_blocks:
        return prompt_text
    return [
        {"type": "text", "text": prompt_text},
        *visual_blocks,
    ]


def _strip_volatile_sections_from_context_injection(context_injection: str) -> str:
    normalized = str(context_injection or "").strip()
    if not normalized:
        return ""

    retained_sections: list[str] = []
    current_lines: list[str] = []
    current_heading: str | None = None

    def flush_section() -> None:
        nonlocal current_lines, current_heading
        if not current_lines:
            return
        section_text = "\n".join(current_lines).strip()
        if section_text and current_heading not in HISTORICAL_CONTEXT_INJECTION_STRIP_HEADINGS:
            retained_sections.append(section_text)
        current_lines = []
        current_heading = None

    for line in normalized.splitlines():
        if line.startswith("## "):
            flush_section()
            current_heading = line.strip()
            current_lines = [line]
            continue

        if not current_lines:
            current_lines = [line]
        else:
            current_lines.append(line)

    flush_section()
    return "\n\n".join(section for section in retained_sections if section).strip()


def prepare_context_injection_for_history(context_injection: str) -> str:
    """Return the stable subset of a runtime context injection worth persisting.

    The latest turn still receives the full runtime injection directly in the live
    request payload. When that user message becomes historical, only the durable
    non-volatile subset should remain attached to the stored message metadata so
    future turns avoid replaying per-turn cache busters such as timestamps,
    active tool lists, transient retrieval snippets, or canvas excerpts.
    """
    return _strip_volatile_sections_from_context_injection(context_injection)


def _filter_clarification_answers_for_questions(
    answers: dict | None,
    questions: list[dict] | None,
) -> dict[str, dict[str, str]]:
    normalized_answers = answers if isinstance(answers, dict) else {}
    normalized_questions = questions if isinstance(questions, list) else []
    filtered_answers: dict[str, dict[str, str]] = {}

    for question in normalized_questions:
        if not isinstance(question, dict):
            continue
        question_id = str(question.get("id") or "").strip()
        if not question_id:
            continue
        answer = normalized_answers.get(question_id)
        if not isinstance(answer, dict):
            continue
        display = str(answer.get("display") or "").strip()
        if not display:
            continue
        filtered_answers[question_id] = {"display": display}

    return filtered_answers


def _collect_answered_clarification_skip_indexes(messages: list[dict]) -> set[int]:
    skip_indexes: set[int] = set()
    for assistant_index, assistant_message in enumerate(messages):
        if not isinstance(assistant_message, dict):
            continue
        assistant_metadata = assistant_message.get("metadata") if isinstance(assistant_message.get("metadata"), dict) else {}
        if not extract_pending_clarification(assistant_metadata):
            continue

        tool_indexes: list[int] = []
        probe_index = assistant_index - 1
        while probe_index >= 0 and str(messages[probe_index].get("role") or "").strip() == "tool":
            tool_indexes.append(probe_index)
            probe_index -= 1

        if probe_index < 0 or str(messages[probe_index].get("role") or "").strip() != "assistant":
            continue

        tool_call_message = messages[probe_index]
        tool_calls = parse_message_tool_calls(tool_call_message.get("tool_calls"))
        clarification_call_ids = {
            str(tool_call.get("id") or "").strip()
            for tool_call in tool_calls
            if str(((tool_call.get("function") or {}).get("name") or "")).strip() == "ask_clarifying_question"
        }
        if not clarification_call_ids:
            continue

        matched_tool_indexes = {
            index
            for index in tool_indexes
            if str(messages[index].get("tool_call_id") or "").strip() in clarification_call_ids
        }
        if matched_tool_indexes:
            skip_indexes.add(probe_index)
            skip_indexes.update(matched_tool_indexes)
    return skip_indexes

def _collect_canvas_saved_sub_agent_skip_indexes(messages: list[dict]) -> set[int]:
    skip_indexes: set[int] = set()

    for assistant_index, message in enumerate(messages):
        if str(message.get("role") or "").strip() != "assistant":
            continue

        metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
        sub_agent_traces = extract_sub_agent_traces(metadata)
        if not any(trace.get("canvas_saved") is True for trace in sub_agent_traces):
            continue

        tool_indexes: list[int] = []
        probe_index = assistant_index - 1
        while probe_index >= 0 and str(messages[probe_index].get("role") or "").strip() == "tool":
            tool_indexes.append(probe_index)
            probe_index -= 1

        if probe_index < 0 or str(messages[probe_index].get("role") or "").strip() != "assistant":
            continue

        tool_call_message = messages[probe_index]
        tool_calls = parse_message_tool_calls(tool_call_message.get("tool_calls"))
        sub_agent_call_ids = {
            str(tool_call.get("id") or "").strip()
            for tool_call in tool_calls
            if str(((tool_call.get("function") or {}).get("name") or "")).strip() == "sub_agent"
        }
        if not sub_agent_call_ids:
            continue

        skip_indexes.add(probe_index)
        skip_indexes.update(
            index
            for index in tool_indexes
            if str(messages[index].get("tool_call_id") or "").strip() in sub_agent_call_ids
        )

    return skip_indexes


def _sanitize_tool_call_chain(api_messages: list[dict]) -> list[dict]:
    """Ensure every assistant tool_call has a matching tool result and vice versa.

    - Tool messages without tool_call_id are already excluded upstream; this pass
      removes assistant tool_calls whose IDs have no corresponding tool result, which
      would cause an API 400 error on providers that enforce the completeness of the
      tool-call / tool-result chain.
    - Assistant messages that become empty after filtering are dropped entirely (unless
      they still carry text content).
    """
    present_call_ids: set[str] = {
        msg["tool_call_id"]
        for msg in api_messages
        if msg.get("role") == "tool" and msg.get("tool_call_id")
    }
    result: list[dict] = []
    for msg in api_messages:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            surviving = [
                tc for tc in msg["tool_calls"]
                if str(tc.get("id") or "").strip() in present_call_ids
            ]
            if len(surviving) == len(msg["tool_calls"]):
                result.append(msg)
                continue
            if not surviving:
                # Drop tool_calls; keep the message only if it has text content.
                if str(msg.get("content") or "").strip():
                    result.append({k: v for k, v in msg.items() if k != "tool_calls"})
            else:
                result.append({**msg, "tool_calls": surviving})
        else:
            result.append(msg)
    return result


def build_api_messages(
    messages: list[dict],
    *,
    canvas_documents: list[dict] | None = None,
    embed_visual_documents: bool = False,
) -> list[dict]:
    api_messages = []
    skip_indexes = _collect_answered_clarification_skip_indexes(messages)
    skip_indexes.update(_collect_canvas_saved_sub_agent_skip_indexes(messages))
    latest_user_message_index = max(
        (index for index, message in enumerate(messages) if message.get("role") == "user"),
        default=-1,
    )
    active_tool_names_by_id: dict[str, str] = {}
    active_tool_names_in_order: list[str] = []
    active_tool_name_index = 0
    clarification_questions_by_assistant_id: dict[str, list[dict]] = {}

    for message in messages:
        if not isinstance(message, dict):
            continue
        if str(message.get("role") or "").strip() != "assistant":
            continue
        message_id = str(message.get("id") or "").strip()
        if not message_id:
            continue
        metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
        pending_clarification = extract_pending_clarification(metadata)
        questions = pending_clarification.get("questions") if isinstance(pending_clarification, dict) else []
        if isinstance(questions, list) and questions:
            clarification_questions_by_assistant_id[message_id] = questions

    for index, message in enumerate(messages):
        if index in skip_indexes:
            continue
        content = message["content"]
        role = message["role"]
        metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
        tool_calls = None
        if role == "user":
            context_injection = str(metadata.get("context_injection") or "").strip()
            if context_injection and index != latest_user_message_index:
                context_injection = _strip_volatile_sections_from_context_injection(context_injection)
            if context_injection:
                api_messages.append(
                    {
                        "role": "system",
                        "content": context_injection,
                    }
                )
            clarification_response = extract_clarification_response(metadata)
            assistant_message_id = str((clarification_response or {}).get("assistant_message_id") or "").strip()
            clarification_questions = clarification_questions_by_assistant_id.get(assistant_message_id)
            if embed_visual_documents:
                content = build_user_message_for_api(
                    content,
                    metadata,
                    canvas_documents=canvas_documents,
                    clarification_questions=clarification_questions,
                )
            else:
                content = build_user_message_for_model(
                    content,
                    metadata,
                    canvas_documents=canvas_documents,
                    clarification_questions=clarification_questions,
                )
        elif role == "summary":
            role = "assistant"
            content = _format_summary_message_for_model(content, metadata)
        elif role == "assistant":
            tool_calls = parse_message_tool_calls(message.get("tool_calls"))
            pending_clarification = extract_pending_clarification(metadata)
            if pending_clarification and not tool_calls and not str(content or "").strip():
                content = _build_pending_clarification_message_content(pending_clarification)
            if tool_calls and not content.strip():
                content = None
            active_tool_names_by_id = {}
            active_tool_names_in_order = []
            active_tool_name_index = 0
            for tool_call in tool_calls or []:
                tool_call_id = str(tool_call.get("id") or "").strip()
                tool_name = str(((tool_call.get("function") or {}).get("name") or "")).strip()
                if not tool_name:
                    continue
                active_tool_names_in_order.append(tool_name)
                if tool_call_id:
                    active_tool_names_by_id[tool_call_id] = tool_name

        api_message = {
            "role": role,
            "content": content,
        }

        if role == "assistant":
            if tool_calls:
                api_message["tool_calls"] = tool_calls
        elif role == "tool":
            tool_call_id = str(message.get("tool_call_id") or "").strip()
            if not tool_call_id:
                # Every tool message must carry tool_call_id; skip if missing to avoid
                # an API 400 "missing field tool_call_id" rejection.
                continue
            tool_name = active_tool_names_by_id.get(tool_call_id, "")
            if not tool_name and active_tool_name_index < len(active_tool_names_in_order):
                tool_name = active_tool_names_in_order[active_tool_name_index]
                active_tool_name_index += 1
            if not tool_name:
                tool_name = "tool"
            api_message["name"] = tool_name
            api_message["tool_call_id"] = tool_call_id

        api_messages.append(api_message)
    return _sanitize_tool_call_chain(api_messages)


def _build_canvas_prompt_payload(
    canvas_documents,
    active_document_id: str | None = None,
    canvas_viewports: list[dict] | None = None,
    *,
    max_lines: int = CANVAS_PROMPT_MAX_LINES,
    max_chars: int | None = None,
    max_tokens: int = CANVAS_PROMPT_MAX_TOKENS,
    code_line_max_chars: int | None = None,
    text_line_max_chars: int | None = None,
) -> dict | None:
    documents = extract_canvas_documents({"canvas_documents": canvas_documents or []})
    if not documents:
        return None

    if max_chars is None:
        max_chars = scale_canvas_char_limit(
            max_lines,
            default_lines=CANVAS_PROMPT_MAX_LINES,
            default_chars=CANVAS_PROMPT_MAX_CHARS,
        )

    manifest = build_canvas_project_manifest(documents, active_document_id=active_document_id)
    resolved_active_document_id = str((manifest or {}).get("active_document_id") or "").strip()
    active_document = documents[-1]
    if resolved_active_document_id:
        for document in documents:
            if str(document.get("id") or "") == resolved_active_document_id:
                active_document = document
                break

    manifest_file_list = (manifest or {}).get("file_list") if isinstance((manifest or {}).get("file_list"), list) else []
    ignored_documents = [
        entry
        for entry in manifest_file_list
        if isinstance(entry, dict) and entry.get("ignored") is True
    ]
    ignored_document_ids = {str(entry.get("id") or "").strip() for entry in ignored_documents}
    other_documents = [
        entry
        for entry in manifest_file_list
        if isinstance(entry, dict)
        and str(entry.get("id") or "").strip() != str(active_document.get("id") or "").strip()
        and str(entry.get("id") or "").strip() not in ignored_document_ids
    ]
    filtered_viewports = [
        viewport
        for viewport in (canvas_viewports or [])
        if isinstance(viewport, dict)
        and str(viewport.get("document_id") or "").strip() not in ignored_document_ids
    ]

    content = str(active_document.get("content") or "")
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    all_lines = content.split("\n") if content else []
    visible_lines = []
    visible_char_count = 0
    clipped_line_count = 0
    line_format = str(active_document.get("format") or "").strip().lower()
    document_capabilities = get_canvas_document_capabilities(active_document)
    active_document_ignored = active_document.get("ignored") is True

    if active_document_ignored:
        return {
            "mode": (manifest or {}).get("mode") or "document",
            "manifest": manifest,
            "relationship_map": (manifest or {}).get("relationship_map"),
            "document_count": len(documents),
            "active_document": active_document,
            "active_document_ignored": True,
            "ignored_documents": ignored_documents,
            "other_documents": other_documents,
            "visible_lines": [],
            "clipped_line_count": 0,
            "is_truncated": False,
            "visible_line_end": 0,
            "total_lines": int(active_document.get("line_count") or len(all_lines)),
            "viewports": filtered_viewports,
            "content_hash": content_hash,
        }

    if not document_capabilities["line_addressable"]:
        return {
            "mode": (manifest or {}).get("mode") or "document",
            "manifest": manifest,
            "relationship_map": (manifest or {}).get("relationship_map"),
            "document_count": len(documents),
            "active_document": active_document,
            "active_document_ignored": False,
            "ignored_documents": ignored_documents,
            "other_documents": other_documents,
            "visible_lines": [],
            "clipped_line_count": 0,
            "is_truncated": False,
            "visible_line_end": 0,
            "total_lines": int(active_document.get("line_count") or len(all_lines)),
            "viewports": filtered_viewports,
            "content_hash": content_hash,
        }

    full_preview_lines = _build_full_canvas_preview_lines_if_fit(
        all_lines,
        max_lines=max_lines,
        max_chars=max_chars,
        max_tokens=max_tokens,
    )
    if full_preview_lines is not None:
        visible_lines = full_preview_lines
    else:
        for index, line in enumerate(all_lines, start=1):
            preview_line, line_was_clipped = _clip_canvas_preview_line(
                line,
                format_name=line_format,
                code_line_max_chars=code_line_max_chars,
                text_line_max_chars=text_line_max_chars,
            )
            numbered_line = f"{index}: {preview_line}"
            extra_chars = len(numbered_line) + (1 if visible_lines else 0)
            if visible_lines and (len(visible_lines) >= max_lines or visible_char_count + extra_chars > max_chars):
                break
            if not visible_lines and extra_chars > max_chars:
                visible_lines.append(numbered_line[:max_chars])
                visible_char_count = len(visible_lines[0])
                if line_was_clipped:
                    clipped_line_count += 1
                break
            visible_lines.append(numbered_line)
            visible_char_count += extra_chars
            if line_was_clipped:
                clipped_line_count += 1

    # Content-size trim using UTF-8 byte budget as a language-agnostic proxy for
    # token cost. tiktoken (cl100k_base) severely underestimates actual provider
    # token counts for non-ASCII content: Turkish/Arabic/CJK text can tokenise
    # at 3-4x the rate of ASCII on DeepSeek and similar models. Byte counts
    # scale proportionally with this density (Turkish chars are 2 bytes each,
    # CJK chars are 3 bytes), making bytes a much safer budget metric.
    # Budget: max_tokens * 2  (1 token ≈ 2 UTF-8 bytes conservatively; this is
    # accurate for ASCII-heavy docs and safely limits Unicode-heavy ones).
    if max_tokens > 0 and len(visible_lines) > 1:
        byte_budget = max_tokens * 2
        if len("\n".join(visible_lines).encode("utf-8")) > byte_budget:
            lo, hi = 1, len(visible_lines) - 1
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if len("\n".join(visible_lines[:mid]).encode("utf-8")) <= byte_budget:
                    lo = mid
                else:
                    hi = mid - 1
            visible_lines = visible_lines[:lo]

    return {
        "mode": (manifest or {}).get("mode") or "document",
        "manifest": manifest,
        "relationship_map": (manifest or {}).get("relationship_map"),
        "document_count": len(documents),
        "active_document": active_document,
        "active_document_ignored": False,
        "ignored_documents": ignored_documents,
        "other_documents": other_documents,
        "visible_lines": visible_lines,
        "clipped_line_count": clipped_line_count,
        "is_truncated": len(visible_lines) < len(all_lines),
        "visible_line_end": len(visible_lines),
        "total_lines": int(active_document.get("line_count") or len(all_lines)),
        "viewports": filtered_viewports,
        "content_hash": content_hash,
    }


def _build_canvas_workspace_summary(canvas_payload: dict) -> list[str]:
    manifest = canvas_payload.get("manifest") if isinstance(canvas_payload.get("manifest"), dict) else {}
    active_document = canvas_payload.get("active_document") if isinstance(canvas_payload.get("active_document"), dict) else {}
    if int(canvas_payload.get("document_count") or 0) <= 1 and (canvas_payload.get("mode") or "document") != "project":
        return []

    is_project_mode = str(canvas_payload.get("mode") or "document").strip().lower() == "project"
    has_explicit_paths = any(
        str(entry.get("path") or "").strip()
        for entry in (canvas_payload.get("other_documents") or [])
    ) or str(active_document.get("path") or "").strip() != ""

    def _document_label(entry: dict) -> str:
        if not isinstance(entry, dict):
            return "Canvas"
        if is_project_mode and has_explicit_paths:
            return str(entry.get("path") or entry.get("title") or entry.get("id") or "Canvas").strip() or "Canvas"
        return str(entry.get("title") or entry.get("path") or entry.get("id") or "Canvas").strip() or "Canvas"

    lines = ["## Canvas File Set Summary"]
    lines.append(f"- Working mode: {canvas_payload.get('mode') or 'document'}")

    project_name = str(manifest.get("project_name") or "").strip()
    if project_name:
        lines.append(f"- Project label: {project_name}")

    active_label = _document_label(active_document)
    lines.append(f"- {'Active file' if is_project_mode and has_explicit_paths else 'Active document'}: {active_label}")

    total_lines = int(active_document.get("line_count") or 0)
    total_pages = int(active_document.get("page_count") or 0)
    visible_line_end = int(canvas_payload.get("visible_line_end") or 0)
    if active_document.get("ignored") is True:
        lines.append("- Canvas view status: hidden (active document is ignored for prompt content)")
    elif total_lines and visible_line_end:
        if visible_line_end >= total_lines:
            lines.append(
                f"- Canvas view status: full document visible ({visible_line_end}/{total_lines} lines)"
            )
            lines.append("- Canvas visibility note: the entire document is already in view; do not expand it just to see more of this same file.")
        else:
            lines.append(f"- Canvas view status: truncated excerpt ({visible_line_end}/{total_lines} lines visible)")
    else:
        lines.append("- Canvas view status: unknown")

    if total_pages > 1:
        lines.append(f"- Active document pages: {total_pages}")

    other_documents = canvas_payload.get("other_documents") if isinstance(canvas_payload.get("other_documents"), list) else []
    other_labels = [
        _document_label(entry)
        for entry in other_documents
        if _document_label(entry)
    ]
    if other_labels:
        shown_labels = other_labels[:4]
        lines.append(f"- {'Other files' if is_project_mode and has_explicit_paths else 'Other canvas documents'}: {', '.join(shown_labels)}")
        if len(other_labels) > len(shown_labels):
            lines.append(f"- Additional documents omitted: {len(other_labels) - len(shown_labels)}")

    ignored_documents = canvas_payload.get("ignored_documents") if isinstance(canvas_payload.get("ignored_documents"), list) else []
    ignored_labels = [
        _document_label(entry)
        for entry in ignored_documents
        if isinstance(entry, dict) and str(entry.get("id") or "").strip() != str(active_document.get("id") or "").strip()
    ]
    if ignored_labels:
        shown_ignored_labels = ignored_labels[:4]
        lines.append(
            f"- {'Ignored files' if is_project_mode and has_explicit_paths else 'Ignored canvas documents'}: "
            f"{', '.join(shown_ignored_labels)} (metadata only)"
        )
        if len(ignored_labels) > len(shown_ignored_labels):
            lines.append(f"- Additional ignored documents omitted: {len(ignored_labels) - len(shown_ignored_labels)}")

    lines.append("")
    return lines


def _format_canvas_metadata_values(values) -> str | None:
    if not isinstance(values, list):
        return None
    cleaned_values = [str(value).strip() for value in values if str(value).strip()]
    if not cleaned_values:
        return None
    return ", ".join(cleaned_values[:8])


def _build_ignored_canvas_documents_section(canvas_payload: dict) -> list[str]:
    ignored_documents = canvas_payload.get("ignored_documents") if isinstance(canvas_payload.get("ignored_documents"), list) else []
    if not ignored_documents:
        return []

    is_project_mode = str(canvas_payload.get("mode") or "document").strip().lower() == "project"
    prefer_path = any(str(entry.get("path") or "").strip() for entry in ignored_documents)
    lines = [
        "## Ignored Canvas Documents",
        "- These documents still exist in Canvas state, but their content is intentionally omitted from the prompt until re-enabled with update_canvas_metadata and ignored=false.",
    ]

    for entry in ignored_documents[:6]:
        if not isinstance(entry, dict):
            continue
        label = (
            str(entry.get("path") or entry.get("title") or entry.get("id") or "Canvas").strip()
            if is_project_mode and prefer_path
            else str(entry.get("title") or entry.get("path") or entry.get("id") or "Canvas").strip()
        ) or "Canvas"
        lines.append(f"- {label}")
        title = str(entry.get("title") or "").strip()
        if title and title != label:
            lines.append(f"  - Title: {title}")
        ignore_reason = str(entry.get("ignored_reason") or "").strip() or "No reason recorded."
        lines.append(f"  - Ignore reason: {ignore_reason}")
        if entry.get("role"):
            lines.append(f"  - Role: {entry['role']}")
        if entry.get("format"):
            lines.append(f"  - Format: {entry['format']}")
        if entry.get("content_mode"):
            lines.append(f"  - Content mode: {entry['content_mode']}")
        if entry.get("canvas_mode"):
            lines.append(f"  - Canvas mode: {entry['canvas_mode']}")
        if entry.get("language"):
            lines.append(f"  - Language: {entry['language']}")
        line_count = int(entry.get("line_count") or 0)
        if line_count > 0:
            lines.append(f"  - Total lines: {line_count}")
        page_count = int(entry.get("page_count") or 0)
        if page_count > 1:
            lines.append(f"  - Total pages: {page_count}")
        for key, label_text in (
            ("imports", "Imports"),
            ("exports", "Exports"),
            ("symbols", "Symbols"),
            ("dependencies", "Dependencies"),
        ):
            metadata_values = _format_canvas_metadata_values(entry.get(key))
            if metadata_values:
                lines.append(f"  - {label_text}: {metadata_values}")

    if len(ignored_documents) > 6:
        lines.append(f"- Additional ignored documents omitted: {len(ignored_documents) - 6}")
    lines.append("")
    return lines


def _canvas_inspection_tool_flags(active_tool_names: list[str]) -> dict[str, bool]:
    active_set = set(active_tool_names or [])
    return {
        "search": "search_canvas_document" in active_set,
        "scroll": "scroll_canvas_document" in active_set,
        "expand": "expand_canvas_document" in active_set,
    }


def _build_canvas_search_guidance_line(active_tool_names: list[str]) -> str | None:
    flags = _canvas_inspection_tool_flags(active_tool_names)
    if not flags["search"]:
        return None
    if flags["scroll"] and flags["expand"]:
        return "- If you first need to locate text or a symbol in a large canvas, use search_canvas_document before expanding or scrolling."
    if flags["expand"]:
        return "- If you first need to locate text or a symbol in a large canvas, use search_canvas_document before expanding."
    if flags["scroll"]:
        return "- If you first need to locate text or a symbol in a large canvas, use search_canvas_document before scrolling."
    return "- If you first need to locate text or a symbol in a large canvas, use search_canvas_document first."


def _build_canvas_inspect_first_line(active_tool_names: list[str]) -> str | None:
    flags = _canvas_inspection_tool_flags(active_tool_names)
    if flags["scroll"] and flags["expand"]:
        return "- If the target lines are not visible yet, inspect first with scroll_canvas_document or expand_canvas_document."
    if flags["expand"]:
        return "- If the target lines are not visible yet, inspect first with expand_canvas_document."
    if flags["scroll"]:
        return "- If the target lines are not visible yet, inspect first with scroll_canvas_document."
    return None


def _build_canvas_parallel_read_guidance_line(active_tool_names: list[str]) -> str | None:
    ordered_names = [
        tool_name
        for tool_name in ("search_canvas_document", "scroll_canvas_document", "expand_canvas_document")
        if tool_name in set(active_tool_names or [])
    ]
    if not ordered_names:
        return None
    if len(ordered_names) == 1:
        readable_names = ordered_names[0]
    elif len(ordered_names) == 2:
        readable_names = f"{ordered_names[0]} or {ordered_names[1]}"
    else:
        readable_names = f"{ordered_names[0]}, {ordered_names[1]}, or {ordered_names[2]}"
    return (
        "- Read-only canvas inspections can run in parallel, so prefer one answer that includes every needed "
        f"{readable_names} call before the edit turn."
    )


def _build_canvas_hidden_excerpt_guidance_line(active_tool_names: list[str]) -> str | None:
    flags = _canvas_inspection_tool_flags(active_tool_names)
    if flags["scroll"]:
        return "- If the excerpt says [Excerpt: lines 1–N of M], use scroll_canvas_document before editing hidden lines."
    if flags["expand"]:
        return "- If the excerpt says [Excerpt: lines 1–N of M], use expand_canvas_document before editing hidden lines."
    return None


def _build_canvas_preview_compaction_note(active_tool_names: list[str], clipped_line_count: int) -> str | None:
    if clipped_line_count <= 0:
        return None
    flags = _canvas_inspection_tool_flags(active_tool_names)
    if flags["scroll"] and flags["expand"]:
        tool_guidance = "use scroll_canvas_document or expand_canvas_document if exact full line text matters"
    elif flags["expand"]:
        tool_guidance = "use expand_canvas_document if exact full line text matters"
    elif flags["scroll"]:
        tool_guidance = "use scroll_canvas_document if exact full line text matters"
    else:
        tool_guidance = "exact full line text may require enabling a canvas read tool"
    return (
        f"- Preview compaction: {int(clipped_line_count)} long line(s) were clipped for token efficiency; {tool_guidance}."
    )


def _build_canvas_truncated_excerpt_guidance(active_tool_names: list[str]) -> str:
    flags = _canvas_inspection_tool_flags(active_tool_names)
    if flags["scroll"] and flags["expand"]:
        inspect_guidance = "Call expand_canvas_document for a larger view or scroll_canvas_document for a targeted range before editing."
    elif flags["expand"]:
        inspect_guidance = "Call expand_canvas_document for a larger view before editing."
    elif flags["scroll"]:
        inspect_guidance = "Call scroll_canvas_document for a targeted range before editing."
    else:
        inspect_guidance = "Do not guess line numbers outside the visible excerpt when no canvas read tool is enabled."
    return (
        "- Guidance: This canvas excerpt is truncated. Use visible line numbers for line-level canvas edits. "
        "The Canvas UI may show more content than the model currently has in context; only the excerpt below and any pinned viewports are visible to you right now. "
        "If an explicit document_path is listed in the Canvas File Set Summary or Active Canvas Document block, use that exact value. Otherwise do not invent a path; target the active document or use document_id instead. "
        f"{inspect_guidance} Never guess line numbers outside the visible excerpt."
    )


def _build_canvas_editing_guidance(active_tool_names: list[str], canvas_payload: dict | None = None) -> list[str]:
    active_document = (canvas_payload or {}).get("active_document") if isinstance((canvas_payload or {}).get("active_document"), dict) else {}
    if active_document and not get_canvas_document_capabilities(active_document)["editable"]:
        return [
            "## Canvas Editing Guidance",
            "- The active canvas document is a read-only visual preview backed by images.",
            "- Do not use line-based canvas editing tools on this document.",
            "- Metadata and content edits should wait until a text or hybrid document representation exists.",
            "",
        ]

    active_set = set(active_tool_names or [])
    if not active_set.intersection(CANVAS_MUTATING_TOOL_NAMES):
        return []

    search_guidance_line = _build_canvas_search_guidance_line(active_tool_names)
    inspect_first_line = _build_canvas_inspect_first_line(active_tool_names)
    parallel_read_guidance_line = _build_canvas_parallel_read_guidance_line(active_tool_names)
    hidden_excerpt_guidance_line = _build_canvas_hidden_excerpt_guidance_line(active_tool_names)

    lines = [
        "## Canvas Editing Guidance",
        "- Prefer the smallest valid canvas change that satisfies the request.",
        "- Do not rewrite the whole document when only part needs to change; use replace_canvas_lines, insert_canvas_lines, or delete_canvas_lines for local edits when the exact visible lines are known.",
        "- When several non-overlapping edits for the same document are already known, prefer batch_canvas_edits over serial line-edit calls.",
        "- Every batch_canvas_edits operation must be a plain object with action set to replace, insert, or delete; do not wrap it in an array, string, or nested shell.",
        "- For batch_canvas_edits, replace needs start_line, end_line, and lines; insert needs after_line and lines; delete needs start_line and end_line.",
        "- Use preview_canvas_changes before a large or risky batch when you need a non-mutating diff preview first.",
        "- Use transform_canvas_lines for bulk find-replace work; use count_only first when the replacement scope is uncertain.",
        "- Use update_canvas_metadata for title, summary, role, dependency, or symbol metadata changes that do not change document content.",
        "- Use update_canvas_metadata with ignored=true and ignored_reason to hide a canvas document's content from future prompts without deleting it; set ignored=false later to re-enable it.",
        "- Do not use line-based read, search, validate, or edit tools on an ignored canvas document until it has been re-enabled.",
        "- Cleanup: if a canvas document is obsolete, superseded, or just a scratch draft that no longer needs to stay in context, delete it with delete_canvas_document so it stops consuming prompt space.",
        "- If the entire canvas is now obsolete or should be reset, use clear_canvas instead of leaving dead documents behind.",
        "- If you will keep working in the same region for multiple turns, use set_canvas_viewport so the pinned lines are injected automatically in later prompts.",
        "- If the document is multi-page and the task is page-specific, use focus_canvas_page instead of manually estimating a page's line range.",
        "- When multiple files or canvas regions are involved, batch independent inspection calls together in one answer instead of requesting them one by one.",
        "- If you do not know the document_id, use the document_path carefully: use document_path only when an explicit project path is shown in the Canvas File Set Summary or Active Canvas Document block; otherwise do not invent a path and target the active document or use document_id.",
        "- For optional selector fields such as document_id or document_path, omit the key entirely when unknown; never send null.",
        "- Use rewrite_canvas_document when most of the document should change or when you already know the complete intended replacement content.",
        "- When you already know the required edits across multiple canvas documents, emit all of those edit tool calls in a single answer instead of editing one document, waiting, and then editing the next.",
        "- Preferred pattern for multi-file canvas work: batch inspections first, then batch all known edits in one answer.",
        "- Multiple canvas tool calls in one answer are fine when needed: inspect, then edit, then create or update other files.",
        "- When using replace_canvas_lines or insert_canvas_lines, ALL code content must be placed INSIDE the `lines` array as properly escaped JSON strings. "
        'Example: {"start_line": 2, "end_line": 3, "lines": ["const char* ssid = \\"MyNet\\";"]}. '
        "Never put code outside the lines array.",
        "## Code Document Rules",
        "- For source code files, use format='code'. If path is given, format and language are usually inferred automatically.",
        "- The content of a code document is raw source code — do NOT wrap it in triple-backtick fences.",
        "- When editing code lines, preserve indentation exactly. Each element of the lines array is one complete line.",
    ]
    if "create_canvas_document" in active_set:
        lines.insert(2, "- create_canvas_document always needs BOTH title and content.")
        lines.insert(3, "- When creating a new canvas document, never omit title. If a project path is known, reuse its basename as the title; otherwise provide a short artifact name such as README.md, app.py, or Release Plan.")
    if search_guidance_line:
        lines.insert(9, search_guidance_line)
    if inspect_first_line:
        lines.insert(10, inspect_first_line)
    if parallel_read_guidance_line:
        lines.insert(12, parallel_read_guidance_line)
    if hidden_excerpt_guidance_line:
        lines.append(hidden_excerpt_guidance_line)
    if (canvas_payload or {}).get("mode") == "project":
        lines.append("- In project mode, prefer document_path for targeting, even when you do not know the document_id yet.")
    lines.append("")
    return lines


def _normalize_clarification_max_questions(value: int | None) -> int:
    try:
        normalized = int(value) if value is not None else CLARIFICATION_DEFAULT_MAX_QUESTIONS
    except (TypeError, ValueError):
        normalized = CLARIFICATION_DEFAULT_MAX_QUESTIONS
    return max(CLARIFICATION_QUESTION_LIMIT_MIN, min(CLARIFICATION_QUESTION_LIMIT_MAX, normalized))


def _normalize_max_parallel_tools(value: int | None, default_value: int = DEFAULT_MAX_PARALLEL_TOOLS) -> int:
    try:
        normalized = int(value) if value is not None else int(default_value)
    except (TypeError, ValueError):
        normalized = int(default_value)
    return max(MAX_PARALLEL_TOOLS_MIN, min(MAX_PARALLEL_TOOLS_MAX, normalized))


def _normalize_tool_name_list(values) -> list[str]:
    normalized: list[str] = []
    for raw_value in values or []:
        name = str(raw_value or "").strip()
        if name and name not in normalized:
            normalized.append(name)
    return normalized


def _format_tool_name_list(values: list[str]) -> str:
    normalized = _normalize_tool_name_list(values)
    if not normalized:
        return "none"
    return ", ".join(f"`{name}`" for name in normalized)


def _finalize_prompt_text(parts: list[str]) -> str:
    text = "\n".join(str(part or "") for part in parts)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _build_active_tools_context(active_tool_names: list[str]) -> list[str]:
    normalized_tool_names = _normalize_tool_name_list(active_tool_names)
    if not normalized_tool_names:
        return []

    parallel_safe_tool_names = [
        name for name in normalized_tool_names if name in PARALLEL_SAFE_READ_ONLY_TOOL_NAMES
    ]

    lines = [
        "## Active Tools This Turn",
        "*These are the exact tools callable in this turn after runtime gating. Do not attempt to call tools outside this list.*\n",
        f"- Callable tools: {_format_tool_name_list(normalized_tool_names)}",
    ]
    if parallel_safe_tool_names:
        lines.append(f"- Parallel-safe read tools: {_format_tool_name_list(parallel_safe_tool_names)}")
    else:
        lines.append("- Parallel-safe read tools: none")
    lines.append("")
    return lines


def build_tool_call_contract(
    active_tool_names: list[str],
    clarification_max_questions: int | None = None,
    max_parallel_tools: int | None = None,
) -> dict | None:
    normalized_tool_names = _normalize_tool_name_list(active_tool_names)
    if not normalized_tool_names:
        return None
    rules = [
        "Call a tool only when it is strictly required to fulfill the user's request. If you can answer definitively from the current context and the task does not require current, external, or source-specific verification, do not call a tool.",
        "Use only the tools listed in the Active Tools section for this turn. Do not invent unavailable tools.",
        "If you do need a tool, call it via native function calling. Never write tool JSON or schema representations in your regular text response.",
        "Unnecessary tool calls waste compute and context. Do not use tools for trivial checks, repetition, or mere curiosity.",
    ]

    web_research_tool_names = {
        "search_web",
        "search_news_ddgs",
        "search_news_google",
        "fetch_url",
        "fetch_url_summarized",
        "grep_fetched_content",
    }
    if any(name in normalized_tool_names for name in web_research_tool_names):
        rules.append(
            "Use web-research tools only when the task genuinely needs current facts, external verification, or exact source text. If the answer is already available from the current context, do not search or fetch anything."
        )

    if "search_web" in normalized_tool_names:
        rules.append(
            "search_web accepts only the queries array. Do not pass max_results, top_k, limit, or any other control arguments; the runtime already caps results and batches queries automatically."
        )

    batching_sections = []
    parallel_safe_in_use = [name for name in normalized_tool_names if name in PARALLEL_SAFE_READ_ONLY_TOOL_NAMES]
    if parallel_safe_in_use:
        parallel_limit = _normalize_max_parallel_tools(max_parallel_tools)
        batching_sections.append(
            "Batch independent tool calls into one assistant turn when their inputs do not depend on each other. "
            "GATHER → REASON → ACT: issue all independent reads in one turn, reason over all results together, then act.\n"
            f"Parallel-safe tools (see Active Tools) run concurrently; cap is {parallel_limit} per turn. "
            "Sequential tools can also be batched in one turn to save an LLM round-trip. "
            "Only split into separate turns when tool B genuinely needs the output of tool A."
        )

    if any(name in normalized_tool_names for name in DEPENDENT_TOOL_NAMES):
        batching_sections.append(
            "**Dependency guard:** search_knowledge_base and search_tool_memory can be batched with other independent reads, "
            "but not with any tool that depends on their output."
        )

    if "ask_clarifying_question" in normalized_tool_names:
        limit = _normalize_clarification_max_questions(clarification_max_questions)
        rules.append(
            "ask_clarifying_question must be the only tool call in its assistant turn. "
            "Put the actual questions only in the tool arguments, not in the assistant text. "
            "Your reasoning or thinking process is NOT a substitute for the tool call — "
            "you must emit the function call even if you already outlined the questions in your thinking. "
            "Do not say that you prepared questions unless you emitted the tool call in that same turn. "
            "Each question label and option label must use plain UI text only in structured fields: avoid Q:/A: prefixes, markdown bullets, XML/tag wrappers, or <|...|> markers. "
            f"Ask at most {limit} question(s) per call and keep the assistant-visible reply short and brief."
        )

    return {
        "rules": rules,
        "batching_guidance": "\n\n".join(section.strip() for section in batching_sections if section.strip()),
    }


def _round_time_for_cache(now: datetime, window_minutes: int = 5) -> datetime:
    normalized_now = now.astimezone().replace(second=0, microsecond=0)
    if window_minutes <= 1:
        return normalized_now
    rounded_minute = (normalized_now.minute // window_minutes) * window_minutes
    return normalized_now.replace(minute=rounded_minute)


def _build_current_time_context(now: datetime) -> str:
    normalized_now = _round_time_for_cache(now)
    offset = normalized_now.strftime("%z")
    timezone_label = f"UTC{offset[:3]}:{offset[3:]}" if offset else (normalized_now.tzname() or "UTC")
    emphasized_timestamp = normalized_now.strftime("%A, %d %B %Y — %H:%M")
    return (
        f"## Current Date and Time\n> **AUTHORITATIVE CURRENT TIME:** {emphasized_timestamp} ({timezone_label})\n"
        f"- ISO: {normalized_now.isoformat(timespec='seconds')}\n"
        f"- Date: {normalized_now.date().isoformat()}\n- Time: {normalized_now.strftime('%H:%M')}\n"
        f"- Weekday: {normalized_now.strftime('%A')}\n- Timezone: {timezone_label}\n"
    )


def build_current_time_context(now: datetime | None = None) -> str:
    return _build_current_time_context((now or datetime.now().astimezone()).astimezone())


def _count_summary_messages(messages: list[dict] | None) -> int:
    count = 0
    for message in messages or []:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "").strip()
        if role == "summary":
            count += 1
            continue
        if role == "assistant":
            content = str(message.get("content") or "").strip()
            if content.lower().startswith(SUMMARY_LABEL.lower()):
                count += 1
    return count


def _build_runtime_volatile_parts(
    *,
    active_tool_names: list[str],
    clarification_response: dict | None = None,
    all_clarification_rounds: list[dict] | None = None,
    retrieved_context=None,
    tool_trace_context=None,
    tool_memory_context=None,
    now: datetime,
    canvas_documents=None,
    canvas_active_document_id: str | None = None,
    canvas_viewports: list[dict] | None = None,
    canvas_prompt_max_lines: int | None = None,
    canvas_prompt_max_chars: int | None = None,
    canvas_prompt_max_tokens: int | None = None,
    canvas_prompt_code_line_max_chars: int | None = None,
    canvas_prompt_text_line_max_chars: int | None = None,
    canvas_payload: dict | None = None,
    summary_count: int = 0,
    include_time_context: bool = True,
    previous_canvas_content_hash: str | None = None,
    double_check: bool = False,
    double_check_query: str = "",
) -> list[str]:
    volatile_parts: list[str] = []

    if include_time_context:
        volatile_parts.append(_build_current_time_context(now))

    if double_check:
        normalized_double_check_query = str(double_check_query or "").strip()
        volatile_parts.append("## Double-Check Protocol")
        volatile_parts.append(
            "*Treat this turn as a verification pass. Audit the relevant factual claims, advice, calculations, technical assertions, and safety-sensitive guidance before finalizing the answer. Use a concise but rigorous tone, and explain your confidence level honestly.*\n"
        )
        volatile_parts.append("- Goal: perform a deliberate second-pass review instead of a normal first-pass answer.")
        if normalized_double_check_query:
            volatile_parts.append(f"- Focus scope: verify this specific claim or request first: {normalized_double_check_query}")
        else:
            volatile_parts.append("- Focus scope: scan the conversation history for the important unresolved claims or recommendations that still need verification.")
        volatile_parts.append(
            "- Avoid re-checking claims that were already double-checked earlier in this conversation unless new evidence, new user instructions, or unresolved uncertainty justify another pass."
        )
        volatile_parts.append(
            "- If the current context is sufficient, verify from the existing conversation and tool results. If fresh or external evidence is needed, use the available web or retrieval tools to gather it."
        )
        volatile_parts.append(
            "- Stress-test your own conclusion: include the strongest counterargument, failure mode, or devil's-advocate objection before settling on the final judgment."
        )
        volatile_parts.append(
            "- Do not present uncertain claims as certain. Distinguish clearly between verified facts, likely inferences, unresolved doubts, and missing evidence."
        )
        volatile_parts.append(
            "- Write the final answer in natural prose. A fixed template is not required, but the reasoning should make it obvious why the conclusion holds and what could still be wrong."
        )
        volatile_parts.append("")

    tool_memory_payload = _build_tool_memory_payload(tool_memory_context, active_tool_names)
    if tool_memory_payload:
        volatile_parts.append("## Tool Memory")
        if "guidance" in tool_memory_payload:
            volatile_parts.append(f"*{tool_memory_payload['guidance']}*\n")
        if tool_memory_payload.get("auto_injected_context"):
            if isinstance(tool_memory_payload["auto_injected_context"], str):
                volatile_parts.append(tool_memory_payload["auto_injected_context"])
            else:
                volatile_parts.append(json.dumps(tool_memory_payload["auto_injected_context"], ensure_ascii=False, indent=2))
        volatile_parts.append("")

    clarification_payload = _build_clarification_response_payload(
        clarification_response,
        all_clarification_rounds=all_clarification_rounds,
    )
    if clarification_payload:
        volatile_parts.append("## Clarification Response")
        volatile_parts.append(f"*{clarification_payload['guidance']}*\n")
        if clarification_payload.get("formatted_answers"):
            volatile_parts.append(str(clarification_payload["formatted_answers"]).strip())
        volatile_parts.append("")

    kb_payload = _build_knowledge_base_payload(retrieved_context, active_tool_names)
    if kb_payload:
        volatile_parts.append("## Knowledge Base")
        if "guidance" in kb_payload:
            volatile_parts.append(f"*{kb_payload['guidance']}*\n")
        if kb_payload.get("auto_injected_context"):
            if isinstance(kb_payload["auto_injected_context"], str):
                volatile_parts.append(kb_payload["auto_injected_context"])
            else:
                volatile_parts.append(json.dumps(kb_payload["auto_injected_context"], ensure_ascii=False, indent=2))
        volatile_parts.append("")

    if canvas_payload is None:
        canvas_payload = _build_canvas_prompt_payload(
            canvas_documents,
            active_document_id=canvas_active_document_id,
            canvas_viewports=canvas_viewports,
            max_lines=canvas_prompt_max_lines or CANVAS_PROMPT_MAX_LINES,
            max_chars=canvas_prompt_max_chars,
            max_tokens=canvas_prompt_max_tokens if canvas_prompt_max_tokens is not None else CANVAS_PROMPT_MAX_TOKENS,
            code_line_max_chars=canvas_prompt_code_line_max_chars,
            text_line_max_chars=canvas_prompt_text_line_max_chars,
        )
    if canvas_payload:
        workspace_summary_lines = _build_canvas_workspace_summary(canvas_payload)
        if workspace_summary_lines:
            volatile_parts.extend(workspace_summary_lines)
        active_document = canvas_payload["active_document"]
        active_document_ignored = active_document.get("ignored") is True
        volatile_parts.append("## Active Canvas Document")
        volatile_parts.append(f"- Active document id: {active_document['id']}")
        if not workspace_summary_lines and active_document.get("path"):
            volatile_parts.append(f"- Path: {active_document['path']}")
        elif not workspace_summary_lines and active_document.get("title"):
            volatile_parts.append(f"- Title: {active_document['title']}")
        if active_document.get("role"):
            volatile_parts.append(f"- Role: {active_document['role']}")
        volatile_parts.append(f"- Format: {active_document['format']}")
        volatile_parts.append(f"- Content mode: {get_canvas_document_content_mode(active_document)}")
        volatile_parts.append(f"- Canvas mode: {get_canvas_document_canvas_mode(active_document)}")
        if active_document.get("language"):
            volatile_parts.append(f"- Language: {active_document['language']}")
        volatile_parts.append(f"- Total lines: {canvas_payload['total_lines']}")
        if int(active_document.get("page_count") or 0) > 1:
            volatile_parts.append(f"- Total pages: {int(active_document.get('page_count') or 0)}")
        if active_document_ignored:
            volatile_parts.append("- Ignored in prompt: true")
            if active_document.get("ignored_reason"):
                volatile_parts.append(f"- Ignore reason: {active_document['ignored_reason']}")
            volatile_parts.append("- Visible lines in prompt: hidden (ignored document)")
        elif get_canvas_document_capabilities(active_document)["line_addressable"]:
            volatile_parts.append(
                f"- Visible lines in prompt: 1-{canvas_payload['visible_line_end']}"
                + (" (truncated excerpt)" if canvas_payload["is_truncated"] else "")
            )
        else:
            volatile_parts.append("- Visual preview: page images are available in the UI, but line excerpts are not injected for this document type.")
        if not active_document_ignored:
            preview_compaction_note = _build_canvas_preview_compaction_note(
                active_tool_names,
                int(canvas_payload.get("clipped_line_count") or 0),
            )
            if preview_compaction_note:
                volatile_parts.append(preview_compaction_note)
        if not active_document_ignored and "expand_canvas_document" in set(active_tool_names or []):
            volatile_parts.append(
                "- Snapshot rule: expand_canvas_document returns a call-time snapshot. If the canvas may have changed after an earlier expansion, call it again before relying on that older view."
            )
        if active_document_ignored:
            volatile_parts.append(
                "- Guidance: This canvas document is intentionally ignored for automatic prompt content. Its metadata stays visible so you can re-enable it later with update_canvas_metadata and ignored=false when needed."
            )
        elif not get_canvas_document_capabilities(active_document)["line_addressable"]:
            volatile_parts.append(
                "- Guidance: This active canvas document is an image-backed visual preview. Treat it as read-only and avoid line-based canvas inspection or editing tools."
            )
        elif canvas_payload["is_truncated"]:
            volatile_parts.append(_build_canvas_truncated_excerpt_guidance(active_tool_names))
        else:
            volatile_parts.append(
                "- Guidance: The active canvas document is fully visible in the current excerpt. Canvas is already fully visible, so use the visible line numbers directly for line-level edits."
            )
        if canvas_payload["mode"] == "project":
            volatile_parts.append(
                "- In project mode, prefer the explicit document_path shown in the prompt for targeting, even when you do not know the document_id yet."
            )
        if (
            not active_document_ignored
            and get_canvas_document_capabilities(active_document)["line_addressable"]
            and is_canvas_document_editable(active_document)
            and "rewrite_canvas_document" in set(active_tool_names or [])
        ):
            volatile_parts.append(
                "- Auto-update rule: If your response generates content that directly replaces or substantially transforms this document, call rewrite_canvas_document immediately — do not ask the user for permission to save."
            )
        if not active_document_ignored and int(active_document.get("page_count") or 0) > 1 and get_canvas_document_capabilities(active_document)["line_addressable"]:
            volatile_parts.append(
                "- Multi-page guidance: if the task refers to a specific PDF-style page, call focus_canvas_page only when the document already exposes explicit '## Page N' markers in its text content."
            )
        if canvas_payload["visible_lines"] and not active_document_ignored:
            _canvas_content_unchanged = (
                previous_canvas_content_hash
                and previous_canvas_content_hash == canvas_payload.get("content_hash")
            )
            if _canvas_content_unchanged:
                volatile_parts.append(
                    f"[Document content unchanged since last turn — cached version is current. Total: {canvas_payload['total_lines']} lines]\n"
                )
            else:
                volatile_parts.append("```text\n" + "\n".join(canvas_payload["visible_lines"]) + "\n```\n")
        elif get_canvas_document_capabilities(active_document)["line_addressable"] and not active_document_ignored:
            volatile_parts.append("(The active canvas document is empty.)\n")

        ignored_documents_section = _build_ignored_canvas_documents_section(canvas_payload)
        if ignored_documents_section:
            volatile_parts.extend(ignored_documents_section)

        viewport_payloads = canvas_payload.get("viewports") if isinstance(canvas_payload.get("viewports"), list) else []
        if viewport_payloads:
            volatile_parts.append("## Pinned Canvas Viewports")
            volatile_parts.append("- These pinned ranges are auto-injected from prior viewport selections. Reuse them before asking to scroll or expand the same region again.")
            for viewport in viewport_payloads[:6]:
                target_label = str(viewport.get("document_path") or viewport.get("title") or viewport.get("document_id") or "Canvas").strip()
                page_label = f" page {int(viewport.get('page_number') or 0)}" if int(viewport.get("page_number") or 0) > 0 else ""
                volatile_parts.append(
                    f"- {target_label}{page_label} lines {int(viewport.get('start_line') or 0)}-{int(viewport.get('end_line') or 0)}"
                    + (
                        f" (remaining turns: {int(viewport.get('remaining_turns') or 0)})"
                        if int(viewport.get("remaining_turns") or 0) > 0
                        else ""
                    )
                )
                visible_lines = viewport.get("visible_lines") if isinstance(viewport.get("visible_lines"), list) else []
                if visible_lines:
                    volatile_parts.append("```text\n" + "\n".join(str(line) for line in visible_lines) + "\n```")
            volatile_parts.append("")

    if summary_count:
        volatile_parts.append("## Conversation Summaries")
        volatile_parts.append(f"- Count: {summary_count}")
        volatile_parts.append(
            "- The summary messages already included below are authoritative compressed history for earlier deleted turns."
        )
        volatile_parts.append("")

    normalized_tool_trace_context = str(tool_trace_context or "").strip()
    if normalized_tool_trace_context:
        volatile_parts.append("## Tool Execution History")
        volatile_parts.append(
            "*Use this as recent operational memory about which tools were already tried, what they returned, and which paths should not be repeated without a concrete reason.*\n"
        )
        volatile_parts.append(normalized_tool_trace_context)
        volatile_parts.append("")

    active_tools_context = _build_active_tools_context(active_tool_names)
    if active_tools_context:
        volatile_parts.extend(active_tools_context)

    return volatile_parts


def _build_runtime_dynamic_state_parts(
    *,
    runtime_tool_names: list[str],
    user_profile_context=None,
    persona_memory=None,
    conversation_memory=None,
    scratchpad: str = "",
    scratchpad_sections=None,
    summary_count: int = 0,
) -> list[str]:
    parts: list[str] = []
    normalized_user_profile_context = str(user_profile_context or "").strip()
    normalized_scratchpad_sections = _normalize_runtime_scratchpad_sections(
        scratchpad_sections=scratchpad_sections,
        scratchpad=scratchpad,
    )
    non_empty_scratchpad_sections = _iter_non_empty_scratchpad_sections(normalized_scratchpad_sections)
    conversation_memory_tools_enabled = any(
        name in {"save_to_conversation_memory", "delete_conversation_memory_entry"}
        for name in runtime_tool_names
    )

    if normalized_user_profile_context:
        parts.append("## User Profile")
        parts.append(
            "*Use this as durable cross-conversation memory about the user when it is relevant to the current request. Do not treat it as higher priority than the user's latest explicit instruction.*\n"
        )
        parts.append(normalized_user_profile_context)
        parts.append("")

    if non_empty_scratchpad_sections or any(name in {"append_scratchpad", "replace_scratchpad"} for name in runtime_tool_names):
        parts.append("## Scratchpad (AI Persistent Memory)")
        scratchpad_intro = (
            "*This is the live persistent scratchpad for rare cross-conversation general memory. Keep it sparse. It is already visible in the prompt, so read it directly here first."
        )
        if "read_scratchpad" in runtime_tool_names:
            scratchpad_intro += " Use read_scratchpad only if you want the structured stored memory as a tool result before editing it."
        scratchpad_intro += "*\n"
        parts.append(scratchpad_intro)
        if non_empty_scratchpad_sections:
            for section_id, section_content in non_empty_scratchpad_sections:
                parts.append(f"### {SCRATCHPAD_SECTION_METADATA[section_id]['title']}")
                parts.append(section_content)
                parts.append("")
        if any(name in {"append_scratchpad", "replace_scratchpad"} for name in runtime_tool_names):
            parts.append(
                "\n### Memory Write Policy\n"
                "- **DO save**: Only minimal durable general facts that are likely to matter across future conversations. Examples: stable user preferences, long-lived general constraints, confirmed identity details, and recurring requirements.\n"
                "- **Default away from scratchpad**: If a detail is mainly about the current chat, current task, recent tool results, current repo state, or temporary plans, save it to conversation memory instead or do not store it at all.\n"
                "- **DO NOT save**: One-off tasks, transient project state, raw tool outputs, web/search results, speculative inferences, broad summaries, or details already obvious from the current chat.\n"
                "- **Before saving**: Ask whether this information is both general enough for future conversations and important enough to deserve long-term storage. If not, do not save it.\n"
                "- **Use the right section**: Preferences belong in User Preferences, reasoning patterns in User Profile & Mindset, durable takeaways in Lessons Learned, recurring unresolved issues in Open Problems, long-running cross-conversation continuity in In-Progress Tasks, technical background in Domain Facts, and overflow facts in General Notes.\n"
                "- **Web findings**: Do not turn search/news/URL results into scratchpad entries unless the result is clearly durable and the user would reasonably expect it to be remembered later. Never save them just because they were requested.\n"
                "- **Style**: Each `notes` item must be one single short standalone fact. Never put multiple facts in one item. `append_scratchpad` appends to one section at a time, and `replace_scratchpad` rewrites one section at a time."
            )
        parts.append("")

    persona_memory_section = build_persona_memory_section(persona_memory)
    if persona_memory_section:
        parts.extend(persona_memory_section)

    conversation_memory_section = build_conversation_memory_section(conversation_memory)
    if conversation_memory_section:
        parts.extend(conversation_memory_section)

    if summary_count and conversation_memory_tools_enabled:
        parts.append("## Conversation Memory Priority")
        parts.append(
            "- Earlier turns in this chat have already been summarized or compacted. Treat Conversation Memory as the durable record for older constraints, decisions, and findings, and save newly confirmed details there before more context is lost."
        )
        parts.append("")

    return parts


def _build_runtime_static_parts(
    *,
    user_preferences: str = "",
    runtime_tool_names: list[str],
    clarification_max_questions: int | None = None,
    max_parallel_tools: int | None = None,
    canvas_payload: dict | None = None,
    workspace_root: str | None = None,
) -> list[str]:
    preferences_text = (user_preferences or "").strip()
    persona_memory_tools_enabled = any(
        name in {"save_to_persona_memory", "delete_persona_memory_entry"}
        for name in runtime_tool_names
    )
    conversation_memory_tools_enabled = any(
        name in {"save_to_conversation_memory", "delete_conversation_memory_entry"}
        for name in runtime_tool_names
    )

    parts = [
        "## Assistant Role",
        "- You are a tool-using assistant.",
        "- Base decisions on the conversation state, tool results, and runtime context with minimal redundancy.",
        "- Follow the tool contracts, policies, and runtime guidance below.",
        "",
    ]

    if preferences_text:
        parts.append(
            f"## Core Directives\n"
            f"These rules are mandatory. Apply them in every response without exception — they override all built-in defaults.\n\n"
            f"{preferences_text}\n"
        )

    contract = build_tool_call_contract(
        runtime_tool_names,
        clarification_max_questions=clarification_max_questions,
        max_parallel_tools=max_parallel_tools,
    )
    if contract:
        parts.append("## Tool Calling")
        parts.append(
            "Native function calling is enabled for this turn. Use the Active Tools section later in this prompt for the exact callable set in this turn. "
            "Do not restate tool schemas in regular text.\n"
        )
        for rule in contract["rules"]:
            parts.append(f"- {rule}")
        parts.append("")

        batching_guidance = str(contract.get("batching_guidance") or "").strip()
        if batching_guidance:
            parts.append("## Batching Strategy")
            parts.append(batching_guidance)
            parts.append("")

    policies = []
    clarification_policy = _build_clarification_policy_payload(runtime_tool_names, clarification_max_questions)
    if clarification_policy:
        policies.append(f"**Clarification**: {clarification_policy['guidance']}")
    image_policy = _build_image_policy_payload(runtime_tool_names)
    if image_policy:
        policies.append(f"**Image Follow-up**: {image_policy['guidance']}")

    if policies:
        parts.append("## Important Policies\n" + "\n".join(f"- {policy}" for policy in policies) + "\n")

    if persona_memory_tools_enabled:
        parts.append("## Persona Memory Write Policy")
        parts.append(
            "- **Use save_to_persona_memory** for stable persona-scoped facts that should persist across future conversations using this same persona.\n"
            "- **DO save**: standing persona preferences, recurring conventions, reusable repo or domain facts tied to this persona's work, and durable details broader than one chat but narrower than global scratchpad memory.\n"
            "- **Default away from persona memory**: if the detail only matters for the current chat, save it to conversation memory instead.\n"
            "- **Use scratchpad instead** for truly cross-persona, cross-conversation durable user memory.\n"
            "- **DO NOT save**: one-off tasks, temporary plans, raw tool outputs, or volatile chat state.\n"
            "- **Style**: `key` should be a short label and `value` should be one compact factual line.\n"
            "- **Cleanup**: If an entry becomes wrong or obsolete, remove it with delete_persona_memory_entry."
        )
        parts.append("")

    if conversation_memory_tools_enabled:
        parts.append("## Conversation Memory Write Policy")
        parts.append(
            "- **Use save_to_conversation_memory** proactively and often for important conversation-scoped facts that should survive later turns in this same chat.\n"
            "- **Default choice**: if information mainly matters for this chat, save it to conversation memory rather than the scratchpad.\n"
            "- **DO save**: confirmed user details relevant to this chat, active goals, firm constraints, accepted decisions, discovered repo or environment facts, and critical tool results that may matter later in the conversation.\n"
            "- **Save incrementally**: after important clarifications, tool results, plan changes, and decision points, prefer a new compact record over hoping the detail remains visible in context.\n"
            "- **Especially save before context loss**: details that would be expensive to rediscover after summarization, pruning, or long tool-heavy detours.\n"
            "- **DO NOT save**: raw verbose outputs, broad summaries, speculative inferences, or durable general facts better suited for the scratchpad.\n"
            "- **Style**: `key` should be a short label and `value` should be one compact factual line.\n"
            "- **Prefer multiple small entries**: one fact, decision, or result per memory entry is better than one overloaded summary.\n"
            "- **Prefer update over duplication**: Reuse the same key for the same fact. Saving an existing key refreshes that memory instead of creating noisy duplicates.\n"
            "- **Cleanup**: If an entry becomes wrong or obsolete, remove it with delete_conversation_memory_entry."
        )
        parts.append("")

    canvas_editing_guidance = _build_canvas_editing_guidance(runtime_tool_names, canvas_payload=canvas_payload)
    if canvas_editing_guidance:
        parts.extend(canvas_editing_guidance)

    normalized_workspace_root = str(workspace_root or "").strip()
    if normalized_workspace_root:
        parts.append("## Workspace Sandbox")
        parts.append(f"- Root: {normalized_workspace_root}")
        parts.append("- Scope: All workspace file tools must stay inside this root.")
        parts.append("- Safety: If a batch write tool returns needs_confirmation, wait for explicit user approval before re-running with confirm=true.\n")

    return parts


def build_runtime_context_injection(
    active_tool_names=None,
    clarification_response: dict | None = None,
    all_clarification_rounds: list[dict] | None = None,
    retrieved_context=None,
    tool_trace_context=None,
    tool_memory_context=None,
    user_profile_context=None,
    persona_memory=None,
    conversation_memory=None,
    now=None,
    scratchpad="",
    scratchpad_sections=None,
    canvas_documents=None,
    canvas_active_document_id: str | None = None,
    canvas_viewports: list[dict] | None = None,
    canvas_prompt_max_lines: int | None = None,
    canvas_prompt_max_chars: int | None = None,
    canvas_prompt_max_tokens: int | None = None,
    canvas_prompt_code_line_max_chars: int | None = None,
    canvas_prompt_text_line_max_chars: int | None = None,
    workspace_root: str | None = None,
    runtime_tool_names: list[str] | None = None,
    canvas_payload: dict | None = None,
    summary_count: int = 0,
    include_time_context: bool = True,
    previous_canvas_content_hash: str | None = None,
    include_dynamic_context: bool = False,
    double_check: bool = False,
    double_check_query: str = "",
) -> str:
    normalized_now = (now or datetime.now().astimezone()).astimezone()
    resolved_tool_names = _normalize_tool_name_list(runtime_tool_names)
    if not resolved_tool_names:
        resolved_tool_names = resolve_runtime_tool_names(
            _normalize_tool_name_list(active_tool_names),
            canvas_documents=canvas_documents,
            workspace_root=workspace_root,
        )
    parts: list[str] = []
    if include_dynamic_context:
        parts.extend(
            _build_runtime_dynamic_state_parts(
                runtime_tool_names=resolved_tool_names,
                user_profile_context=user_profile_context,
                persona_memory=persona_memory,
                conversation_memory=conversation_memory,
                scratchpad=scratchpad,
                scratchpad_sections=scratchpad_sections,
                summary_count=summary_count,
            )
        )
    parts.extend(
        _build_runtime_volatile_parts(
            active_tool_names=resolved_tool_names,
            clarification_response=clarification_response,
            all_clarification_rounds=all_clarification_rounds,
            double_check=double_check,
            double_check_query=double_check_query,
            retrieved_context=retrieved_context,
            tool_trace_context=tool_trace_context,
            tool_memory_context=tool_memory_context,
            now=normalized_now,
            canvas_documents=canvas_documents,
            canvas_active_document_id=canvas_active_document_id,
            canvas_viewports=canvas_viewports,
            canvas_prompt_max_lines=canvas_prompt_max_lines,
            canvas_prompt_max_chars=canvas_prompt_max_chars,
            canvas_prompt_max_tokens=canvas_prompt_max_tokens,
            canvas_prompt_code_line_max_chars=canvas_prompt_code_line_max_chars,
            canvas_prompt_text_line_max_chars=canvas_prompt_text_line_max_chars,
            canvas_payload=canvas_payload,
            summary_count=summary_count,
            include_time_context=include_time_context,
            previous_canvas_content_hash=previous_canvas_content_hash,
        )
    )
    return _finalize_prompt_text(parts)


def build_runtime_system_message(
    user_preferences="",
    active_tool_names=None,
    clarification_response: dict | None = None,
    all_clarification_rounds: list[dict] | None = None,
    retrieved_context=None,
    user_profile_context=None,
    persona_memory=None,
    conversation_memory=None,
    tool_trace_context=None,
    tool_memory_context=None,
    now=None,
    scratchpad="",
    scratchpad_sections=None,
    canvas_documents=None,
    canvas_active_document_id: str | None = None,
    canvas_viewports: list[dict] | None = None,
    canvas_prompt_max_lines: int | None = None,
    canvas_prompt_max_chars: int | None = None,
    canvas_prompt_max_tokens: int | None = None,
    canvas_prompt_code_line_max_chars: int | None = None,
    canvas_prompt_text_line_max_chars: int | None = None,
    workspace_root: str | None = None,
    clarification_max_questions: int | None = None,
    max_parallel_tools: int | None = None,
    include_time_context: bool = True,
    include_volatile_context: bool = True,
    include_dynamic_context: bool = True,
    runtime_tool_names: list[str] | None = None,
    canvas_payload: dict | None = None,
    summary_count: int = 0,
    previous_canvas_content_hash: str | None = None,
    double_check: bool = False,
    double_check_query: str = "",
):
    now = (now or datetime.now().astimezone()).astimezone()
    configured_tool_names = _normalize_tool_name_list(active_tool_names)
    resolved_runtime_tool_names = _normalize_tool_name_list(runtime_tool_names)
    if not resolved_runtime_tool_names:
        resolved_runtime_tool_names = resolve_runtime_tool_names(
            configured_tool_names,
            canvas_documents=canvas_documents,
            workspace_root=workspace_root,
        )
    runtime_tool_names = resolved_runtime_tool_names
    if canvas_payload is None:
        canvas_payload = _build_canvas_prompt_payload(
            canvas_documents,
            active_document_id=canvas_active_document_id,
            canvas_viewports=canvas_viewports,
            max_lines=canvas_prompt_max_lines or CANVAS_PROMPT_MAX_LINES,
            max_chars=canvas_prompt_max_chars,
            max_tokens=canvas_prompt_max_tokens if canvas_prompt_max_tokens is not None else CANVAS_PROMPT_MAX_TOKENS,
            code_line_max_chars=canvas_prompt_code_line_max_chars,
            text_line_max_chars=canvas_prompt_text_line_max_chars,
        )
    
    parts = _build_runtime_static_parts(
        user_preferences=user_preferences,
        runtime_tool_names=runtime_tool_names,
        clarification_max_questions=clarification_max_questions,
        max_parallel_tools=max_parallel_tools,
        canvas_payload=canvas_payload,
        workspace_root=workspace_root,
    )

    if include_dynamic_context:
        parts.extend(
            _build_runtime_dynamic_state_parts(
                runtime_tool_names=runtime_tool_names,
                user_profile_context=user_profile_context,
                persona_memory=persona_memory,
                conversation_memory=conversation_memory,
                scratchpad=scratchpad,
                scratchpad_sections=scratchpad_sections,
                summary_count=summary_count,
            )
        )

    if include_volatile_context:
        parts.extend(
            _build_runtime_volatile_parts(
                active_tool_names=runtime_tool_names,
                clarification_response=clarification_response,
                all_clarification_rounds=all_clarification_rounds,
                double_check=double_check,
                double_check_query=double_check_query,
                retrieved_context=retrieved_context,
                tool_trace_context=tool_trace_context,
                tool_memory_context=tool_memory_context,
                now=now,
                canvas_documents=canvas_documents,
                canvas_active_document_id=canvas_active_document_id,
                canvas_viewports=canvas_viewports,
                canvas_prompt_max_lines=canvas_prompt_max_lines,
                canvas_prompt_max_chars=canvas_prompt_max_chars,
                canvas_prompt_max_tokens=canvas_prompt_max_tokens,
                canvas_prompt_code_line_max_chars=canvas_prompt_code_line_max_chars,
                canvas_prompt_text_line_max_chars=canvas_prompt_text_line_max_chars,
                canvas_payload=canvas_payload,
                summary_count=summary_count,
                include_time_context=include_time_context,
                previous_canvas_content_hash=previous_canvas_content_hash,
            )
        )
    elif include_time_context:
        parts.append(_build_current_time_context(now))

    return {
        "role": "system",
        "content": _finalize_prompt_text(parts),
    }


def prepend_runtime_context(
    messages,
    user_preferences="",
    active_tool_names=None,
    clarification_response: dict | None = None,
    all_clarification_rounds: list[dict] | None = None,
    retrieved_context=None,
    user_profile_context=None,
    persona_memory=None,
    conversation_memory=None,
    tool_trace_context=None,
    tool_memory_context=None,
    scratchpad="",
    scratchpad_sections=None,
    canvas_documents=None,
    canvas_active_document_id: str | None = None,
    canvas_viewports: list[dict] | None = None,
    canvas_prompt_max_lines: int | None = None,
    canvas_prompt_max_chars: int | None = None,
    canvas_prompt_max_tokens: int | None = None,
    canvas_prompt_code_line_max_chars: int | None = None,
    canvas_prompt_text_line_max_chars: int | None = None,
    workspace_root: str | None = None,
    clarification_max_questions: int | None = None,
    max_parallel_tools: int | None = None,
    runtime_tool_names: list[str] | None = None,
    current_context_injection: str | None = None,
    summary_count: int | None = None,
    runtime_message: dict | None = None,
    now: datetime | None = None,
    previous_canvas_content_hash: str | None = None,
    double_check: bool = False,
    double_check_query: str = "",
):
    normalized_now = (now or datetime.now().astimezone()).astimezone()
    resolved_runtime_tool_names = _normalize_tool_name_list(runtime_tool_names)
    if not resolved_runtime_tool_names:
        resolved_runtime_tool_names = resolve_runtime_tool_names(
            _normalize_tool_name_list(active_tool_names),
            canvas_documents=canvas_documents,
            workspace_root=workspace_root,
        )
    injection_content = str(current_context_injection or "").strip()
    canvas_payload = None
    if runtime_message is None or not injection_content:
        canvas_payload = _build_canvas_prompt_payload(
            canvas_documents,
            active_document_id=canvas_active_document_id,
            canvas_viewports=canvas_viewports,
            max_lines=canvas_prompt_max_lines or CANVAS_PROMPT_MAX_LINES,
            max_chars=canvas_prompt_max_chars,
            max_tokens=canvas_prompt_max_tokens if canvas_prompt_max_tokens is not None else CANVAS_PROMPT_MAX_TOKENS,
            code_line_max_chars=canvas_prompt_code_line_max_chars,
            text_line_max_chars=canvas_prompt_text_line_max_chars,
        )

    if isinstance(runtime_message, dict):
        runtime_message = {
            "role": str(runtime_message.get("role") or "system"),
            "content": str(runtime_message.get("content") or ""),
        }
    else:
        runtime_message = build_runtime_system_message(
            user_preferences,
            active_tool_names or [],
            clarification_response=clarification_response,
            all_clarification_rounds=all_clarification_rounds,
            double_check=double_check,
            double_check_query=double_check_query,
            retrieved_context=retrieved_context,
            user_profile_context=user_profile_context,
            persona_memory=persona_memory,
            conversation_memory=conversation_memory,
            tool_trace_context=tool_trace_context,
            tool_memory_context=tool_memory_context,
            scratchpad=scratchpad,
            scratchpad_sections=scratchpad_sections,
            canvas_documents=canvas_documents,
            canvas_active_document_id=canvas_active_document_id,
            canvas_viewports=canvas_viewports,
            canvas_prompt_max_lines=canvas_prompt_max_lines,
            canvas_prompt_max_chars=canvas_prompt_max_chars,
            canvas_prompt_max_tokens=canvas_prompt_max_tokens,
            canvas_prompt_code_line_max_chars=canvas_prompt_code_line_max_chars,
            canvas_prompt_text_line_max_chars=canvas_prompt_text_line_max_chars,
            workspace_root=workspace_root,
            clarification_max_questions=clarification_max_questions,
            max_parallel_tools=max_parallel_tools,
            include_time_context=False,
            include_volatile_context=False,
            include_dynamic_context=False,
            runtime_tool_names=resolved_runtime_tool_names,
            canvas_payload=canvas_payload,
            now=normalized_now,
        )

    normalized_summary_count = summary_count if summary_count is not None else _count_summary_messages(messages)
    if not injection_content:
        if canvas_payload is None:
            canvas_payload = _build_canvas_prompt_payload(
                canvas_documents,
                active_document_id=canvas_active_document_id,
                canvas_viewports=canvas_viewports,
                max_lines=canvas_prompt_max_lines or CANVAS_PROMPT_MAX_LINES,
                max_chars=canvas_prompt_max_chars,
                max_tokens=canvas_prompt_max_tokens if canvas_prompt_max_tokens is not None else CANVAS_PROMPT_MAX_TOKENS,
                code_line_max_chars=canvas_prompt_code_line_max_chars,
                text_line_max_chars=canvas_prompt_text_line_max_chars,
            )
        injection_content = build_runtime_context_injection(
            active_tool_names=active_tool_names or [],
            clarification_response=clarification_response,
            all_clarification_rounds=all_clarification_rounds,
            double_check=double_check,
            double_check_query=double_check_query,
            retrieved_context=retrieved_context,
            tool_trace_context=tool_trace_context,
            tool_memory_context=tool_memory_context,
            user_profile_context=user_profile_context,
            persona_memory=persona_memory,
            conversation_memory=conversation_memory,
            scratchpad=scratchpad,
            scratchpad_sections=scratchpad_sections,
            canvas_documents=canvas_documents,
            canvas_active_document_id=canvas_active_document_id,
            canvas_viewports=canvas_viewports,
            canvas_prompt_max_lines=canvas_prompt_max_lines,
            canvas_prompt_max_chars=canvas_prompt_max_chars,
            canvas_prompt_max_tokens=canvas_prompt_max_tokens,
            canvas_prompt_code_line_max_chars=canvas_prompt_code_line_max_chars,
            canvas_prompt_text_line_max_chars=canvas_prompt_text_line_max_chars,
            workspace_root=workspace_root,
            runtime_tool_names=resolved_runtime_tool_names,
            canvas_payload=canvas_payload,
            summary_count=normalized_summary_count,
            include_time_context=True,
            now=normalized_now,
            previous_canvas_content_hash=previous_canvas_content_hash,
            include_dynamic_context=True,
        )

    if not injection_content:
        return [runtime_message, *messages]

    insertion_index = len(messages)
    for index in range(len(messages) - 1, -1, -1):
        if str(messages[index].get("role") or "").strip() == "user":
            insertion_index = index
            break

    return [
        runtime_message,
        *messages[:insertion_index],
        {
            "role": "system",
            "content": injection_content,
        },
        *messages[insertion_index:],
    ]
