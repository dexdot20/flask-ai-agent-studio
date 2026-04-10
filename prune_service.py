from __future__ import annotations

import logging
from typing import Any

from config import PRUNING_MIN_TARGET_TOKENS, PRUNING_TARGET_REDUCTION_RATIO
from db import (
    get_app_settings,
    get_conversation_message_rows,
    get_db,
    get_pruning_min_target_tokens,
    get_pruning_target_reduction_ratio,
    message_row_to_dict,
    parse_message_metadata,
    serialize_message_metadata,
)
from model_registry import (
    DEEPSEEK_PROVIDER,
    DEFAULT_CHAT_MODEL,
    apply_model_target_request_options,
    get_operation_model,
    get_provider_client,
    resolve_model_target,
)
from token_utils import estimate_text_tokens

PRUNABLE_ROLES = {"user", "assistant"}
PRUNING_MODEL = DEFAULT_CHAT_MODEL
client = get_provider_client(DEEPSEEK_PROVIDER)
PRUNING_SYSTEM_PROMPT = (
    "You are a specialized text refinement AI. Your goal is to rewrite a single chat message for conciseness while strictly preserving the original language, core meaning, intent, tone, and all critical facts.\n"
    "Do not delete, summarize, or paraphrase code blocks, commands, logs, JSON, tables, numbers, URLs, identifiers, API names, configuration values, or other technical data.\n"
    "Preserve unresolved questions, decisions, constraints, requested follow-ups, and references that later turns may rely on.\n"
    "When you encounter those sections, keep those sections verbatim and only trim truly redundant surrounding prose.\n"
    "Return only the refined message text without conversational filler or markdown artifacts."
)
PRUNING_CONTEXT_MESSAGE_MAX_CHARS = 700
PRUNING_CONTEXT_NEIGHBOR_COUNT = 2
PRUNING_MAX_ATTEMPTS = 2
LOGGER = logging.getLogger(__name__)


def _extract_response_text(response: Any) -> str:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
        return "".join(parts).strip()
    return str(content or "").strip()


def _estimate_pruning_target_tokens(
    content: str,
    reduction_ratio: float = PRUNING_TARGET_REDUCTION_RATIO,
    min_target_tokens: int = PRUNING_MIN_TARGET_TOKENS,
) -> int:
    estimated_tokens = estimate_text_tokens(content)
    if estimated_tokens <= 0:
        return 1

    target_tokens = max(1, int(estimated_tokens * float(reduction_ratio)))
    if estimated_tokens < min_target_tokens:
        return min(estimated_tokens, target_tokens)
    return max(min_target_tokens, target_tokens)


def _build_pruning_context_hint(conversation_id: int, message_id: int) -> str:
    normalized_conversation_id = int(conversation_id or 0)
    normalized_message_id = int(message_id or 0)
    if normalized_conversation_id <= 0 or normalized_message_id <= 0:
        return ""

    with get_db() as conn:
        rows = get_conversation_message_rows(conn, normalized_conversation_id)

    visible_messages = [message_row_to_dict(row) for row in rows]
    current_index = next(
        (index for index, message in enumerate(visible_messages) if int(message.get("id") or 0) == normalized_message_id),
        -1,
    )
    if current_index < 0:
        return ""

    def format_neighbor(label: str, message: dict) -> str:
        role = str(message.get("role") or "").strip() or "message"
        content = str(message.get("content") or "").strip()
        if not content:
            return ""
        if len(content) > PRUNING_CONTEXT_MESSAGE_MAX_CHARS:
            content = content[:PRUNING_CONTEXT_MESSAGE_MAX_CHARS].rstrip() + "..."
        return f"{label} ({role}): {content}"

    context_lines: list[str] = []
    previous_lines: list[str] = []
    for index in range(current_index - 1, -1, -1):
        neighbor = visible_messages[index]
        if not str(neighbor.get("content") or "").strip():
            continue
        snippet = format_neighbor("Previous visible message", neighbor)
        if snippet:
            previous_lines.append(snippet)
            if len(previous_lines) >= PRUNING_CONTEXT_NEIGHBOR_COUNT:
                break

    context_lines.extend(reversed(previous_lines))

    next_lines: list[str] = []
    for index in range(current_index + 1, len(visible_messages)):
        neighbor = visible_messages[index]
        if not str(neighbor.get("content") or "").strip():
            continue
        snippet = format_neighbor("Next visible message", neighbor)
        if snippet:
            next_lines.append(snippet)
            if len(next_lines) >= PRUNING_CONTEXT_NEIGHBOR_COUNT:
                break

    context_lines.extend(next_lines)

    return "\n".join(context_lines).strip()


def _estimate_pruning_max_output_tokens(target_tokens: int) -> int:
    normalized_target = max(1, int(target_tokens or 1))
    return max(256, min(4000, max(normalized_target + 96, int(normalized_target * 1.5))))


def _build_pruning_messages(
    content: str,
    target_tokens: int | None = None,
    context_hint: str = "",
    role: str = "",
    retry_instruction: str = "",
) -> list[dict[str, str]]:
    normalized_target_tokens = max(1, int(target_tokens or estimate_text_tokens(content) or 1))
    normalized_context_hint = str(context_hint or "").strip()
    normalized_role = str(role or "").strip() or "message"
    normalized_retry_instruction = str(retry_instruction or "").strip()
    user_prompt_parts = [
        "Preserve the message's core idea, critical details, technical accuracy, unresolved questions, user constraints, and action items; only reduce unnecessary repetition, indirect phrasing, and filler.",
        "Code blocks, logs, JSON, tables, numbers, commands, URLs, and other sensitive technical data must be kept verbatim; do not rewrite, summarize, or delete those sections.",
        f"Target message role: {normalized_role}.",
        f"Aim for roughly {normalized_target_tokens} tokens while keeping the message faithful and readable.",
    ]
    if normalized_retry_instruction:
        user_prompt_parts.append(f"Retry instruction:\n{normalized_retry_instruction}")
    if normalized_context_hint:
        user_prompt_parts.append(
            "Conversation context below is reference-only. Do not rewrite it; use it only to judge which details in the target message must survive pruning."
        )
        user_prompt_parts.append(f"Conversation context:\n{normalized_context_hint}")
    user_prompt_parts.append(f"Target message:\n{content}")
    return [
        {"role": "system", "content": PRUNING_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "\n\n".join(user_prompt_parts),
        },
    ]


def is_prunable_message(message: dict) -> bool:
    role = str(message.get("role") or "").strip()
    if role not in PRUNABLE_ROLES:
        return False
    if role == "assistant" and message.get("tool_calls"):
        return False
    metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
    if metadata.get("is_summary") is True or metadata.get("is_pruned") is True:
        return False
    return bool(str(message.get("content") or "").strip())


def _load_message_row(message_id: int):
    with get_db() as conn:
        return conn.execute(
        """SELECT id, conversation_id, position, role, content, metadata, tool_calls, tool_call_id,
                  prompt_tokens, completion_tokens, total_tokens, deleted_at
           FROM messages
           WHERE id = ? AND deleted_at IS NULL""",
            (message_id,),
        ).fetchone()


def _persist_pruned_message(message_id: int, pruned_content: str, metadata: dict) -> dict:
    serialized_metadata = serialize_message_metadata(metadata)
    with get_db() as conn:
        conn.execute(
            "UPDATE messages SET content = ?, metadata = ? WHERE id = ?",
            (pruned_content, serialized_metadata, message_id),
        )
        updated_row = conn.execute(
            """SELECT id, position, role, content, metadata, tool_calls, tool_call_id,
                      prompt_tokens, completion_tokens, total_tokens, deleted_at
               FROM messages
               WHERE id = ?""",
            (message_id,),
        ).fetchone()
    return message_row_to_dict(updated_row)


def prune_message(message_id: int) -> dict:
    row = _load_message_row(message_id)
    if not row:
        raise ValueError("Message not found.")

    message = message_row_to_dict(row)
    if not is_prunable_message(message):
        raise ValueError("Only visible user or assistant messages can be pruned.")

    original_content = str(message.get("content") or "")
    metadata = parse_message_metadata(message.get("metadata"))

    settings = get_app_settings()
    pruning_target_reduction_ratio = get_pruning_target_reduction_ratio(settings)
    pruning_min_target_tokens = get_pruning_min_target_tokens(settings)
    target_tokens = _estimate_pruning_target_tokens(
        original_content,
        pruning_target_reduction_ratio,
        pruning_min_target_tokens,
    )
    context_hint = _build_pruning_context_hint(int(row["conversation_id"] or 0), int(row["id"] or 0))
    pruning_model = get_operation_model("prune", settings, fallback_model_id=PRUNING_MODEL)
    target = resolve_model_target(pruning_model, settings)

    pruned_content = ""
    retry_instruction = ""
    for attempt in range(PRUNING_MAX_ATTEMPTS):
        request_kwargs = apply_model_target_request_options(
            {
                "model": target["api_model"],
                "messages": _build_pruning_messages(
                    original_content,
                    target_tokens=target_tokens,
                    context_hint=context_hint,
                    role=message.get("role") or "",
                    retry_instruction=retry_instruction,
                ),
                "max_tokens": _estimate_pruning_max_output_tokens(target_tokens),
                "temperature": 0.15 if attempt > 0 else 0.2,
            },
            target,
        )
        response = target["client"].chat.completions.create(**request_kwargs)
        pruned_content = _extract_response_text(response)
        if pruned_content:
            break
        retry_instruction = (
            "The previous attempt returned empty content. Return only a faithful pruned rewrite of the target "
            "message and keep all technical details intact."
        )

    if not pruned_content:
        raise ValueError("Pruning model returned empty content.")

    metadata["pruned_original"] = original_content
    metadata["is_pruned"] = True
    pruned_message = _persist_pruned_message(message_id, pruned_content, metadata)
    pruned_message["conversation_id"] = int(row["conversation_id"] or 0)
    return pruned_message


def prune_conversation_batch(conversation_id: int, batch_size: int) -> int:
    normalized_conversation_id = int(conversation_id or 0)
    normalized_batch_size = max(1, min(50, int(batch_size or 1)))
    if normalized_conversation_id <= 0:
        return 0

    with get_db() as conn:
        rows = get_conversation_message_rows(conn, normalized_conversation_id)
        messages = [message_row_to_dict(row) for row in rows]
        candidate_ids = [
            message["id"]
            for message in sorted(
                (message for message in messages if is_prunable_message(message)),
                key=lambda message: estimate_text_tokens(str(message.get("content") or "")),
                reverse=True,
            )[:normalized_batch_size]
        ]

    pruned_count = 0
    for message_id in candidate_ids:
        try:
            prune_message(message_id)
        except Exception:
            LOGGER.exception("Failed to prune message %s during batch pruning.", message_id)
            continue
        pruned_count += 1

    if pruned_count:
        with get_db() as conn:
            conn.execute(
                "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
                (normalized_conversation_id,),
            )
    return pruned_count