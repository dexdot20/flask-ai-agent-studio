# ruff: noqa: I001
from __future__ import annotations

import ast
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
import html
import json
import logging
import math
import os
import threading
import time
from typing import Any

import re
import string
from logging.handlers import RotatingFileHandler
from urllib.parse import urlparse
from uuid import uuid4

from canvas_service import (
    batch_read_canvas_documents,
    batch_canvas_edits,
    build_canvas_document_result_snapshot,
    build_canvas_document_context_result,
    build_canvas_tool_result,
    CANVAS_MUTATING_TOOL_NAMES,
    clear_canvas_viewport,
    clear_overlapping_canvas_viewports,
    clear_canvas,
    compute_canvas_content_hash,
    create_canvas_document,
    create_canvas_runtime_state,
    delete_canvas_document,
    delete_canvas_lines,
    find_canvas_document,
    focus_canvas_page,
    get_canvas_runtime_active_document_id,
    get_canvas_runtime_documents,
    get_canvas_runtime_snapshot,
    get_canvas_viewport_payloads,
    insert_canvas_lines,
    join_canvas_lines,
    list_canvas_lines,
    preview_canvas_changes,
    replace_canvas_lines,
    rewrite_canvas_document,
    search_canvas_document,
    set_canvas_viewport,
    scroll_canvas_document,
    scale_canvas_char_limit,
    transform_canvas_lines,
    update_canvas_metadata,
    validate_canvas_document,
)
from github_import_service import import_github_repository_into_canvas, preview_github_repository_for_canvas
from project_workspace_service import (
    create_directory as workspace_create_directory,
    create_file as workspace_create_file,
    create_workspace_runtime_state,
    get_workspace_root,
    list_dir as workspace_list_dir,
    read_file as workspace_read_file,
    search_files as workspace_search_files,
    update_file as workspace_update_file,
    validate_project_workspace,
    write_project_tree,
)
from config import (
    AGENT_CONTEXT_COMPACTION_KEEP_RECENT_ROUNDS,
    AGENT_CONTEXT_COMPACTION_THRESHOLD,
    AGENT_TRACE_LOG_ENABLED,
    AGENT_TRACE_LOG_INCLUDE_RAW,
    AGENT_TOOL_RESULT_TRANSCRIPT_MAX_CHARS,
    AGENT_TRACE_LOG_PATH,
    CONVERSATION_MEMORY_ENABLED,
    DEFAULT_SETTINGS,
    DEFAULT_MAX_PARALLEL_TOOLS,
    FETCH_RAW_TOOL_RESULT_MAX_TEXT_CHARS,
    FETCH_SUMMARIZE_MAX_INPUT_CHARS,
    FETCH_SUMMARIZE_MAX_OUTPUT_TOKENS,
    FETCH_SUMMARY_MAX_CHARS,
    FETCH_SUMMARY_TOKEN_THRESHOLD,
    MAX_PARALLEL_TOOLS_MAX,
    MAX_PARALLEL_TOOLS_MIN,
    PROMPT_MAX_INPUT_TOKENS,
    RAG_SEARCH_DEFAULT_TOP_K,
    RAG_TOOL_RESULT_MAX_TEXT_CHARS,
    RAG_TOOL_RESULT_SUMMARY_MAX_CHARS,
    SCRATCHPAD_SECTION_METADATA,
    SCRATCHPAD_SECTION_ORDER,
    SUB_AGENT_ALLOWED_TOOL_NAMES as DEFAULT_SUB_AGENT_ALLOWED_TOOL_NAMES,
    TOOL_MEMORY_ENABLED,
)
from db import (
    append_to_scratchpad,
    count_scratchpad_notes,
    delete_conversation_memory_entry,
    delete_persona_memory_entry,
    delete_tool_memory_entry,
    get_context_compaction_keep_recent_rounds,
    get_context_compaction_threshold,
    get_effective_conversation_persona,
    get_fetch_url_clip_aggressiveness,
    get_fetch_url_summarized_max_input_chars,
    get_fetch_url_summarized_max_output_tokens,
    get_fetch_url_token_threshold,
    get_all_scratchpad_sections,
    get_app_settings,
    get_db,
    get_clarification_max_questions,
    get_message_tool_result_content,
    get_model_temperature,
    get_prompt_max_input_tokens,
    get_rag_source_types,
    get_search_tool_query_limit,
    get_sub_agent_max_steps,
    get_sub_agent_max_parallel_tools,
    get_sub_agent_retry_attempts,
    get_sub_agent_retry_delay_seconds,
    get_sub_agent_timeout_seconds,
    insert_conversation_memory_entry,
    insert_persona_memory_entry,
    insert_tool_memory_entry,
    list_tool_memory_entries,
    parse_message_tool_calls,
    read_image_asset_bytes,
    replace_scratchpad,
)
from messages import (
    _build_canvas_prompt_payload,
    _build_pending_clarification_message_content,
    build_current_time_context,
    CANVAS_RUNTIME_CONTEXT_INSERT_BEFORE_HEADINGS,
    CANVAS_RUNTIME_CONTEXT_REFRESH_HEADINGS,
    refresh_canvas_sections_in_context_injection,
)
from image_service import answer_image_question
from model_registry import (
    DEEPSEEK_PROVIDER,
    apply_chat_parameter_overrides,
    apply_model_target_request_options,
    build_model_target_tool_choice_fallback_request,
    build_openrouter_cache_estimate_context,
    model_target_supports_native_reasoning_continuation,
    get_operation_model_candidates,
    get_operation_model,
    get_model_pricing as lookup_model_pricing,
    get_provider_client,
    has_known_model_pricing as lookup_has_known_model_pricing,
    resolve_model_target,
    should_retry_model_target_tool_choice_with_auto,
)
from rag_service import (
    get_exact_tool_memory_match,
    search_knowledge_base_tool,
    upsert_tool_memory_result,
)
from tool_registry import (
    CANVAS_READ_BARRIER_TOOL_NAMES,
    TOOL_SPEC_BY_NAME,
    WEB_TOOL_NAMES,
    get_tool_runtime_metadata,
    get_ui_hidden_tool_names,
    get_openai_tool_specs,
    is_tool_parallel_safe,
    is_tool_session_cacheable,
)
from token_utils import estimate_text_tokens
from web_tools import (
    fetch_url_tool,
    grep_fetched_content_tool,
    search_news_ddgs_tool,
    search_news_google_tool,
    search_web_tool,
    scroll_fetched_content_tool,
)
from video_transcript_service import (
    build_video_transcript_context_block,
    normalize_youtube_url,
    transcribe_youtube_video,
)

SUB_AGENT_ALLOWED_TOOL_NAMES = DEFAULT_SUB_AGENT_ALLOWED_TOOL_NAMES

FINAL_ANSWER_ERROR_TEXT = "The model returned an invalid tool instruction and no final answer could be produced."
FINAL_ANSWER_MISSING_TEXT = "The model did not produce a final answer in assistant content."
CONTEXT_OVERFLOW_RECOVERY_ERROR_TEXT = (
    "Context window is full and cannot be compacted further. "
    "Try starting a new conversation, disabling RAG or large canvas content, or reducing the request size."
)
USER_CANCELLED_ERROR_TEXT = "Cancelled by user."
MISSING_FINAL_ANSWER_MARKER = "[INSTRUCTION: MISSING FINAL ANSWER"
TOOL_EXECUTION_RESULTS_MARKER = "[TOOL EXECUTION RESULTS]"
REASONING_REPLAY_MARKER = "[AGENT REASONING CONTEXT]"
MAX_REASONING_REPLAY_ENTRIES = 2
MAX_REASONING_REPLAY_CHARS = 4_000
MAX_REASONING_REPLAY_TOTAL_CHARS = 10_000
CANVAS_STREAM_CONTENT_TOOL_NAMES = {
    "create_canvas_document",
    "rewrite_canvas_document",
}
CANVAS_STREAM_REPLACE_CONTENT_TOOL_NAMES = {
    "batch_canvas_edits",
    "transform_canvas_lines",
    "replace_canvas_lines",
    "insert_canvas_lines",
    "delete_canvas_lines",
}
# Derived: all tools that open a streaming canvas operation.
CANVAS_STREAM_OPEN_TOOL_NAMES = CANVAS_STREAM_CONTENT_TOOL_NAMES | CANVAS_STREAM_REPLACE_CONTENT_TOOL_NAMES
CANVAS_CONTEXT_READ_TOOL_NAMES = {
    "expand_canvas_document",
    "batch_read_canvas_documents",
    "scroll_canvas_document",
}
# All canvas read/inspect tools (superset of CANVAS_CONTEXT_READ_TOOL_NAMES).
# Used by the canvas dependency barrier and the self-read guard to identify
# tools that must not observe stale pre-mutation canvas state.
CANVAS_ALL_READ_TOOL_NAMES = set(CANVAS_READ_BARRIER_TOOL_NAMES)
# CANVAS_MUTATION_TOOL_NAMES: alias for the authoritative set imported from canvas_service.
CANVAS_MUTATION_TOOL_NAMES = CANVAS_MUTATING_TOOL_NAMES
# Derived: all canvas-related tool names (mutations + reads).
CANVAS_TOOL_NAMES = CANVAS_MUTATION_TOOL_NAMES | CANVAS_CONTEXT_READ_TOOL_NAMES | CANVAS_ALL_READ_TOOL_NAMES
# Derived: runtime section markers are the canvas sections that get refreshed
# each turn plus the insert-before anchors and the time section.
RUNTIME_CONTEXT_INJECTION_SECTION_MARKERS = (
    CANVAS_RUNTIME_CONTEXT_REFRESH_HEADINGS
    | set(CANVAS_RUNTIME_CONTEXT_INSERT_BEFORE_HEADINGS)
    | {"## Current Date and Time"}
)
DSML_INVOKE_TAG_RE = re.compile(r'<[^>]*invoke\s+name="(?P<name>[^"]+)"[^>]*>', re.IGNORECASE)
DSML_FUNCTION_CALLS_TAG_RE = re.compile(r"<[^>]*function_calls[^>]*>", re.IGNORECASE)
DSML_PARAMETER_TAG_RE = re.compile(
    r'<[^>]*parameter\s+name="(?P<name>[^"]+)"(?P<attrs>[^>]*)>(?P<value>.*?)</[^>]*parameter\s*>',
    re.IGNORECASE | re.DOTALL,
)
DSML_STRING_ATTR_RE = re.compile(r'\bstring\s*=\s*["\']true["\']', re.IGNORECASE)
TOOL_ARGUMENT_CODE_FENCE_RE = re.compile(
    r"^\s*```(?:json|javascript|js|python|py)?\s*(?P<body>.*?)\s*```\s*$",
    re.IGNORECASE | re.DOTALL,
)
_VALID_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
TOOL_ARGUMENT_LANGUAGE_LABELS = {"json", "javascript", "js", "python", "py"}
SEARCH_QUERY_BATCHED_TOOL_NAMES = {
    "search_web",
    "search_news_ddgs",
    "search_news_google",
}
SEARCH_QUERY_ARGUMENT_ALIASES = (
    "queries",
    "query",
    "search_queries",
    "search_query",
    "q",
)
SEARCH_MEMORY_PROMOTION_MATCH_LIMIT = 2
SEARCH_MEMORY_PROMOTION_EXCERPT_LIMIT = 180
SUB_AGENT_MAX_TRANSCRIPT_MESSAGES = 24
SUB_AGENT_MAX_MESSAGE_CONTENT_CHARS = 4_000
SUB_AGENT_MAX_REASONING_CHARS = 4_000
SUB_AGENT_MAX_SUMMARY_CHARS = 4_000
SUB_AGENT_MAX_ERROR_CHARS = 800
SUB_AGENT_MAX_ARTIFACTS = 16
INPUT_BREAKDOWN_KEYS = (
    "core_instructions",
    "tool_specs",
    "canvas",
    "scratchpad",
    "tool_trace",
    "tool_memory",
    "rag_context",
    "internal_state",
    "user_messages",
    "assistant_history",
    "assistant_tool_calls",
    "tool_results",
    "unknown_provider_overhead",
)
_AGENT_TRACE_LOGGER = None
_AGENT_TRACE_LOGGER_LOCK = threading.Lock()


def _get_default_deepseek_client():
    return get_provider_client(DEEPSEEK_PROVIDER)


client = _get_default_deepseek_client()


def _get_agent_trace_logger():
    if not AGENT_TRACE_LOG_ENABLED:
        return None

    global _AGENT_TRACE_LOGGER
    if _AGENT_TRACE_LOGGER is not None:
        return _AGENT_TRACE_LOGGER

    with _AGENT_TRACE_LOGGER_LOCK:
        if _AGENT_TRACE_LOGGER is not None:
            return _AGENT_TRACE_LOGGER

        logger = logging.getLogger("chatbot.agent.trace")
        target_log_path = os.path.abspath(AGENT_TRACE_LOG_PATH)
        has_target_handler = any(
            isinstance(handler, RotatingFileHandler)
            and os.path.abspath(str(getattr(handler, "baseFilename", ""))) == target_log_path
            for handler in logger.handlers
        )
        if not has_target_handler:
            log_dir = os.path.dirname(target_log_path)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            handler = RotatingFileHandler(target_log_path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        _AGENT_TRACE_LOGGER = logger
        return logger


def get_model_pricing(model_id: str, settings: dict | None = None) -> dict:
    current_settings = settings if isinstance(settings, dict) else get_app_settings()
    return lookup_model_pricing(model_id, current_settings)


def has_known_model_pricing(model_id: str, settings: dict | None = None) -> bool:
    current_settings = settings if isinstance(settings, dict) else get_app_settings()
    return lookup_has_known_model_pricing(model_id, current_settings)


def _coerce_usage_int(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _extract_usage_metrics(usage) -> dict[str, int]:
    fields = (
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "prompt_cache_hit_tokens",
        "prompt_cache_miss_tokens",
        "prompt_cache_write_tokens",
    )
    payload: dict = {}

    if isinstance(usage, dict):
        payload.update(usage)
    elif usage is not None:
        model_dump = getattr(usage, "model_dump", None)
        if callable(model_dump):
            try:
                dumped = model_dump()
            except TypeError:
                dumped = None
            if isinstance(dumped, dict):
                payload.update(dumped)
        else:
            dict_method = getattr(usage, "dict", None)
            if callable(dict_method):
                try:
                    dumped = dict_method()
                except TypeError:
                    dumped = None
                if isinstance(dumped, dict):
                    payload.update(dumped)

        model_extra = getattr(usage, "model_extra", None)
        if isinstance(model_extra, dict):
            payload.update(model_extra)

        for key in fields:
            attr_value = getattr(usage, key, None)
            if attr_value is not None:
                payload[key] = attr_value

    prompt_cache_hit_present = (
        "prompt_cache_hit_tokens" in payload and payload.get("prompt_cache_hit_tokens") is not None
    )
    prompt_cache_miss_present = (
        "prompt_cache_miss_tokens" in payload and payload.get("prompt_cache_miss_tokens") is not None
    )
    prompt_cache_write_present = (
        "prompt_cache_write_tokens" in payload and payload.get("prompt_cache_write_tokens") is not None
    )
    prompt_tokens_present = "prompt_tokens" in payload and payload.get("prompt_tokens") is not None
    completion_tokens_present = "completion_tokens" in payload and payload.get("completion_tokens") is not None
    total_tokens_present = "total_tokens" in payload and payload.get("total_tokens") is not None

    # Normalize OpenRouter prompt_tokens_details.cached_tokens → prompt_cache_hit_tokens
    if not prompt_cache_hit_present:
        prompt_tokens_details = payload.get("prompt_tokens_details")
        if isinstance(prompt_tokens_details, dict):
            cached = prompt_tokens_details.get("cached_tokens")
        elif prompt_tokens_details is not None:
            cached = getattr(prompt_tokens_details, "cached_tokens", None)
        else:
            cached = None
        if cached is not None:
            payload["prompt_cache_hit_tokens"] = cached
            prompt_cache_hit_present = True

    if not prompt_cache_write_present:
        prompt_tokens_details = payload.get("prompt_tokens_details")
        if isinstance(prompt_tokens_details, dict):
            cache_write_tokens = prompt_tokens_details.get("cache_write_tokens")
        elif prompt_tokens_details is not None:
            cache_write_tokens = getattr(prompt_tokens_details, "cache_write_tokens", None)
        else:
            cache_write_tokens = payload.get("cache_write_tokens")
        if cache_write_tokens is not None:
            payload["prompt_cache_write_tokens"] = cache_write_tokens
            prompt_cache_write_present = True

    metrics = {key: _coerce_usage_int(payload.get(key)) for key in fields}
    metrics["cache_hit_present"] = prompt_cache_hit_present
    metrics["cache_miss_present"] = prompt_cache_miss_present
    metrics["cache_write_present"] = prompt_cache_write_present
    metrics["cache_metrics_present"] = (
        prompt_cache_hit_present or prompt_cache_miss_present or prompt_cache_write_present
    )
    metrics["usage_fields_present"] = (
        prompt_tokens_present
        or completion_tokens_present
        or total_tokens_present
        or prompt_cache_hit_present
        or prompt_cache_miss_present
        or prompt_cache_write_present
    )
    metrics["raw"] = dict(payload)
    return metrics


def _empty_input_breakdown() -> dict[str, int]:
    return {key: 0 for key in INPUT_BREAKDOWN_KEYS}


def _estimate_text_tokens(text: str) -> int:
    return estimate_text_tokens(text)


def _estimate_serialized_tokens(value) -> int:
    if value in (None, "", [], {}):
        return 0
    try:
        serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        serialized = str(value)
    return _estimate_text_tokens(serialized)


def _shared_prefix_char_count(left: str, right: str) -> int:
    if not left or not right:
        return 0
    limit = min(len(left), len(right))
    index = 0
    while index < limit and left[index] == right[index]:
        index += 1
    return index


def _estimate_openrouter_cache_metrics(
    cache_state: dict[str, str],
    cache_context: dict[str, object] | None,
    prompt_token_target: int,
) -> dict[str, int | bool] | None:
    if not isinstance(cache_context, dict):
        return None
    if cache_context.get("supports_prompt_cache") is not True:
        return None

    normalized_prompt_tokens = _coerce_usage_int(prompt_token_target)
    if normalized_prompt_tokens <= 0:
        return None

    current_text = str(cache_context.get("cacheable_text") or "")
    previous_text = str(cache_state.get("previous_cacheable_text") or "")
    cache_state["previous_cacheable_text"] = current_text

    shared_prefix_chars = _shared_prefix_char_count(previous_text, current_text)
    shared_prefix_tokens = _estimate_text_tokens(current_text[:shared_prefix_chars]) if shared_prefix_chars > 0 else 0
    prompt_cache_hit_tokens = min(normalized_prompt_tokens, max(0, shared_prefix_tokens))
    prompt_cache_miss_tokens = max(0, normalized_prompt_tokens - prompt_cache_hit_tokens)
    return {
        "prompt_cache_hit_tokens": prompt_cache_hit_tokens,
        "prompt_cache_miss_tokens": prompt_cache_miss_tokens,
        "cache_metrics_estimated": True,
    }


def _estimate_message_wrapper_tokens(role: str, *, include_tool_calls: bool = False) -> int:
    payload = {
        "role": str(role or ""),
        "content": "",
    }
    if include_tool_calls:
        payload["tool_calls"] = []
    return _estimate_serialized_tokens(payload)


def _estimate_request_tools_tokens(request_tools: list[dict] | None) -> int:
    if not request_tools:
        return 0
    return _estimate_serialized_tokens({"tools": request_tools, "tool_choice": "auto"})


def _align_breakdown_to_provider_total(breakdown: dict[str, int], total_tokens: int) -> dict[str, int]:
    adjusted = {
        key: max(0, int(value or 0))
        for key, value in (breakdown or {}).items()
        if key in INPUT_BREAKDOWN_KEYS and int(value or 0) > 0
    }
    target_total = max(0, int(total_tokens or 0))
    current_total = sum(adjusted.values())
    if current_total < target_total:
        adjusted["unknown_provider_overhead"] = adjusted.get("unknown_provider_overhead", 0) + (
            target_total - current_total
        )
        return adjusted
    if current_total <= target_total:
        return adjusted

    overflow = current_total - target_total
    for key in ("unknown_provider_overhead", "internal_state", "assistant_history", "core_instructions"):
        if overflow <= 0:
            break
        available = adjusted.get(key, 0)
        if available <= 0:
            continue
        reduction = min(available, overflow)
        adjusted[key] = available - reduction
        overflow -= reduction
    return {key: value for key, value in adjusted.items() if value > 0}


def _estimate_message_breakdown(message: dict) -> dict[str, int]:
    role = str(message.get("role") or "").strip()
    content = str(message.get("content") or "")
    content_tokens = _estimate_text_tokens(content)
    if role == "user":
        return {"user_messages": content_tokens}
    if role == "assistant":
        tool_call_tokens = _estimate_serialized_tokens(message.get("tool_calls") or [])
        breakdown: dict[str, int] = {}
        if content_tokens > 0:
            breakdown["assistant_history"] = content_tokens
        if tool_call_tokens > 0:
            breakdown["assistant_tool_calls"] = tool_call_tokens
        return breakdown
    if role == "tool":
        return {"tool_results": content_tokens}
    if role == "system":
        if content.startswith(TOOL_EXECUTION_RESULTS_MARKER):
            return {"tool_results": content_tokens}
        if content.startswith(REASONING_REPLAY_MARKER) or content.startswith("[AGENT WORKING MEMORY]"):
            return {"internal_state": content_tokens}
        return {"core_instructions": content_tokens}
    return {"core_instructions": content_tokens} if content_tokens > 0 else {}


def _estimate_input_breakdown(
    messages_to_send: list[dict],
    *,
    provider_prompt_tokens: int | None = None,
    request_tools: list[dict] | None = None,
) -> tuple[dict[str, int], int, int]:
    breakdown = _empty_input_breakdown()
    for message in messages_to_send:
        for key, value in _estimate_message_breakdown(message).items():
            if key in breakdown and value > 0:
                breakdown[key] += value

    tool_schema_tokens = _estimate_request_tools_tokens(request_tools)
    if tool_schema_tokens > 0:
        breakdown["tool_specs"] += tool_schema_tokens

    measured_total = sum(max(0, int(value or 0)) for value in breakdown.values())
    if provider_prompt_tokens is None:
        return breakdown, measured_total, tool_schema_tokens

    aligned_breakdown = _align_breakdown_to_provider_total(breakdown, provider_prompt_tokens)
    return aligned_breakdown, max(0, int(provider_prompt_tokens or 0)), tool_schema_tokens


def _estimate_messages_tokens(messages_to_send: list[dict]) -> int:
    return _estimate_input_breakdown(messages_to_send)[1]


def _get_model_call_input_tokens(call: dict) -> int:
    if not isinstance(call, dict):
        return 0

    prompt_tokens = call.get("prompt_tokens")
    if isinstance(prompt_tokens, (int, float)):
        return max(0, int(prompt_tokens))

    estimated_input_tokens = call.get("estimated_input_tokens")
    if isinstance(estimated_input_tokens, (int, float)):
        return max(0, int(estimated_input_tokens))

    return 0


def _summarize_model_call_usage(model_calls: list[dict], fallback_input_tokens: int = 0) -> dict[str, int]:
    max_input_tokens_per_call = 0
    for call in model_calls:
        max_input_tokens_per_call = max(max_input_tokens_per_call, _get_model_call_input_tokens(call))

    if max_input_tokens_per_call <= 0:
        max_input_tokens_per_call = max(0, int(fallback_input_tokens or 0))

    return {
        "max_input_tokens_per_call": max_input_tokens_per_call,
    }


def _extract_error_signal_text(error) -> str:
    fragments: list[str] = []

    def visit(value, depth: int = 0):
        if depth > 4 or value in (None, ""):
            return
        if isinstance(value, bytes):
            visit(value.decode("utf-8", errors="replace"), depth + 1)
            return
        if isinstance(value, dict):
            for key in ("message", "error", "detail", "code", "type"):
                nested = value.get(key)
                if nested not in (None, ""):
                    visit(nested, depth + 1)
            return
        if isinstance(value, Exception):
            visit(str(value), depth + 1)
            for attr in ("message", "body", "response"):
                nested = getattr(value, attr, None)
                if nested not in (None, ""):
                    visit(nested, depth + 1)
            return

        text = str(value or "").strip()
        if not text:
            return
        if text[:1] in "{" and text[-1:] in "}":
            try:
                parsed = json.loads(text)
            except Exception:
                pass
            else:
                visit(parsed, depth + 1)
                return
        if len(text) > 600:
            text = text[:600]
        fragments.append(text)

    visit(error)
    if not fragments:
        return ""
    return " | ".join(fragment for fragment in fragments if fragment).strip().lower()


def _summarize_input_breakdown_for_error(messages_to_send: list[dict]) -> str:
    if not isinstance(messages_to_send, list) or not messages_to_send:
        return ""

    breakdown, estimated_input_tokens, tool_schema_tokens = _estimate_input_breakdown(messages_to_send)
    summary_parts: list[str] = []
    if estimated_input_tokens > 0:
        prompt_part = f"Estimated prompt size: ~{estimated_input_tokens:,} tokens"
        if tool_schema_tokens > 0:
            prompt_part += f" (+ ~{tool_schema_tokens:,} tool-schema tokens)"
        summary_parts.append(prompt_part)

    largest_buckets = [
        (key, max(0, int(value or 0))) for key, value in breakdown.items() if max(0, int(value or 0)) > 0
    ]
    largest_buckets.sort(key=lambda item: item[1], reverse=True)
    if largest_buckets:
        bucket_summary = ", ".join(f"{str(key).replace('_', ' ')} ~{value:,}" for key, value in largest_buckets[:3])
        summary_parts.append(f"Largest input buckets: {bucket_summary}")
    return ". ".join(summary_parts).strip().rstrip(".")


def _build_context_overflow_recovery_error(messages_to_send: list[dict] | None = None) -> str:
    detail = _summarize_input_breakdown_for_error(messages_to_send or [])
    if not detail:
        return CONTEXT_OVERFLOW_RECOVERY_ERROR_TEXT
    return f"{CONTEXT_OVERFLOW_RECOVERY_ERROR_TEXT} {detail}."


def _classify_context_overflow_error(error_str) -> str:
    """Classify whether the error signal indicates a context overflow condition.

    Returns a severity label:
      - "high": Strong evidence of context-overflow (context_length_exceeded,
                maximum context length, etc.)
      - "medium": Weak evidence (generic "invalid params" + "context", or "token" +
                  "exceed"/"too long" with supporting context indicators)
      - "none": No meaningful context-overflow signal detected
    """
    normalized = _extract_error_signal_text(error_str)
    if not normalized:
        return "none"
    normalized_lower = normalized.lower()
    if "rate_limit" in normalized_lower or re.search(r"\b429\b", normalized_lower):
        return "none"

    known_phrases = (
        "context_length_exceeded",
        "maximum context length",
        "reduce the length",
        "request too large",
        "prompt is too long",
        "input is too long",
        "too many tokens",
        "context window",
        "context is full",
        "context overflow",
        "input tokens exceed",
        "prompt has too many tokens",
        "prompt tokens exceed",
        "exceeds maximum context",
        "context limit",
        "input too long",
    )
    if any(phrase in normalized_lower for phrase in known_phrases):
        return "high"
    # Check for generic "invalid params" error - only treat as context overflow if
    # combined with other context-related indicators
    if "invalid params" in normalized_lower and "context" in normalized_lower:
        return "medium"
    if "token" in normalized_lower and ("exceed" in normalized_lower or "too long" in normalized_lower):
        return "medium" if any(term in normalized_lower for term in ("context", "prompt", "input")) else "none"
    return "none"


def _classify_truncated_stream_disconnect_error(error_str) -> bool:
    normalized = _extract_error_signal_text(error_str)
    if not normalized:
        return False

    return any(
        phrase in normalized
        for phrase in (
            "incomplete chunked read",
            "peer closed connection without sending complete message body",
        )
    )


def _classify_retryable_model_error(error: Exception | str) -> str:
    """Classify whether the error signal indicates a retryable condition.

    Returns a severity label:
      - "high": Strong evidence of a retryable error (rate_limit, timeout,
                service unavailable, gateway errors, etc.)
      - "low": Weak evidence (429 status code detected via regex)
      - "none": Not retryable (e.g. context overflow takes priority)
    """
    error_text = str(error or "").strip().lower()
    if not error_text:
        return "none"
    if _classify_context_overflow_error(error_text) != "none":
        return "none"

    retryable_phrases = (
        "rate_limit",
        "too many requests",
        "request timeout",
        "request timed out",
        "timed out",
        "timeout",
        "deadline exceeded",
        "temporarily unavailable",
        "service unavailable",
        "bad gateway",
        "gateway timeout",
        "connection aborted",
        "connection reset",
        "api connection error",
        "server error",
        "upstream error",
    )
    if any(phrase in error_text for phrase in retryable_phrases):
        return "high"
    return "low" if re.search(r"\b429\b", error_text) else "none"


# ---------------------------------------------------------------------------
# Legacy aliases — kept to avoid breaking external test patches that reference
# the old function names. Remove once all callers are updated.
# ---------------------------------------------------------------------------
_is_context_overflow_error = _classify_context_overflow_error
_is_truncated_stream_disconnect_error = _classify_truncated_stream_disconnect_error
_is_retryable_model_error = _classify_retryable_model_error


def _normalize_tool_args_for_cache(value):
    if isinstance(value, dict):
        return {str(key): _normalize_tool_args_for_cache(value[key]) for key in sorted(value.keys())}
    if isinstance(value, list):
        return [_normalize_tool_args_for_cache(item) for item in value]
    if isinstance(value, str):
        return value.strip()
    return value


def build_tool_cache_key(tool_name: str, tool_args: dict) -> str:
    tool_name = _normalize_tool_name(tool_name)
    normalized_args = _normalize_tool_args_for_cache(tool_args if isinstance(tool_args, dict) else {})
    payload = json.dumps(normalized_args, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha1(f"{tool_name}|{payload}".encode("utf-8")).hexdigest()
    return f"tool-cache:{digest}"


def _clean_tool_text(text: str, limit: int | None = None) -> str:
    cleaned = str(text or "").strip()
    if limit and len(cleaned) > limit:
        return cleaned[:limit].rstrip() + "…"
    return cleaned


def _coerce_tool_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _format_tool_execution_error(error: Exception | str) -> str:
    raw_text = _clean_tool_text(str(error or ""), limit=280)
    if not raw_text:
        return "Tool execution failed."

    class_name = type(error).__name__ if isinstance(error, Exception) else ""
    lowered = raw_text.casefold()
    if class_name.endswith("Error") and class_name not in {"ValueError", "RuntimeError"}:
        if lowered.startswith(class_name.casefold()):
            raw_text = raw_text[len(class_name) :].lstrip(": ") or raw_text
    if raw_text.lower().startswith("traceback"):
        return "Tool execution failed before producing a usable result."
    return raw_text


def _sanitize_clarification_text(text: str, limit: int | None = None) -> str:
    cleaned = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not cleaned:
        return ""
    cleaned = re.sub(r"<\|(im_start|im_end|assistant|user|system|tool|endoftext)\|>", " ", cleaned, flags=re.IGNORECASE)
    while cleaned.startswith("<|") and cleaned.endswith("|>") and len(cleaned) > 4:
        cleaned = cleaned[2:-2].strip()
    cleaned = re.sub(r"^\s*<\|\s*[\"']?\s*", "", cleaned)
    cleaned = re.sub(r"\s*[\"']?\s*\|>\s*$", "", cleaned)
    cleaned = cleaned.replace("```", " ").replace("`", " ")
    cleaned = re.sub(r"^\s*[*\-•–]+\s*", "", cleaned)
    cleaned = re.sub(r"^\s*(?:Q|A|Question|Answer)\s*[:：]\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^\s*<\|\s*[\"']?\s*", "", cleaned)
    cleaned = re.sub(r"\s*[\"']?\s*\|>\s*$", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned.strip().strip("\"'").strip()
    if limit and len(cleaned) > limit:
        return cleaned[:limit].rstrip() + "…"
    return cleaned


def _sanitize_clarification_id(value: str, index: int) -> str:
    cleaned = _sanitize_clarification_text(value, limit=80).casefold()
    cleaned = re.sub(r"[^a-z0-9_]+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or f"question_{index}"


def _truncate_preview_text(text: str, limit: int | None = None) -> str:
    cleaned = str(text or "").strip()
    if limit and len(cleaned) > limit:
        return cleaned[:limit].rstrip() + "..."
    return cleaned


def _build_recovery_hint_for_tool(tool_name: str, tool_args: dict | None = None) -> str:
    normalized_tool_name = str(tool_name or "").strip()
    normalized_tool_args = tool_args if isinstance(tool_args, dict) else {}

    if normalized_tool_name == "fetch_url":
        url = _clean_tool_text(normalized_tool_args.get("url") or "", limit=160)
        if url:
            return f"Need omitted text? Use scroll_fetched_content with {url} and a start line, or grep_fetched_content with {url} and a keyword or regex."
        return (
            "Need omitted text? Use scroll_fetched_content with the same URL and a start line, "
            "or grep_fetched_content with a keyword or regex."
        )
    if normalized_tool_name == "fetch_url_summarized":
        url = _clean_tool_text(normalized_tool_args.get("url") or "", limit=160)
        if url:
            return (
                f"Need more than the summary? Call fetch_url for {url}, then use scroll_fetched_content or "
                "grep_fetched_content."
            )
        return "Need more than the summary? Call fetch_url, then use scroll_fetched_content or grep_fetched_content."
    if normalized_tool_name in {"search_web", "search_news_ddgs", "search_news_google"}:
        return "If exact wording is needed, fetch a specific returned URL or rerun the search with a narrower query."
    if normalized_tool_name == "search_knowledge_base":
        return "Repeat search_knowledge_base with the same query if you need the exact retrieved excerpts again."
    if normalized_tool_name == "read_file":
        return "Read the same file again if exact source lines are needed."
    if normalized_tool_name in {"expand_canvas_document", "scroll_canvas_document", "search_canvas_document"}:
        return "Reopen the same canvas document or search it again if you need the exact omitted lines."
    return ""


def _coerce_int_range(value, default: int, minimum: int, maximum: int) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        normalized = default
    return max(minimum, min(maximum, normalized))


def _tool_result_has_error(tool_name: str, result) -> bool:
    del tool_name
    if not isinstance(result, dict):
        return False

    if result.get("ok") is False:
        return True

    status = str(result.get("status") or "").strip().lower()
    if status in {"error", "failed"}:
        return True

    error_text = str(result.get("error") or "").strip()
    if not error_text:
        return False

    return status not in {"ok", "success", "needs_user_input"}


def _normalize_search_queries(raw_queries) -> list[str]:
    if isinstance(raw_queries, str):
        parsed_queries = _parse_json_like_value(raw_queries)
        if isinstance(parsed_queries, list):
            raw_queries = parsed_queries
        else:
            raw_queries = [raw_queries]
    if not isinstance(raw_queries, list):
        return []

    normalized_queries: list[str] = []
    seen_queries: set[str] = set()
    for raw_query in raw_queries:
        query = str(raw_query or "").strip()
        if not query or query in seen_queries:
            continue
        normalized_queries.append(query)
        seen_queries.add(query)
    return normalized_queries


def _resolve_search_query_batch_size(batch_size: int | None = None) -> int:
    if batch_size is not None:
        try:
            resolved_batch_size = int(batch_size)
        except (TypeError, ValueError):
            resolved_batch_size = 0
    else:
        resolved_batch_size = get_search_tool_query_limit(get_app_settings())

    if resolved_batch_size <= 0:
        resolved_batch_size = get_search_tool_query_limit(get_app_settings())
    return max(1, resolved_batch_size)


def _iter_search_query_batches(raw_queries, *, batch_size: int | None = None):
    normalized_queries = _normalize_search_queries(raw_queries)
    resolved_batch_size = _resolve_search_query_batch_size(batch_size)
    for index in range(0, len(normalized_queries), resolved_batch_size):
        yield normalized_queries[index : index + resolved_batch_size]


def _get_search_tool_queries(tool_args: dict):
    return _coerce_search_tool_queries(tool_args)


def _coerce_search_tool_queries(tool_args: dict, *, ensure_key: bool = False):
    if not isinstance(tool_args, dict):
        return []

    matched_key = None
    raw_queries = []
    for key in SEARCH_QUERY_ARGUMENT_ALIASES:
        if key not in tool_args:
            continue
        matched_key = key
        raw_queries = tool_args.get(key)
        break

    if matched_key is None:
        if ensure_key:
            tool_args["queries"] = []
        return []

    normalized_queries = _normalize_search_queries(raw_queries)
    if matched_key != "queries":
        tool_args.pop(matched_key, None)
    tool_args["queries"] = normalized_queries
    return normalized_queries


def _merge_batched_search_results(result_batches: list[list]) -> list:
    merged_results: list = []
    seen_references: set[str] = set()
    seen_errors: set[str] = set()

    for batch in result_batches:
        if not isinstance(batch, list):
            continue
        for row in batch:
            if not isinstance(row, dict):
                merged_results.append(row)
                continue

            reference = str(row.get("url") or row.get("link") or "").strip()
            if reference:
                if reference in seen_references:
                    continue
                seen_references.add(reference)
                merged_results.append(row)
                continue

            error_key = json.dumps(
                {
                    "error": str(row.get("error") or "").strip(),
                    "query": str(row.get("query") or "").strip(),
                    "title": str(row.get("title") or "").strip(),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            if error_key in seen_errors:
                continue
            seen_errors.add(error_key)
            merged_results.append(row)

    return merged_results


def _normalize_tool_name_list(values) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized = []
    for raw_value in values:
        name = str(raw_value or "").strip()
        if name and name not in normalized:
            normalized.append(name)
    return normalized


_TOOL_NAME_ALIASES = {
    "google_search": "search_web",
}


class AgentRunCancelledError(Exception):
    """Raised when the current agent run is cancelled by the user."""


def _normalize_tool_name(tool_name: str) -> str:
    name = str(tool_name or "").strip()
    return _TOOL_NAME_ALIASES.get(name, name)


def _is_agent_cancel_event_set(cancel_event) -> bool:
    is_set = getattr(cancel_event, "is_set", None)
    return bool(callable(is_set) and is_set())


def _get_agent_cancel_reason(agent_context: dict | None) -> str:
    if not isinstance(agent_context, dict):
        return USER_CANCELLED_ERROR_TEXT
    reason = str(agent_context.get("cancel_reason") or "").strip()
    return reason or USER_CANCELLED_ERROR_TEXT


def _raise_if_agent_cancelled(agent_context: dict | None) -> None:
    if not isinstance(agent_context, dict):
        return
    if _is_agent_cancel_event_set(agent_context.get("cancel_event")):
        raise AgentRunCancelledError(_get_agent_cancel_reason(agent_context))


def _sleep_with_agent_cancel(agent_context: dict | None, delay_seconds: float) -> None:
    remaining_seconds = max(0.0, float(delay_seconds or 0.0))
    while remaining_seconds > 0:
        _raise_if_agent_cancelled(agent_context)
        sleep_slice = min(0.25, remaining_seconds)
        time.sleep(sleep_slice)
        remaining_seconds = max(0.0, remaining_seconds - sleep_slice)


def _is_session_cacheable_tool(tool_name: str) -> bool:
    return is_tool_session_cacheable(_normalize_tool_name(tool_name))


def _resolve_sub_agent_tool_names(settings: dict, parent_tool_names: list[str] | None = None) -> list[str]:
    allowed = settings.get("sub_agent_allowed_tool_names") if isinstance(settings, dict) else None
    configured_tool_names = (
        allowed
        if isinstance(allowed, list) and allowed
        else parent_tool_names
        if isinstance(parent_tool_names, list) and parent_tool_names
        else SUB_AGENT_ALLOWED_TOOL_NAMES
    )
    normalized_tool_names: list[str] = []
    for tool_name in configured_tool_names:
        normalized_tool_name = _normalize_tool_name(tool_name)
        if normalized_tool_name == "sub_agent":
            continue
        if normalized_tool_name not in TOOL_SPEC_BY_NAME:
            continue
        if get_tool_runtime_metadata(normalized_tool_name).get("read_only") is not True:
            continue
        if normalized_tool_name not in normalized_tool_names:
            normalized_tool_names.append(normalized_tool_name)
    return normalized_tool_names


def _normalize_sub_agent_tool_calls(tool_calls) -> list[dict]:
    if not isinstance(tool_calls, list):
        return []

    normalized = []
    for tool_call in tool_calls[:8]:
        if not isinstance(tool_call, dict):
            continue
        function = tool_call.get("function") if isinstance(tool_call.get("function"), dict) else {}
        name = _normalize_tool_name(str(function.get("name") or tool_call.get("name") or "").strip())
        if not name:
            continue
        raw_arguments = function.get("arguments")
        parsed_arguments = _parse_json_like_value(raw_arguments)
        arguments = parsed_arguments if isinstance(parsed_arguments, dict) else {}
        entry = {"name": name}
        preview = _tool_input_preview(name, arguments)
        if preview:
            entry["preview"] = _clean_tool_text(preview, limit=240)
        if raw_arguments not in (None, ""):
            entry["arguments"] = _clean_tool_text(_serialize_tool_message_content(raw_arguments), limit=1_200)
        normalized.append(entry)
    return normalized


def _normalize_sub_agent_history_message(message: dict) -> dict | None:
    if not isinstance(message, dict):
        return None
    role = str(message.get("role") or "").strip()
    if role not in {"assistant", "tool"}:
        return None

    content = str(message.get("content") or "")
    cleaned_content = _clean_tool_text(content, limit=SUB_AGENT_MAX_MESSAGE_CONTENT_CHARS)
    normalized = {"role": role}
    if cleaned_content:
        normalized["content"] = cleaned_content
    if len(content) > len(cleaned_content):
        normalized["content_truncated"] = True

    if role == "assistant":
        tool_calls = _normalize_sub_agent_tool_calls(message.get("tool_calls"))
        if tool_calls:
            normalized["tool_calls"] = tool_calls
        if not normalized.get("content") and not tool_calls:
            return None
        return normalized

    tool_call_id = str(message.get("tool_call_id") or "").strip()
    if tool_call_id:
        normalized["tool_call_id"] = tool_call_id[:120]
    if not normalized.get("content"):
        return None
    return normalized


def _build_sub_agent_retry_messages(child_history: list[dict]) -> list[dict]:
    if not isinstance(child_history, list):
        return []

    retry_messages: list[dict] = []
    tool_call_names_by_id: dict[str, str] = {}
    tool_call_names_in_order: list[str] = []
    tool_call_name_index = 0
    index = 0
    while index < len(child_history):
        message = child_history[index]
        if not isinstance(message, dict):
            index += 1
            continue

        role = str(message.get("role") or "").strip()
        content = _clean_tool_text(message.get("content") or "", limit=SUB_AGENT_MAX_MESSAGE_CONTENT_CHARS)

        if role == "assistant":
            retry_message: dict[str, Any] = {"role": "assistant"}
            if content:
                retry_message["content"] = content

            raw_tool_calls = message.get("tool_calls") if isinstance(message.get("tool_calls"), list) else []
            normalized_tool_calls = []
            tool_call_ids: list[str] = []
            tool_call_names_by_id = {}
            tool_call_names_in_order = []
            tool_call_name_index = 0
            lookahead_index = index + 1
            while lookahead_index < len(child_history):
                next_message = child_history[lookahead_index]
                if not isinstance(next_message, dict) or str(next_message.get("role") or "").strip() != "tool":
                    break
                tool_call_ids.append(str(next_message.get("tool_call_id") or "").strip()[:120])
                lookahead_index += 1

            for call_index, raw_tool_call in enumerate(raw_tool_calls[:8], start=1):
                if not isinstance(raw_tool_call, dict):
                    continue
                function_name = _clean_tool_text(raw_tool_call.get("name") or "", limit=80)
                if not function_name:
                    continue
                arguments_text = _clean_tool_text(raw_tool_call.get("arguments") or "", limit=1_200)
                if not arguments_text:
                    arguments_text = "{}"
                tool_call_id = ""
                if call_index - 1 < len(tool_call_ids):
                    tool_call_id = tool_call_ids[call_index - 1]
                if not tool_call_id:
                    tool_call_id = str(raw_tool_call.get("id") or f"tool-call-{call_index}").strip()[:120]
                tool_call_names_in_order.append(function_name)
                tool_call_names_by_id[tool_call_id] = function_name
                normalized_tool_calls.append(
                    {
                        "id": tool_call_id,
                        "type": "function",
                        "function": {
                            "name": function_name,
                            "arguments": arguments_text,
                        },
                    }
                )

            if normalized_tool_calls:
                retry_message["tool_calls"] = normalized_tool_calls
            if retry_message.get("content") or normalized_tool_calls:
                retry_messages.append(retry_message)
            index += 1
            continue

        if role == "tool":
            tool_call_id = str(message.get("tool_call_id") or "").strip()[:120]
            if not tool_call_id:
                # Drop tool messages without an ID - they would fail API validation.
                index += 1
                continue
            tool_name = tool_call_names_by_id.get(tool_call_id, "")
            if not tool_name and tool_call_name_index < len(tool_call_names_in_order):
                tool_name = tool_call_names_in_order[tool_call_name_index]
                tool_call_name_index += 1
            if not tool_name:
                tool_name = "tool"
            tool_message: dict[str, Any] = {
                "role": "tool",
                "content": content,
                "name": tool_name,
                "tool_call_id": tool_call_id,
            }
            if tool_message.get("content"):
                retry_messages.append(tool_message)
            index += 1
            continue

        if content:
            retry_messages.append({"role": role, "content": content})
        index += 1

    return retry_messages


def _append_sub_agent_history_entries(accumulator: list[dict], entries: list[dict]) -> list[dict]:
    if not isinstance(accumulator, list):
        accumulator = []
    if not isinstance(entries, list):
        return accumulator[:SUB_AGENT_MAX_TRANSCRIPT_MESSAGES]

    for entry in entries:
        normalized_entry = _normalize_sub_agent_history_message(entry)
        if normalized_entry is None:
            continue
        accumulator.append(normalized_entry)
        if len(accumulator) > SUB_AGENT_MAX_TRANSCRIPT_MESSAGES:
            accumulator[:] = accumulator[-SUB_AGENT_MAX_TRANSCRIPT_MESSAGES:]
    return accumulator


def _append_sub_agent_tool_results(accumulator: list[dict], entries: list[dict]) -> list[dict]:
    if not isinstance(accumulator, list):
        accumulator = []
    if not isinstance(entries, list):
        return accumulator[:SUB_AGENT_MAX_ARTIFACTS]

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        accumulator.append(entry)
        if len(accumulator) > SUB_AGENT_MAX_ARTIFACTS:
            accumulator[:] = accumulator[-SUB_AGENT_MAX_ARTIFACTS:]
    return accumulator


def _append_sub_agent_tool_trace_entries(accumulator: list[dict], entries: list[dict]) -> list[dict]:
    if not isinstance(accumulator, list):
        accumulator = []
    if not isinstance(entries, list):
        return accumulator[:32]

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        accumulator.append(entry)
        if len(accumulator) > 32:
            accumulator[:] = accumulator[-32:]
    return accumulator


def _combine_sub_agent_reasoning(existing: str, incoming: str) -> str:
    cleaned_existing = _clean_tool_text(existing or "", limit=SUB_AGENT_MAX_REASONING_CHARS)
    cleaned_incoming = _clean_tool_text(incoming or "", limit=SUB_AGENT_MAX_REASONING_CHARS)
    if not cleaned_incoming:
        return cleaned_existing
    if not cleaned_existing:
        return cleaned_incoming
    return _clean_tool_text(f"{cleaned_existing}\n\n{cleaned_incoming}", limit=SUB_AGENT_MAX_REASONING_CHARS)


def _is_sub_agent_placeholder_answer(text: str) -> bool:
    cleaned_text = _clean_tool_text(text or "", limit=SUB_AGENT_MAX_SUMMARY_CHARS)
    return cleaned_text in {FINAL_ANSWER_ERROR_TEXT, FINAL_ANSWER_MISSING_TEXT}


def _is_sub_agent_internal_final_answer_error(tool_name: str, error_text: str) -> bool:
    if _normalize_tool_name(str(tool_name or "").strip()) != "agent":
        return False
    cleaned_error = _clean_tool_text(error_text or "", limit=SUB_AGENT_MAX_ERROR_CHARS).lower()
    return bool(cleaned_error) and "final answer" in cleaned_error


def _build_sub_agent_missing_final_answer_summary(
    tool_trace: list[dict],
    artifacts: list[dict],
    transcript_messages: list[dict],
) -> str:
    findings: list[str] = []
    seen: set[str] = set()

    def add_finding(value: str, label: str = "") -> None:
        cleaned_value = _clean_tool_text(value or "", limit=300)
        cleaned_label = _clean_tool_text(label or "", limit=120)
        if not cleaned_value or _is_sub_agent_placeholder_answer(cleaned_value):
            return
        if cleaned_label and cleaned_label.lower() not in cleaned_value.lower():
            candidate = f"{cleaned_label}: {cleaned_value}"
        else:
            candidate = cleaned_value
        if candidate in seen:
            return
        seen.add(candidate)
        findings.append(candidate)

    for artifact in artifacts[:SUB_AGENT_MAX_ARTIFACTS]:
        if not isinstance(artifact, dict):
            continue
        add_finding(artifact.get("value") or "", artifact.get("label") or "")
        if len(findings) >= 3:
            break

    if len(findings) < 3:
        for entry in reversed(_normalize_sub_agent_tool_trace(tool_trace)):
            if str(entry.get("state") or "done") == "running":
                continue
            add_finding(entry.get("summary") or "")
            if len(findings) >= 3:
                break

    if not findings:
        for message in reversed(transcript_messages):
            if not isinstance(message, dict) or str(message.get("role") or "").strip() != "assistant":
                continue
            add_finding(message.get("content") or "")
            if findings:
                break

    prefix = "Sub-agent gathered tool output, but the delegated model did not write a usable final conclusion."
    if findings:
        return f"{prefix} Collected findings: {'; '.join(findings[:3])}"
    return prefix


def _upsert_sub_agent_tool_trace(entries: list[dict], call_map: dict[str, int], event: dict) -> None:
    tool_name = str(event.get("tool") or "").strip()
    if not tool_name:
        return

    call_id = str(event.get("call_id") or f"step-{event.get('step') or 1}-{tool_name}").strip()
    entry = {
        "tool_name": tool_name,
        "step": _coerce_int_range(event.get("step"), 1, 1, 999),
    }

    preview = _clean_tool_text(event.get("preview") or "", limit=300)
    if preview:
        entry["preview"] = preview

    event_type = str(event.get("type") or "").strip()
    if event_type == "step_update":
        entry["state"] = "running"
    elif event_type == "tool_error":
        entry["state"] = "error"
        summary = _clean_tool_text(event.get("error") or "", limit=300)
        if summary:
            entry["summary"] = summary
    elif event_type == "tool_result":
        summary = _clean_tool_text(event.get("summary") or "", limit=300)
        if summary:
            entry["summary"] = summary
        entry["state"] = "error" if str(summary).lower().startswith(("error:", "failed:")) else "done"
        if event.get("cached") is True or "(cached)" in str(summary).lower():
            entry["cached"] = True
    else:
        return

    existing_index = call_map.get(call_id)
    if existing_index is None:
        call_map[call_id] = len(entries)
        entries.append(entry)
        return

    entries[existing_index].update(entry)


def _normalize_sub_agent_tool_trace(entries: list[dict]) -> list[dict]:
    normalized = []
    for entry in entries[:32]:
        if not isinstance(entry, dict):
            continue
        tool_name = _clean_tool_text(entry.get("tool_name") or "", limit=80)
        if not tool_name:
            continue
        cleaned = {
            "tool_name": tool_name,
            "step": _coerce_int_range(entry.get("step"), 1, 1, 999),
            "state": str(entry.get("state") or "done").strip()
            if str(entry.get("state") or "").strip() in {"running", "done", "error"}
            else "done",
        }
        preview = _clean_tool_text(entry.get("preview") or "", limit=300)
        if preview:
            cleaned["preview"] = preview
        summary = _clean_tool_text(entry.get("summary") or "", limit=300)
        if summary:
            cleaned["summary"] = summary
        if entry.get("cached") is True:
            cleaned["cached"] = True
        normalized.append(cleaned)
    return normalized


def _build_sub_agent_artifacts(transcript_messages: list[dict], tool_results: list[dict]) -> list[dict]:
    artifacts = []
    seen = set()

    def add_artifact(kind: str, label: str, value: str):
        cleaned_kind = _clean_tool_text(kind, limit=40)
        cleaned_label = _clean_tool_text(label, limit=160)
        cleaned_value = _clean_tool_text(value, limit=300)
        if not cleaned_kind or not cleaned_label or not cleaned_value:
            return
        key = (cleaned_kind, cleaned_label, cleaned_value)
        if key in seen:
            return
        seen.add(key)
        artifacts.append({"kind": cleaned_kind, "label": cleaned_label, "value": cleaned_value})

    for message in transcript_messages:
        if not isinstance(message, dict):
            continue
        tool_calls = message.get("tool_calls") if isinstance(message.get("tool_calls"), list) else []
        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                continue
            tool_name = _normalize_tool_name(str(tool_call.get("name") or "").strip())
            preview = str(tool_call.get("preview") or "").strip()
            if tool_name and preview:
                add_artifact("tool_input", tool_name.replace("_", " ").title(), preview)

    for entry in tool_results[:SUB_AGENT_MAX_ARTIFACTS]:
        if not isinstance(entry, dict):
            continue
        tool_name = str(entry.get("tool_name") or "").strip()
        input_preview = str(entry.get("input_preview") or tool_name).strip()
        summary = str(entry.get("summary") or entry.get("content") or "").strip()
        if tool_name and input_preview and summary:
            add_artifact(tool_name, input_preview, summary)

    return artifacts[:SUB_AGENT_MAX_ARTIFACTS]


def _build_sub_agent_messages(
    task: str,
    allowed_tools: list[str],
    max_parallel_tools: int | None = None,
    search_tool_query_limit: int | None = None,
    now: datetime | None = None,
) -> list[dict]:
    normalized_search_tool_query_limit = get_search_tool_query_limit(
        {"search_tool_query_limit": search_tool_query_limit}
    )
    parts = [
        "You are an advanced delegated helper agent for a larger AI assistant system.",
        "Complete the delegated task using only the tools that are exposed to you. Read-only still includes web search and URL fetch tools when they are available.",
        "You must not ask the user clarifying questions, mutate files, mutate canvas documents, or delegate to another sub-agent.",
        "Treat the delegated task text as the complete instruction from the parent assistant.",
        "Do not infer, restate, or rely on hidden user background, personal details, prior conversation summaries, or canvas context unless they are explicitly written in that task text.",
        "If the task text is not in English, first rewrite it into clear English working notes for yourself, then continue in English.",
        "Use English for tool planning, reasoning, status updates, and the final answer unless told otherwise.",
        f"When using read-only search tools like search_web or search_news, batch queries between 1 and {normalized_search_tool_query_limit} items per list and split broader searches into multiple calls.",
        "You may batch independent read-only tool calls into the same turn when they do not depend on each other.",
        "Synthesize your findings and return a concise, definitive final answer that directly helps the parent assistant continue.",
    ]
    parts.append(build_current_time_context(now))
    if allowed_tools:
        parts.append(f"Available read-only tools: {', '.join(allowed_tools)}.")
    if max_parallel_tools is not None:
        normalized_parallel_tools = max(
            MAX_PARALLEL_TOOLS_MIN, min(MAX_PARALLEL_TOOLS_MAX, int(max_parallel_tools or 0))
        )
        parts.append(
            f"At most {normalized_parallel_tools} tool call(s) can execute in parallel in one turn. "
            f"If you need more independent reads than that, prioritize the most relevant first."
        )

    user_parts = [f"Delegated task from the parent assistant:\n{_clean_tool_text(task, limit=2_000)}"]
    user_parts.append(
        "Return the best final answer you can. Include the most useful findings and concrete references from the tools you used."
    )

    return [
        {"role": "system", "content": "\n\n".join(parts)},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]


def _resolve_sub_agent_max_steps(settings: dict) -> int:
    return get_sub_agent_max_steps(settings)


def _build_canvas_expected_context(
    canvas_state: dict,
    *,
    document_id: str | None = None,
    document_path: str | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
    after_line: int | None = None,
    mode: str,
) -> tuple[int | None, list[str] | None]:
    if not isinstance(canvas_state, dict):
        return None, None

    try:
        _, document = find_canvas_document(canvas_state, document_id=document_id, document_path=document_path)
    except Exception:
        return None, None

    existing_lines = list_canvas_lines(document.get("content") or "")
    if not existing_lines:
        return None, None

    if mode in {"replace", "delete"}:
        if not isinstance(start_line, int) or not isinstance(end_line, int):
            return None, None
        if start_line < 1 or end_line < start_line:
            return None, None
        expected_lines = existing_lines[start_line - 1 : end_line]
        return start_line, expected_lines or None

    if mode == "insert":
        if not isinstance(after_line, int) or after_line < 0:
            return None, None
        if after_line == 0:
            expected_start_line = 1
            expected_lines = existing_lines[: min(3, len(existing_lines))]
            return expected_start_line, expected_lines or None

        expected_start_line = max(1, after_line - 1)
        expected_end_line = min(len(existing_lines), after_line + 1)
        expected_lines = existing_lines[expected_start_line - 1 : expected_end_line]
        return expected_start_line, expected_lines or None

    return None, None


def _build_sub_agent_resume_message(previous_model: str, reason: str) -> dict:
    parts = []
    cleaned_previous_model = _clean_tool_text(previous_model, limit=120)
    cleaned_reason = _clean_tool_text(reason, limit=120)
    if cleaned_previous_model and cleaned_reason:
        parts.append(f"The previous attempt on {cleaned_previous_model} stopped because of {cleaned_reason}.")
    elif cleaned_previous_model:
        parts.append(f"The previous attempt on {cleaned_previous_model} stopped.")
    elif cleaned_reason:
        parts.append(f"The previous attempt stopped because of {cleaned_reason}.")
    parts.append("Continue from the latest transcript and do not repeat completed work.")
    return {"role": "system", "content": " ".join(parts)}


def _append_sub_agent_trace(runtime_state: dict, entry: dict) -> None:
    if not isinstance(entry, dict):
        return
    traces = runtime_state.setdefault("sub_agent_traces", [])
    if isinstance(traces, list):
        traces.append(entry)


def _has_missing_final_answer_instruction(messages: list[dict]) -> bool:
    return any(MISSING_FINAL_ANSWER_MARKER in str(message.get("content") or "") for message in messages)


def _get_latest_user_message_index(messages: list[dict]) -> int:
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if str(message.get("role") or "").strip() == "user":
            return index
    return -1


def _conversation_has_clarification_tool_call(messages: list[dict]) -> bool:
    """Return True if ask_clarifying_question was already called in this turn (after the latest user message).

    Only checks messages that follow the latest user message so that historical
    clarification rounds from previous turns do not block the retry logic for new turns.
    """
    latest_user_index = _get_latest_user_message_index(messages)
    if latest_user_index < 0:
        return False

    for message in messages[latest_user_index + 1 :]:
        if not isinstance(message, dict):
            continue
        if str(message.get("role") or "").strip() != "assistant":
            continue
        tool_calls = parse_message_tool_calls(message.get("tool_calls"))
        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                continue
            function_payload = tool_call.get("function") if isinstance(tool_call.get("function"), dict) else {}
            tool_name = str(function_payload.get("name") or tool_call.get("name") or "").strip()
            if tool_name == "ask_clarifying_question":
                return True
    return False


def _is_tool_execution_result_message(message: dict) -> bool:
    content = str(message.get("content") or "").strip()
    return content.startswith(TOOL_EXECUTION_RESULTS_MARKER)


def _iter_agent_exchange_blocks(messages: list[dict]) -> list[dict]:
    blocks: list[dict] = []
    index = 0
    exchange_index = 0
    while index < len(messages):
        message = messages[index]
        role = str(message.get("role") or "").strip()
        tool_calls = message.get("tool_calls") if isinstance(message, dict) else None
        if role == "assistant" and isinstance(tool_calls, list) and tool_calls:
            exchange_index += 1
            block_messages = [message]
            index += 1
            while index < len(messages):
                candidate = messages[index]
                candidate_role = str(candidate.get("role") or "").strip()
                if candidate_role == "tool" or _is_tool_execution_result_message(candidate):
                    block_messages.append(candidate)
                    index += 1
                    continue
                break
            blocks.append({"type": "exchange", "step_index": exchange_index, "messages": block_messages})
            continue

        block_type = "system_prefix" if role == "system" and not blocks else "passthrough"
        blocks.append({"type": block_type, "messages": [message]})
        index += 1
    return blocks


def _flatten_agent_exchange_blocks(blocks: list[dict]) -> list[dict]:
    flattened: list[dict] = []
    for block in blocks:
        flattened.extend(block.get("messages") or [])
    return flattened


def _merge_adjacent_user_messages(messages: list[dict]) -> list[dict] | None:
    merged_messages: list[dict] = []
    buffered_user_contents: list[str] = []
    merged_any = False

    def flush_user_buffer():
        nonlocal merged_any
        if not buffered_user_contents:
            return
        merged_content = "\n\n".join(content for content in buffered_user_contents if content)
        if len(buffered_user_contents) > 1:
            merged_any = True
        merged_messages.append({"role": "user", "content": merged_content})
        buffered_user_contents.clear()

    for message in messages:
        if str(message.get("role") or "").strip() == "user":
            buffered_user_contents.append(str(message.get("content") or "").strip())
            continue
        flush_user_buffer()
        merged_messages.append(message)

    flush_user_buffer()
    return merged_messages if merged_any else None


def _extract_compaction_assistant_intent(message: dict) -> str:
    return _clean_tool_text(message.get("content") or "", limit=140)


def _extract_compaction_tool_call_preview(tool_call: dict) -> str:
    function = tool_call.get("function") or {}
    tool_name = str(function.get("name") or "").strip() or "tool"
    raw_arguments = function.get("arguments")
    parsed_arguments = _parse_json_like_value(raw_arguments)
    arguments = parsed_arguments if isinstance(parsed_arguments, dict) else {}

    if tool_name in {"search_web", "search_news_ddgs", "search_news_google"}:
        queries = _get_search_tool_queries(arguments)
        if isinstance(queries, list):
            preview = ", ".join(str(item).strip() for item in queries if str(item).strip())
            if preview:
                return f"{tool_name}: {_clean_tool_text(preview, limit=120)}"
    if tool_name == "fetch_url":
        url = str(arguments.get("url") or "").strip()
        if url:
            return f"{tool_name}: {_clean_tool_text(url, limit=140)}"
    if tool_name == "fetch_url_summarized":
        url = str(arguments.get("url") or "").strip()
        focus = str(arguments.get("focus") or "").strip()
        if url and focus:
            return f"{tool_name}: {_clean_tool_text(url, limit=90)} | {_clean_tool_text(focus, limit=45)}"
        if url:
            return f"{tool_name}: {_clean_tool_text(url, limit=140)}"
    if tool_name == "search_knowledge_base":
        query = str(arguments.get("query") or "").strip()
        if query:
            return f"{tool_name}: {_clean_tool_text(query, limit=120)}"

    scalar_parts: list[str] = []
    for key, value in list(arguments.items())[:3]:
        if isinstance(value, (str, int, float)):
            text = _clean_tool_text(value, limit=60)
            if text:
                scalar_parts.append(f"{key}={text}")
    if scalar_parts:
        return f"{tool_name}: " + ", ".join(scalar_parts)
    return tool_name


def _extract_compaction_tool_result_preview(message: dict) -> str:
    content = str(message.get("content") or "").strip()
    if not content:
        return ""

    parsed = _parse_json_like_value(content)
    if isinstance(parsed, dict):
        error = _clean_tool_text(parsed.get("error") or "", limit=120)
        if error:
            return f"error: {error}"
        summary = _clean_tool_text(parsed.get("summary") or parsed.get("title") or "", limit=120)
        if summary:
            return summary
        value = _clean_tool_text(parsed.get("content") or parsed.get("value") or "", limit=120)
        if value:
            return value

    normalized = content.replace(TOOL_EXECUTION_RESULTS_MARKER, "").strip()
    for line in normalized.splitlines():
        cleaned = _clean_tool_text(line, limit=120)
        if not cleaned:
            continue
        if cleaned.lower().startswith(("url:", "title:")):
            continue
        return cleaned
    return _clean_tool_text(normalized, limit=120)


def _count_exchange_blocks(messages: list[dict]) -> int:
    return sum(1 for block in _iter_agent_exchange_blocks(messages) if block.get("type") == "exchange")


def _compact_exchange_to_message(block: dict) -> dict:
    """Compact an exchange block into a single summary message.

    Preserves original role hierarchy in metadata per Coding Principles.md:
    - Chronological Integrity: step_index maintained
    - Metadata Preservation: original roles and tool calls stored in metadata
    """
    tool_previews: list[str] = []
    result_parts: list[str] = []
    recovery_hints: list[str] = []
    assistant_intent = ""
    reasoning_content = ""
    original_roles: list[str] = []
    original_tool_call_count = 0
    original_tool_result_count = 0

    for message in block.get("messages") or []:
        role = str(message.get("role") or "").strip()
        if role not in original_roles:
            original_roles.append(role)
        if role == "assistant":
            assistant_intent = assistant_intent or _extract_compaction_assistant_intent(message)
            # Extract reasoning_content from metadata for preservation
            if not reasoning_content:
                metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
                reasoning_content = str(metadata.get("reasoning_content") or "").strip()
            tool_calls = message.get("tool_calls") or []
            original_tool_call_count += len(tool_calls)
            for tool_call in tool_calls:
                preview = _extract_compaction_tool_call_preview(tool_call)
                if preview and preview not in tool_previews:
                    tool_previews.append(preview)
                function = tool_call.get("function") or {}
                raw_arguments = function.get("arguments")
                parsed_arguments = _parse_json_like_value(raw_arguments)
                arguments = parsed_arguments if isinstance(parsed_arguments, dict) else {}
                recovery_hint = _build_recovery_hint_for_tool(function.get("name") or "", arguments)
                if recovery_hint and recovery_hint not in recovery_hints:
                    recovery_hints.append(recovery_hint)
        elif role == "tool" or _is_tool_execution_result_message(message):
            original_tool_result_count += 1
            content = _extract_compaction_tool_result_preview(message)
            if content:
                result_parts.append(content)

    # Build content with clear section headers per Coding Principles.md
    parts = [f"[Context: compacted tool step {block.get('step_index') or '?'}]"]
    if assistant_intent:
        parts.append(f"Assistant intent: {assistant_intent}")
    if reasoning_content:
        if len(reasoning_content) > 500:
            parts.append(f"Reasoning: {reasoning_content[:497]}...")
        else:
            parts.append(f"Reasoning: {reasoning_content}")
    if tool_previews:
        parts.append("Actions:\n- " + "\n- ".join(tool_previews[:4]))
    if result_parts:
        parts.append("Outcomes:\n- " + "\n- ".join(result_parts[:3]))
    if recovery_hints:
        parts.append("Recovery:\n- " + "\n- ".join(recovery_hints[:2]))

    # Preserve metadata per Coding Principles.md — Metadata Preservation
    # This ensures original role hierarchy is not lost during compaction
    return {
        "role": "user",
        "content": "\n".join(parts),
        "metadata": {
            "compacted": True,
            "step_index": block.get("step_index"),
            "original_roles": original_roles,
            "original_tool_call_count": original_tool_call_count,
            "original_tool_result_count": original_tool_result_count,
        },
    }


def _try_compact_messages(messages: list[dict], budget: int, keep_recent: int = 2) -> list[dict] | None:
    if not isinstance(messages, list):
        return None

    blocks = _iter_agent_exchange_blocks(messages)
    exchange_positions = [index for index, block in enumerate(blocks) if block.get("type") == "exchange"]
    if not exchange_positions:
        return _merge_adjacent_user_messages(messages)

    keep_recent = max(0, int(keep_recent))
    compactable_positions = exchange_positions[:-keep_recent] if keep_recent else exchange_positions[:]
    if not compactable_positions:
        return None

    working_blocks = [{**block, "messages": list(block.get("messages") or [])} for block in blocks]
    best_messages: list[dict] | None = None
    for position in compactable_positions:
        block = working_blocks[position]
        block["messages"] = [_compact_exchange_to_message(block)]
        best_messages = _flatten_agent_exchange_blocks(working_blocks)
        merged_user_messages = _merge_adjacent_user_messages(best_messages)
        if merged_user_messages is not None:
            best_messages = merged_user_messages
        if _estimate_messages_tokens(best_messages) <= max(1, int(budget)):
            return best_messages
    return best_messages


def _serialize_for_log(value, depth: int = 0):
    if depth >= 2:
        if isinstance(value, str):
            return _clean_tool_text(value, limit=300)
        if isinstance(value, (int, float, bool)) or value is None:
            return value
        return _clean_tool_text(str(value), limit=300)

    if isinstance(value, str):
        return _clean_tool_text(value, limit=800)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        items = list(value.items())[:20]
        return {str(key): _serialize_for_log(item, depth + 1) for key, item in items}
    if isinstance(value, (list, tuple)):
        return [_serialize_for_log(item, depth + 1) for item in list(value)[:20]]
    return _clean_tool_text(str(value), limit=800)


def _serialize_for_raw_log(value, depth: int = 0):
    if depth >= 8:
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _serialize_for_raw_log(item, depth + 1) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize_for_raw_log(item, depth + 1) for item in value]

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return _serialize_for_raw_log(model_dump(), depth + 1)
        except Exception:
            return str(value)

    dict_method = getattr(value, "dict", None)
    if callable(dict_method):
        try:
            return _serialize_for_raw_log(dict_method(), depth + 1)
        except Exception:
            return str(value)

    return str(value)


def _summarize_messages_for_log(messages_to_send: list[dict]) -> list[dict]:
    summary = []
    for message in messages_to_send[:20]:
        role = str(message.get("role") or "").strip()
        content = str(message.get("content") or "")
        context_type = ""
        if role == "system":
            try:
                payload = json.loads(content)
            except Exception:
                payload = None
            if isinstance(payload, dict):
                context_type = str(payload.get("context_type") or "").strip()
        summary.append(
            {
                "role": role,
                "context_type": context_type or None,
                "content_excerpt": _clean_tool_text(content, limit=240),
            }
        )
    return summary


def _trace_agent_event(event: str, *, raw_fields: dict | None = None, **fields):
    if not AGENT_TRACE_LOG_ENABLED:
        return

    payload = {"event": event}
    for key, value in fields.items():
        payload[key] = _serialize_for_log(value)
    if AGENT_TRACE_LOG_INCLUDE_RAW and isinstance(raw_fields, dict) and raw_fields:
        payload["raw"] = {str(key): _serialize_for_raw_log(value) for key, value in raw_fields.items()}
    try:
        logger = _get_agent_trace_logger()
        if logger is None:
            return
        logger.info(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    except Exception:
        return


def trace_agent_stream_payload(
    event_name: str,
    *,
    payload,
    conversation_id: int | None = None,
    stream_request_id: str | None = None,
    step: int | None = None,
) -> None:
    event_type = ""
    if isinstance(payload, dict):
        event_type = str(payload.get("type") or "").strip()
    _trace_agent_event(
        event_name,
        conversation_id=conversation_id,
        stream_request_id=stream_request_id,
        step=step,
        event_type=event_type or None,
        raw_fields={"payload": payload},
    )


def _normalize_fetch_token_threshold(value) -> int:
    try:
        threshold = int(value)
    except (TypeError, ValueError):
        threshold = FETCH_SUMMARY_TOKEN_THRESHOLD
    return max(1, threshold)


def _normalize_fetch_clip_aggressiveness(value) -> int:
    try:
        aggressiveness = int(value)
    except (TypeError, ValueError):
        aggressiveness = 50
    return max(0, min(100, aggressiveness))


def _shrink_excerpt_lengths(lengths: list[int], minimums: list[int], overflow: int) -> list[int]:
    adjusted = list(lengths)
    remaining_overflow = max(0, int(overflow or 0))
    for index in (1, 2, 0):
        if remaining_overflow <= 0:
            break
        reducible = max(0, adjusted[index] - minimums[index])
        if reducible <= 0:
            continue
        delta = min(reducible, remaining_overflow)
        adjusted[index] -= delta
        remaining_overflow -= delta
    return adjusted


def _build_head_tail_excerpt(text: str, target_chars: int) -> tuple[str, dict]:
    cleaned = str(text or "")
    normalized_target = max(0, int(target_chars or 0))
    if not cleaned or normalized_target <= 0 or len(cleaned) <= normalized_target:
        return cleaned, {"strategy": "full_text", "excerpt_count": 1}

    marker = "\n\n[... middle content omitted ...]\n\n"
    available = normalized_target - len(marker)
    if available < 1_200:
        return _clean_tool_text(cleaned, limit=normalized_target), {"strategy": "truncated_excerpt", "excerpt_count": 1}

    head_chars = max(700, int(available * 0.72))
    tail_chars = max(320, available - head_chars)
    if head_chars + tail_chars >= len(cleaned):
        return cleaned, {"strategy": "full_text", "excerpt_count": 1}

    omitted_chars = max(0, len(cleaned) - head_chars - tail_chars)
    dynamic_marker = f"\n\n[... {omitted_chars:,} middle characters omitted ...]\n\n"
    available = normalized_target - len(dynamic_marker)
    if available < 1_000:
        return _clean_tool_text(cleaned, limit=normalized_target), {"strategy": "truncated_excerpt", "excerpt_count": 1}

    head_chars = max(600, int(available * 0.72))
    tail_chars = max(280, available - head_chars)
    if head_chars + tail_chars >= len(cleaned):
        return cleaned, {"strategy": "full_text", "excerpt_count": 1}

    head = cleaned[:head_chars].rstrip()
    tail = cleaned[-tail_chars:].lstrip()
    if not head or not tail:
        return _clean_tool_text(cleaned, limit=normalized_target), {"strategy": "truncated_excerpt", "excerpt_count": 1}
    return f"{head}{dynamic_marker}{tail}", {"strategy": "head_tail_excerpt", "excerpt_count": 2}


def _extract_fetch_entropy_terms(text: str) -> list[str]:
    return [term.lower() for term in re.findall(r"[A-Za-z0-9_./:-]{3,}", str(text or ""))]


def _extract_fetch_anchor_terms(text: str) -> list[str]:
    unique_terms: list[str] = []
    seen_terms: set[str] = set()
    for term in _extract_fetch_entropy_terms(text):
        if len(term) < 5 or term.isdigit() or term in seen_terms:
            continue
        seen_terms.add(term)
        unique_terms.append(term)
        if len(unique_terms) >= 8:
            break
    return unique_terms


def _score_fetch_excerpt_window(window: str, *, anchor_terms: list[str] | None = None) -> float:
    normalized_window = str(window or "").strip()
    if not normalized_window:
        return 0.0

    terms = _extract_fetch_entropy_terms(normalized_window)
    lexical_score = 0.0
    if terms:
        lexical_score = min(1.0, (len(set(terms)) / len(terms)) * 1.4)

    structural_score = 0.0
    if "```" in normalized_window or re.search(r"^\s{4,}\S", normalized_window, re.MULTILINE):
        structural_score += 0.24
    if re.search(r"https?://|www\.", normalized_window):
        structural_score += 0.18
    if re.search(r"\b\d[\d.,_:/-]*\b", normalized_window):
        structural_score += 0.16
    if re.search(r"^#{1,6}\s+", normalized_window, re.MULTILINE):
        structural_score += 0.14
    if re.search(r"^[\-*•]\s+", normalized_window, re.MULTILINE):
        structural_score += 0.10
    if "{" in normalized_window and "}" in normalized_window:
        structural_score += 0.08
    structural_score = min(1.0, structural_score)

    density_score = min(1.0, max(1, _estimate_text_tokens(normalized_window)) / 220.0)

    reference_score = 0.0
    normalized_anchor_terms = [term for term in (anchor_terms or []) if term]
    if normalized_anchor_terms:
        lowered_window = normalized_window.lower()
        anchor_hits = sum(1 for term in normalized_anchor_terms if term in lowered_window)
        reference_score = min(1.0, anchor_hits / max(1, min(4, len(normalized_anchor_terms))))

    return lexical_score * 0.38 + structural_score * 0.24 + density_score * 0.18 + reference_score * 0.20


def _select_entropy_middle_excerpt_start(
    text: str,
    *,
    head_chars: int,
    middle_chars: int,
    tail_chars: int,
    anchor_text: str = "",
) -> tuple[int | None, dict]:
    cleaned = str(text or "")
    if not cleaned or middle_chars <= 0:
        return None, {"window_selection": "center_window"}

    min_start = max(1, int(head_chars or 0) + 1)
    max_start = len(cleaned) - max(0, int(tail_chars or 0)) - int(middle_chars or 0) - 1
    if max_start <= min_start:
        return None, {"window_selection": "center_window"}

    center_start = max(min_start, min(max_start, (len(cleaned) - middle_chars) // 2))
    anchor_terms = _extract_fetch_anchor_terms(anchor_text)
    lowered_text = cleaned.lower()

    candidate_starts: set[int] = {center_start, min_start, max_start}
    step = max(200, middle_chars // 2)
    candidate_starts.update(range(min_start, max_start + 1, step))

    for term in anchor_terms[:6]:
        position = lowered_text.find(term)
        if position < 0:
            continue
        candidate_starts.add(max(min_start, min(max_start, position - middle_chars // 4)))

    best_start = center_start
    best_score = -1.0
    best_distance = 1.0
    for start in sorted(candidate_starts):
        window = cleaned[start : start + middle_chars]
        score = _score_fetch_excerpt_window(window, anchor_terms=anchor_terms)
        distance = abs(start - center_start) / max(1, max_start - min_start)
        if score > best_score + 1e-9 or (abs(score - best_score) <= 1e-9 and distance < best_distance):
            best_start = start
            best_score = score
            best_distance = distance

    selection = "center_window"
    if anchor_terms and best_start != center_start:
        selection = "entropy_anchor_window"
    elif best_start != center_start:
        selection = "entropy_window"
    return best_start, {"window_selection": selection, "window_entropy_score": round(max(0.0, best_score), 4)}


def _clip_text_preserving_ends(text: str, target_chars: int, *, anchor_text: str = "") -> tuple[str, dict]:
    cleaned = str(text or "")
    normalized_target = max(0, int(target_chars or 0))
    if not cleaned or normalized_target <= 0 or len(cleaned) <= normalized_target:
        return cleaned, {"strategy": "full_text", "excerpt_count": 1}

    if normalized_target < 240:
        return _clean_tool_text(cleaned, limit=normalized_target), {"strategy": "truncated_excerpt", "excerpt_count": 1}

    if normalized_target < 2_000:
        return _build_head_tail_excerpt(cleaned, normalized_target)

    base_marker_one = "\n\n[... middle excerpt follows ...]\n\n"
    base_marker_two = "\n\n[... final excerpt follows ...]\n\n"
    available = normalized_target - len(base_marker_one) - len(base_marker_two)
    if available < 1_500:
        return _build_head_tail_excerpt(cleaned, normalized_target)

    lengths = [
        max(520, int(available * 0.42)),
        max(360, int(available * 0.20)),
        max(420, available - max(520, int(available * 0.42)) - max(360, int(available * 0.20))),
    ]
    minimums = [420, 260, 320]

    def _compose_excerpt(current_lengths: list[int]):
        head_chars, middle_chars, tail_chars = current_lengths
        middle_start, selection_details = _select_entropy_middle_excerpt_start(
            cleaned,
            head_chars=head_chars,
            middle_chars=middle_chars,
            tail_chars=tail_chars,
            anchor_text=anchor_text,
        )
        if middle_start is None:
            middle_start = max(head_chars, (len(cleaned) - middle_chars) // 2)
            selection_details = {"window_selection": "center_window"}
        middle_end = middle_start + middle_chars
        tail_start = max(middle_end, len(cleaned) - tail_chars)
        if middle_start <= head_chars or tail_start <= middle_end:
            return None
        omitted_before = max(0, middle_start - head_chars)
        omitted_after = max(0, tail_start - middle_end)
        marker_one = f"\n\n[... {omitted_before:,} characters omitted before middle excerpt ...]\n\n"
        marker_two = f"\n\n[... {omitted_after:,} characters omitted before final excerpt ...]\n\n"
        total_len = head_chars + middle_chars + tail_chars + len(marker_one) + len(marker_two)
        return {
            "head_chars": head_chars,
            "middle_start": middle_start,
            "middle_end": middle_end,
            "tail_start": tail_start,
            "marker_one": marker_one,
            "marker_two": marker_two,
            "overflow": max(0, total_len - normalized_target),
            **selection_details,
        }

    composed = _compose_excerpt(lengths)
    if not composed:
        return _build_head_tail_excerpt(cleaned, normalized_target)
    if composed["overflow"] > 0:
        lengths = _shrink_excerpt_lengths(lengths, minimums, composed["overflow"])
        composed = _compose_excerpt(lengths)
    if not composed:
        return _build_head_tail_excerpt(cleaned, normalized_target)

    head = cleaned[: composed["head_chars"]].rstrip()
    middle = cleaned[composed["middle_start"] : composed["middle_end"]].strip()
    tail = cleaned[composed["tail_start"] :].lstrip()
    if not head or not middle or not tail:
        return _build_head_tail_excerpt(cleaned, normalized_target)
    return (
        f"{head}{composed['marker_one']}{middle}{composed['marker_two']}{tail}",
        {"strategy": "head_middle_tail_excerpt", "excerpt_count": 3},
    )


def _build_fetch_clipped_text(result: dict, token_threshold: int, clip_aggressiveness: int) -> tuple[str, int, dict]:
    raw_content = _clean_tool_text(result.get("content") or "")
    token_estimate = _estimate_text_tokens(raw_content)
    if not raw_content:
        return "", token_estimate, {"strategy": "empty_content", "excerpt_count": 0}

    if token_estimate <= token_threshold:
        return raw_content, token_estimate, {"strategy": "full_text", "excerpt_count": 1}

    clip_ratio = min(1.0, token_threshold / max(token_estimate, 1))
    preserve_multiplier = min(1.0, 1.8 - (_normalize_fetch_clip_aggressiveness(clip_aggressiveness) / 100) * 1.0)
    target_chars = max(2000, min(FETCH_SUMMARY_MAX_CHARS, int(len(raw_content) * clip_ratio * preserve_multiplier)))
    anchor_parts: list[str] = []
    for field_name in ("title", "meta_description", "structured_data", "content_source_element"):
        field_value = _clean_tool_text(result.get(field_name) or "", limit=600)
        if field_value:
            anchor_parts.append(field_value)
    outline = result.get("outline") if isinstance(result.get("outline"), list) else []
    if outline:
        anchor_parts.extend(
            _clean_tool_text(item, limit=120) for item in outline[:12] if _clean_tool_text(item, limit=120)
        )
    clipped_content, clip_details = _clip_text_preserving_ends(
        raw_content,
        target_chars,
        anchor_text=" ".join(anchor_parts),
    )
    result_text = clipped_content or raw_content
    return result_text, _estimate_text_tokens(result_text), clip_details


def _describe_fetch_content_mode(content_mode: str, clip_strategy: str) -> str:
    normalized_mode = str(content_mode or "").strip()
    normalized_strategy = str(clip_strategy or "").strip()
    if normalized_mode == "cleaned_full_text":
        return "Full cleaned page text."
    if normalized_mode == "clipped_text":
        if normalized_strategy == "head_middle_tail_excerpt":
            return "Excerpted page text with preserved leading, middle, and trailing sections."
        return "Excerpted page text with preserved leading and trailing sections."
    if normalized_mode == "budget_compact":
        return "Tool result was compacted further to fit the prompt budget."
    if normalized_mode == "budget_brief":
        return "Tool result was heavily compacted to fit the prompt budget."
    return "Page text excerpt."


def _build_fetch_diagnostic_fields(result: dict) -> dict:
    if not isinstance(result, dict):
        return {}

    content = _clean_tool_text(result.get("content") or "")
    warning = _clean_tool_text(result.get("fetch_warning") or "", limit=400)
    error = _clean_tool_text(result.get("error") or "", limit=400)
    status = result.get("status")
    status_label = f"HTTP {status}" if isinstance(status, int) and status > 0 else None

    if error:
        outcome = "error"
        detail = error
    elif not content:
        outcome = "empty_content"
        detail = warning or "The request completed but no extractable page content was returned."
    elif result.get("partial_content"):
        outcome = "partial_content"
        detail = warning or "Only partial page content could be recovered."
    elif warning:
        outcome = "limited_content"
        detail = warning
    else:
        outcome = "success"
        detail = "The page was fetched successfully and extractable content was returned."

    if status_label and detail:
        detail = f"{status_label}. {detail}"
    elif status_label:
        detail = status_label

    return {
        "fetch_attempted": True,
        "fetch_outcome": outcome,
        "content_char_count": len(content),
        "same_url_retry_recommended": False,
        "fetch_diagnostic": (
            f"fetch_url already attempted this URL. Outcome: {detail} "
            "Do not call fetch_url again for the same URL in this turn. "
            "If you need omitted sections or exact text from this page, use scroll_fetched_content or grep_fetched_content instead."
        ).strip(),
    }


def _normalize_fetch_content_source(value) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"main", "article", "body", "root"}:
        return normalized
    return ""


def _build_fetch_context_summary(result: dict, limit: int = 420) -> str:
    if not isinstance(result, dict):
        return ""

    parts: list[str] = []
    content_source = _normalize_fetch_content_source(result.get("content_source_element"))
    meta_description = _clean_tool_text(result.get("meta_description") or "", limit=180)
    structured_data = _clean_tool_text(result.get("structured_data") or "", limit=220)
    outline = result.get("outline") if isinstance(result.get("outline"), list) else []

    if content_source:
        parts.append(f"Primary container: {content_source}.")
    if meta_description:
        parts.append(f"Description: {meta_description}")
    if outline:
        headings = "; ".join(
            _clean_tool_text(item, limit=80) for item in outline[:4] if _clean_tool_text(item, limit=80)
        )
        if headings:
            parts.append(f"Outline anchors: {headings}")
    if structured_data:
        parts.append(f"Structured hints: {structured_data}")

    return _clean_tool_text(" ".join(parts), limit=limit)


def _infer_fetch_summary_profile(result: dict) -> dict:
    url = _clean_tool_text(result.get("url") or "", limit=280).casefold()
    title = _clean_tool_text(result.get("title") or "", limit=200).casefold()
    meta_description = _clean_tool_text(result.get("meta_description") or "", limit=200).casefold()
    content_format = str(result.get("content_format") or "").strip().lower()
    content_source = _normalize_fetch_content_source(result.get("content_source_element"))
    outline = result.get("outline") if isinstance(result.get("outline"), list) else []
    outline_text = " ".join(_clean_tool_text(item, limit=80).casefold() for item in outline[:10])
    content_preview = _clean_tool_text(result.get("content") or "", limit=600).casefold()
    haystack = " ".join(part for part in [url, title, meta_description, outline_text] if part)

    technical_terms = (
        "docs",
        "documentation",
        "api",
        "reference",
        "sdk",
        "guide",
        "manual",
        "developer",
        "endpoint",
        "configuration",
        "config",
        "parameter",
    )
    news_terms = (
        "news",
        "breaking",
        "reported",
        "announced",
        "press release",
        "headline",
        "today",
        "yesterday",
        "update",
    )

    if content_format in {"json", "xml"} or any(term in haystack for term in technical_terms):
        return {
            "name": "technical_documentation",
            "section_labels": "Summary, Key APIs or configuration, Important details, Constraints or caveats",
            "guidance": (
                "Preserve exact terminology, endpoint names, configuration keys, defaults, version numbers, and explicit limitations."
            ),
        }
    if any(term in haystack for term in news_terms) or (content_source == "article" and "blog" not in haystack):
        return {
            "name": "news_or_update",
            "section_labels": "Headline, What happened, Key facts, Why it matters, Open questions or uncertainty",
            "guidance": "Preserve timelines, named entities, attributed claims, and what is still unverified.",
        }
    if any(
        term in content_preview
        for term in ("api ", "endpoint", "config", "configuration", "schema", "get /", "post /", "request body")
    ):
        return {
            "name": "technical_documentation",
            "section_labels": "Summary, Key APIs or configuration, Important details, Constraints or caveats",
            "guidance": (
                "Preserve exact terminology, endpoint names, configuration keys, defaults, version numbers, and explicit limitations."
            ),
        }
    return {
        "name": "general_web_page",
        "section_labels": "Overview, Key points, Important details, Constraints or uncertainty",
        "guidance": "Preserve the page's main claims, exact figures, limitations, and actionable details.",
    }


def _estimate_fetch_summary_max_tokens(
    source_text: str,
    configured_max_tokens: int = FETCH_SUMMARIZE_MAX_OUTPUT_TOKENS,
) -> int:
    del source_text
    configured_cap = max(200, min(4_000, int(configured_max_tokens or FETCH_SUMMARIZE_MAX_OUTPUT_TOKENS)))
    return configured_cap


def _summarize_fetch_result(result: dict, fallback_url: str = "") -> str:
    if not isinstance(result, dict):
        return fallback_url[:60]

    error = _clean_tool_text(result.get("error") or "", limit=180)
    warning = _clean_tool_text(result.get("fetch_warning") or "", limit=180)
    title = _clean_tool_text(result.get("title") or "", limit=120)
    url = _clean_tool_text(result.get("url") or fallback_url or "", limit=120)

    if error:
        return f"Fetch failed: {error}"
    if result.get("partial_content"):
        return f"Partial page content extracted: {title or url or 'page'}"
    if warning:
        return f"Limited page content extracted: {title or url or 'page'}"
    if result.get("content"):
        return f"Page content extracted: {title or url or 'page'}"
    return f"No extractable page content: {title or url or 'page'}"


def _extract_chat_completion_text(response) -> str:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = str(item.get("text") or "")
                if text:
                    parts.append(text)
        return "".join(parts).strip()
    return str(content or "").strip()


def _snapshot_model_invocation_value(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _snapshot_model_invocation_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_snapshot_model_invocation_value(item) for item in value]
    return str(value)


def _build_model_invocation_usage_summary(
    provider_usage: dict,
    *,
    estimated_input_tokens: int | None = None,
    estimated_breakdown: dict | None = None,
    tool_schema_tokens: int | None = None,
) -> dict:
    received = bool(provider_usage.get("received"))
    summary = {
        "prompt_tokens": provider_usage.get("prompt_tokens") if received else None,
        "prompt_cache_hit_tokens": provider_usage.get("prompt_cache_hit_tokens") if received else 0,
        "prompt_cache_miss_tokens": provider_usage.get("prompt_cache_miss_tokens") if received else 0,
        "prompt_cache_write_tokens": provider_usage.get("prompt_cache_write_tokens") if received else 0,
        "completion_tokens": provider_usage.get("completion_tokens") if received else None,
        "total_tokens": provider_usage.get("total_tokens") if received else None,
        "missing_provider_usage": not received,
    }
    if estimated_input_tokens is not None:
        summary["estimated_input_tokens"] = max(0, int(estimated_input_tokens or 0))
    if isinstance(estimated_breakdown, dict):
        summary["input_breakdown"] = {str(key): max(0, int(value or 0)) for key, value in estimated_breakdown.items()}
    if tool_schema_tokens is not None:
        summary["tool_schema_tokens"] = max(0, int(tool_schema_tokens or 0))
    return summary


def _append_model_invocation_log(
    invocation_log_sink: list[dict] | None,
    *,
    agent_context: dict | None,
    step: int,
    call_type: str,
    retry_reason: str | None,
    model_target: dict,
    request_payload,
    response_summary,
    operation: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    estimated_input_tokens: int | None = None,
    prompt_cache_hit_tokens: int | None = None,
    prompt_cache_miss_tokens: int | None = None,
    prompt_cache_write_tokens: int | None = None,
    cost: float | None = None,
    latency_ms: int | None = None,
    response_status: str | None = None,
    error_type: str | None = None,
    error_message: str | None = None,
) -> None:
    context = agent_context if isinstance(agent_context, dict) else {}
    record = model_target.get("record") if isinstance(model_target, dict) else {}
    log_record = {
        "source_message_id": _coerce_int_range(context.get("source_message_id"), 0, 0, 2_147_483_647),
        "step": max(0, int(step or 0)),
        "call_type": str(call_type or "agent_step").strip() or "agent_step",
        "is_retry": bool(retry_reason),
        "retry_reason": str(retry_reason or "").strip() or None,
        "sub_agent_depth": _coerce_int_range(context.get("sub_agent_depth"), 0, 0, 8),
        "provider": str((record or {}).get("provider") or "").strip(),
        "api_model": str(model_target.get("api_model") or "").strip(),
        "operation": str(operation or call_type or "").strip() or None,
        "request_payload": _snapshot_model_invocation_value(request_payload),
        "response_summary": _snapshot_model_invocation_value(response_summary),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "estimated_input_tokens": estimated_input_tokens,
        "prompt_cache_hit_tokens": prompt_cache_hit_tokens,
        "prompt_cache_miss_tokens": prompt_cache_miss_tokens,
        "prompt_cache_write_tokens": prompt_cache_write_tokens,
        "cost": cost,
        "latency_ms": latency_ms,
        "response_status": response_status,
        "error_type": error_type,
        "error_message": error_message,
    }
    if isinstance(invocation_log_sink, list):
        invocation_log_sink.append(log_record)

    _trace_agent_event(
        "model_invocation_recorded",
        step=log_record["step"],
        call_type=log_record["call_type"],
        operation=log_record["operation"],
        provider=log_record["provider"],
        api_model=log_record["api_model"],
        response_status=log_record["response_status"],
        error_type=log_record["error_type"],
        error_message=log_record["error_message"],
        raw_fields={
            "agent_context": context,
            "request_payload": request_payload,
            "response_summary": response_summary,
            "record": log_record,
        },
    )


def _build_fetch_summary_source_text(
    result: dict,
    max_input_chars: int = FETCH_SUMMARIZE_MAX_INPUT_CHARS,
) -> str:
    parts: list[str] = []
    title = _clean_tool_text(result.get("title") or "", limit=200)
    url = _clean_tool_text(result.get("url") or "", limit=240)
    content_source = _normalize_fetch_content_source(result.get("content_source_element"))
    meta_description = _clean_tool_text(result.get("meta_description") or "", limit=600)
    structured_data = _clean_tool_text(result.get("structured_data") or "", limit=2_000)
    outline = result.get("outline") if isinstance(result.get("outline"), list) else []
    normalized_max_input_chars = max(4_000, min(1_000_000, int(max_input_chars or FETCH_SUMMARIZE_MAX_INPUT_CHARS)))
    content = _clean_tool_text(result.get("content") or "", limit=normalized_max_input_chars)
    if title:
        parts.append(f"Title: {title}")
    if url:
        parts.append(f"URL: {url}")
    if content_source:
        parts.append(f"Primary content source: {content_source}")
    if meta_description:
        parts.append(f"Meta description: {meta_description}")
    if structured_data:
        parts.append("Structured data:\n" + structured_data)
    if outline:
        headings = [
            f"- {_clean_tool_text(item, limit=120)}" for item in outline[:40] if _clean_tool_text(item, limit=120)
        ]
        if headings:
            parts.append("Page outline:\n" + "\n".join(headings))
    if content:
        parts.append("Page content:\n" + content)
    return "\n\n".join(parts).strip()


def _summarize_fetched_page_result(
    result: dict,
    focus: str,
    parent_model: str = "",
    *,
    agent_context: dict | None = None,
    invocation_log_sink: list[dict] | None = None,
) -> tuple[dict, str]:
    settings = get_app_settings()
    summarizer_model = get_operation_model("fetch_summarize", settings, fallback_model_id=parent_model)
    target = resolve_model_target(summarizer_model, settings)
    summary_max_input_chars = get_fetch_url_summarized_max_input_chars(settings)
    summary_max_output_tokens = get_fetch_url_summarized_max_output_tokens(settings)
    source_text = _build_fetch_summary_source_text(result, max_input_chars=summary_max_input_chars)
    if not source_text:
        raise ValueError("Fetched page did not contain enough text to summarize.")

    focus_text = _clean_tool_text(focus, limit=600)
    summary_profile = _infer_fetch_summary_profile(result)
    system_prompt = (
        "You are a precise web-page summarizer working for another AI assistant. "
        "Produce a dense factual summary of the fetched page using short section headers and flat bullet lists when they improve scanning. "
        "Keep exact numbers, dates, version names, URLs, constraints, and caveats when present. "
        "If a focus question is provided, begin with 'Focus answer:' and prioritize only the information relevant to that focus; say clearly when the page does not answer it. "
        f"For this page, prefer these section labels when relevant: {summary_profile['section_labels']}. "
        f"{summary_profile['guidance']} "
        "Return only the summary."
    )
    user_parts = []
    if focus_text:
        user_parts.append(f"Focus:\n{focus_text}")
    user_parts.append(source_text)
    max_output_tokens = _estimate_fetch_summary_max_tokens(
        source_text,
        configured_max_tokens=summary_max_output_tokens,
    )
    request_kwargs = apply_model_target_request_options(
        {
            "model": target["api_model"],
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "\n\n".join(user_parts)},
            ],
            "max_tokens": max_output_tokens,
            "temperature": 0.2,
        },
        target,
    )
    try:
        _t0_fetch_sum = time.monotonic()
        response = target["client"].chat.completions.create(**request_kwargs)
        _fetch_sum_latency_ms = max(0, round((time.monotonic() - _t0_fetch_sum) * 1000))
    except Exception as exc:
        _fetch_sum_latency_ms = (
            max(0, round((time.monotonic() - _t0_fetch_sum) * 1000)) if "_t0_fetch_sum" in dir() else None
        )
        _append_model_invocation_log(
            invocation_log_sink,
            agent_context=agent_context,
            step=_coerce_int_range((agent_context or {}).get("current_step"), 0, 0, 1_000),
            call_type="fetch_summarize",
            retry_reason=None,
            model_target=target,
            request_payload=request_kwargs,
            response_summary={
                "status": "error",
                "error": str(exc),
                "usage": {"missing_provider_usage": True},
            },
            operation="fetch_summarize",
            response_status="error",
            error_type=type(exc).__name__,
            error_message=str(exc),
            latency_ms=_fetch_sum_latency_ms,
        )
        raise
    summary_text = _clean_tool_text(_extract_chat_completion_text(response), limit=RAG_TOOL_RESULT_MAX_TEXT_CHARS)
    if not summary_text:
        raise ValueError("Fetch summarizer returned empty content.")

    response_usage = _extract_usage_metrics(getattr(response, "usage", None))
    _append_model_invocation_log(
        invocation_log_sink,
        agent_context=agent_context,
        step=_coerce_int_range((agent_context or {}).get("current_step"), 0, 0, 1_000),
        call_type="fetch_summarize",
        retry_reason=None,
        model_target=target,
        request_payload=request_kwargs,
        response_summary={
            "status": "ok",
            "usage": {
                "prompt_tokens": response_usage["prompt_tokens"] or None,
                "prompt_cache_hit_tokens": response_usage["prompt_cache_hit_tokens"],
                "prompt_cache_miss_tokens": response_usage["prompt_cache_miss_tokens"],
                "prompt_cache_write_tokens": response_usage["prompt_cache_write_tokens"],
                "completion_tokens": response_usage["completion_tokens"] or None,
                "total_tokens": response_usage["total_tokens"] or None,
                "missing_provider_usage": not bool(response_usage.get("usage_fields_present")),
            },
            "content_text": summary_text,
        },
        operation="fetch_summarize",
        response_status="ok",
        latency_ms=_fetch_sum_latency_ms,
        prompt_tokens=response_usage.get("prompt_tokens"),
        completion_tokens=response_usage.get("completion_tokens"),
        total_tokens=response_usage.get("total_tokens"),
        prompt_cache_hit_tokens=response_usage.get("prompt_cache_hit_tokens"),
        prompt_cache_miss_tokens=response_usage.get("prompt_cache_miss_tokens"),
        prompt_cache_write_tokens=response_usage.get("prompt_cache_write_tokens"),
    )

    summarized_result = {
        "url": str(result.get("url") or "").strip(),
        "title": str(result.get("title") or "").strip(),
        "summary": summary_text,
        "model": _clean_tool_text(summarizer_model, limit=120),
        "content_char_count": len(_clean_tool_text(result.get("content") or "")),
        "summary_profile": summary_profile["name"],
    }
    if focus_text:
        summarized_result["focus"] = focus_text
    return (
        summarized_result,
        f"Page summarized: {summarized_result.get('title') or summarized_result.get('url') or 'page'}",
    )


def _prepare_fetch_result_for_model(
    result: dict,
    fetch_url_token_threshold: int | None = None,
    fetch_url_clip_aggressiveness: int | None = None,
) -> dict:
    if not isinstance(result, dict):
        return result

    content = _clean_tool_text(result.get("content") or "")
    prepared = dict(result)
    content_source = _normalize_fetch_content_source(result.get("content_source_element"))
    meta_description = _clean_tool_text(result.get("meta_description") or "", limit=400)
    structured_data = _clean_tool_text(result.get("structured_data") or "", limit=1_600)
    recovery_hint = _build_recovery_hint_for_tool("fetch_url", {"url": result.get("url")})
    prepared["cleanup_applied"] = True
    prepared["content_token_estimate"] = _estimate_text_tokens(content)
    if content_source:
        prepared["content_source_element"] = content_source
    if meta_description:
        prepared["meta_description"] = meta_description
    if structured_data:
        prepared["structured_data"] = structured_data
    if recovery_hint:
        prepared["recovery_hint"] = recovery_hint
    prepared.update(_build_fetch_diagnostic_fields(prepared))
    if not content or prepared.get("error"):
        return prepared

    prepared["content"] = content
    prepared["content_mode"] = "cleaned_full_text"

    token_threshold = _normalize_fetch_token_threshold(fetch_url_token_threshold)
    if prepared["content_token_estimate"] <= token_threshold:
        return prepared

    clip_aggressiveness = _normalize_fetch_clip_aggressiveness(fetch_url_clip_aggressiveness)
    clipped_text, token_estimate, clip_details = _build_fetch_clipped_text(
        prepared, token_threshold, clip_aggressiveness
    )
    if not clipped_text or clipped_text == content:
        return prepared

    raw_char_count = len(content)
    clipped_char_count = len(clipped_text)
    clipped_pct = int(100 * clipped_char_count / max(raw_char_count, 1))
    clip_strategy = str(clip_details.get("strategy") or "head_tail_excerpt")
    coverage_note = (
        "Leading, middle, and trailing excerpts are preserved."
        if clip_strategy == "head_middle_tail_excerpt"
        else "The leading and trailing excerpts are preserved; the middle portion is omitted."
    )
    if clip_details.get("window_selection") in {"entropy_window", "entropy_anchor_window"}:
        coverage_note += " The middle excerpt is chosen from a higher-signal region instead of always using the literal center of the page."
    prepared["content"] = clipped_text
    prepared["content_mode"] = "clipped_text"
    prepared["clip_strategy"] = clip_strategy
    prepared["excerpt_count"] = max(1, int(clip_details.get("excerpt_count") or 1))
    context_summary = _build_fetch_context_summary(prepared)
    if context_summary:
        prepared["context_summary"] = context_summary
    prepared["summary_notice"] = (
        f"Content was clipped: showing {clipped_char_count:,} of {raw_char_count:,} characters "
        f"({clipped_pct}% of the page, approximately {token_estimate:,} tokens). "
        f"{coverage_note} "
        f"{('Context anchors: ' + context_summary + ' ') if context_summary else ''}"
        f"{recovery_hint or 'Use scroll_fetched_content to browse omitted sections and grep_fetched_content for exact text.'}"
    )
    prepared["content_token_estimate"] = token_estimate
    prepared["raw_content_available"] = True
    return prepared


def _build_fetch_tool_message_content(tool_args: dict, summary: str, transcript_result: dict) -> str:
    parts = []
    title = _clean_tool_text(transcript_result.get("title") or "", limit=160)
    url = _clean_tool_text(transcript_result.get("url") or tool_args.get("url") or "", limit=200)
    notice = _clean_tool_text(transcript_result.get("summary_notice") or "", limit=500)
    diagnostic = _clean_tool_text(transcript_result.get("fetch_diagnostic") or "", limit=280)
    content_format = str(transcript_result.get("content_format") or "").strip()
    content_source = _normalize_fetch_content_source(transcript_result.get("content_source_element"))
    outline = transcript_result.get("outline")
    context_summary = _clean_tool_text(transcript_result.get("context_summary") or "", limit=380)
    meta_description = _clean_tool_text(transcript_result.get("meta_description") or "", limit=260)
    structured_data = _clean_tool_text(transcript_result.get("structured_data") or "", limit=700)
    recovery_hint = _clean_tool_text(transcript_result.get("recovery_hint") or "", limit=280)
    budget_notice = _clean_tool_text(transcript_result.get("budget_notice") or "", limit=220)
    pages_extracted = transcript_result.get("pages_extracted")
    page_count = transcript_result.get("page_count")
    content_mode = str(transcript_result.get("content_mode") or "").strip()
    clip_strategy = str(transcript_result.get("clip_strategy") or "").strip()
    body_limit = None if content_mode in {"clipped_text", "budget_compact", "budget_brief"} else FETCH_SUMMARY_MAX_CHARS
    body = _clean_tool_text(transcript_result.get("content") or "", limit=body_limit)

    source_lines = []
    if title:
        source_lines.append(f"Title: {title}")
    if url:
        source_lines.append(f"URL: {url}")
    if content_source:
        source_lines.append(f"Primary content source: {content_source}")
    if content_format and content_format != "html":
        fmt_info = f"Format: {content_format}"
        if content_format == "pdf" and isinstance(pages_extracted, int) and isinstance(page_count, int):
            fmt_info += f" ({pages_extracted} of {page_count} pages extracted)"
        elif content_format == "pdf" and isinstance(pages_extracted, int):
            fmt_info += f" ({pages_extracted} pages extracted)"
        source_lines.append(fmt_info)
    if meta_description:
        source_lines.append(f"Description: {meta_description}")
    if source_lines:
        parts.append("## Source Metadata\n" + "\n".join(source_lines))

    coverage_lines = []
    if body:
        coverage_lines.append(f"Coverage: {_describe_fetch_content_mode(content_mode, clip_strategy)}")
    if transcript_result.get("raw_content_available") is True:
        coverage_lines.append(
            "Raw page recovery: Use scroll_fetched_content for sequential browsing and grep_fetched_content for exact text."
        )
    if content_mode in {"clipped_text", "budget_compact", "budget_brief"} and url:
        coverage_lines.append(f'Scroll example: scroll_fetched_content(url="{url}", start_line=1)')
        coverage_lines.append(f'Exact-text lookup example: grep_fetched_content(url="{url}", pattern="keyword")')
    if coverage_lines:
        parts.append("## Content Coverage\n" + "\n".join(coverage_lines))

    if summary:
        parts.append("## Fetch Summary\n" + f"Summary: {_clean_tool_text(summary, limit=300)}")

    note_lines = []
    if notice:
        note_lines.append(f"Note: {notice}")
    if diagnostic:
        note_lines.append(f"Fetch status: {diagnostic}")
    if budget_notice:
        note_lines.append(f"Budget note: {budget_notice}")
    if recovery_hint:
        note_lines.append(f"Recovery: {recovery_hint}")
    if context_summary:
        note_lines.append(f"Context anchors: {context_summary}")
    if note_lines:
        parts.append("## Retrieval Notes\n" + "\n".join(note_lines))

    if outline and isinstance(outline, list):
        heading_lines = [f"- {_clean_tool_text(str(h), limit=120)}" for h in outline[:50] if str(h).strip()]
        if heading_lines:
            parts.append("## Page Outline\n" + "\n".join(heading_lines))

    if structured_data:
        parts.append("## Structured Data\n" + structured_data)
    if body:
        body_heading = (
            "## Page Content [Excerpted]"
            if content_mode in {"clipped_text", "budget_compact", "budget_brief"}
            else "## Page Content [Full]"
        )
        parts.append(body_heading + "\n" + body)
    return "\n\n".join(parts).strip()


def _format_canvas_scroll_result_as_text(result: dict) -> str:
    """Format a scroll/range-read canvas result into human-readable text."""
    title = result.get("title") or result.get("document_path") or "Untitled"
    total = result.get("total_lines", 0)
    start = result.get("start_line", 1)
    end = result.get("end_line_actual", total)
    lines = result.get("visible_lines") or []
    parts = [f"### {title} (lines {start}–{end} of {total})"]
    if lines:
        parts.append("```")
        parts.append("\n".join(str(l) for l in lines))
        parts.append("```")
    nav = []
    if result.get("has_more_above"):
        nav.append(f"↑ More content above line {start}")
    if result.get("has_more_below"):
        nav.append(f"↓ More content below line {end}")
    if nav:
        parts.append(" | ".join(nav))
    return "\n".join(parts)


def _format_fetched_content_scroll_result_as_text(result: dict) -> str:
    """Format a fetched-page scroll result into human-readable text."""
    title = result.get("title") or result.get("url") or "Fetched page"
    total = result.get("line_count", 0)
    start = result.get("start_line", 1)
    end = result.get("end_line_actual", total)
    lines = result.get("visible_lines") or []
    parts = [f"### {title} (fetched lines {start}–{end} of {total})"]
    url = _clean_tool_text(result.get("url") or "", limit=220)
    if url:
        parts.append(f"URL: {url}")
    if lines:
        parts.append("```text")
        parts.append("\n".join(str(line) for line in lines))
        parts.append("```")
    nav = []
    if result.get("has_more_above"):
        nav.append(f"↑ More page content above line {start}")
    if result.get("has_more_below"):
        nav.append(f"↓ More page content below line {end}")
    if nav:
        parts.append(" | ".join(nav))
    note = _clean_tool_text(result.get("note") or "", limit=280)
    if note:
        parts.append(note)
    return "\n".join(parts)


def _format_canvas_expand_result_as_text(result: dict) -> str:
    """Format an expand/full-read canvas result into human-readable text."""
    title = result.get("title") or result.get("document_path") or "Untitled"
    fmt = result.get("format") or "text"
    lang = result.get("language") or ""
    line_count = result.get("line_count") or 0
    lines = result.get("visible_lines") or []
    truncated = result.get("is_truncated", False)
    header_parts = [fmt]
    if lang and lang != fmt:
        header_parts.append(lang)
    header_parts.append(f"{line_count} lines")
    parts = [f"### {title} ({', '.join(header_parts)})"]
    if lines:
        fence_lang = lang if lang else ""
        parts.append(f"```{fence_lang}")
        parts.append("\n".join(str(l) for l in lines))
        parts.append("```")
    if truncated:
        parts.append(f"[Truncated — showing {len(lines)} of {line_count} lines]")
    return "\n".join(parts)


def _format_canvas_read_result_as_text(tool_name: str, result: dict) -> str:
    """Convert a canvas read tool result from JSON to readable Markdown text."""
    if tool_name == "batch_read_canvas_documents":
        results_list = result.get("results") or []
        total = result.get("requested_count", len(results_list))
        ok = result.get("success_count", 0)
        sections = [f"## Batch Read: {ok}/{total} documents"]
        for item in results_list:
            if not isinstance(item, dict):
                continue
            if item.get("status") == "error":
                doc_id = item.get("document_id") or item.get("document_path") or "unknown"
                sections.append(f"### {doc_id}\nError: {item.get('error', 'unknown error')}")
            elif "start_line" in item and "end_line_actual" in item:
                sections.append(_format_canvas_scroll_result_as_text(item))
            else:
                sections.append(_format_canvas_expand_result_as_text(item))
        return "\n\n".join(sections)
    elif tool_name == "scroll_canvas_document":
        return _format_canvas_scroll_result_as_text(result)
    else:
        return _format_canvas_expand_result_as_text(result)


def _prepare_tool_result_for_transcript(
    tool_name: str,
    result,
    fetch_url_token_threshold: int | None = None,
    fetch_url_clip_aggressiveness: int | None = None,
):
    if tool_name == "fetch_url" and isinstance(result, dict):
        return _prepare_fetch_result_for_model(
            result,
            fetch_url_token_threshold=fetch_url_token_threshold,
            fetch_url_clip_aggressiveness=fetch_url_clip_aggressiveness,
        )
    if tool_name == "scroll_fetched_content" and isinstance(result, dict) and not result.get("error"):
        return _format_fetched_content_scroll_result_as_text(result)
    if tool_name in CANVAS_CONTEXT_READ_TOOL_NAMES and isinstance(result, dict):
        result = _format_canvas_read_result_as_text(tool_name, result)
    if tool_name in CANVAS_MUTATION_TOOL_NAMES and isinstance(result, dict):
        compact_result: dict[str, object] = {}
        for key in (
            "status",
            "action",
            "url",
            "document_id",
            "document_path",
            "title",
            "format",
            "language",
            "line_count",
            "path",
            "role",
            "summary",
            "expected_start_line",
            "document_count",
            "import_group_id",
            "chunked",
            "truncated",
            "content_format",
            "fetch_summary",
        ):
            value = result.get(key)
            if value not in (None, "", [], {}):
                compact_result[key] = value

        expected_lines = result.get("expected_lines")
        if isinstance(expected_lines, list) and expected_lines:
            compact_result["expected_lines"] = [str(line) for line in expected_lines[:20]]

        primary_locator = result.get("primary_locator") if isinstance(result.get("primary_locator"), dict) else None
        if primary_locator:
            compact_result["primary_locator"] = primary_locator

        document_snapshot = result.get("document") if isinstance(result.get("document"), dict) else None
        if document_snapshot:
            compact_document = {}
            for key in ("id", "title", "format", "language", "line_count", "path", "role", "summary"):
                value = document_snapshot.get(key)
                if value not in (None, "", [], {}):
                    compact_document[key] = value
            if compact_document:
                compact_result["document"] = compact_document

        documents = result.get("documents") if isinstance(result.get("documents"), list) else []
        if documents:
            compact_documents = []
            for entry in documents[:12]:
                if not isinstance(entry, dict):
                    continue
                compact_entry = {}
                document_id = entry.get("document_id") or entry.get("id")
                document_path = entry.get("document_path") or entry.get("path")
                if document_id not in (None, ""):
                    compact_entry["document_id"] = document_id
                if document_path not in (None, ""):
                    compact_entry["document_path"] = document_path
                for key in (
                    "title",
                    "format",
                    "language",
                    "line_count",
                    "source_url",
                    "source_title",
                    "source_kind",
                    "import_group_id",
                    "chunk_index",
                    "chunk_count",
                ):
                    value = entry.get(key)
                    if value not in (None, "", [], {}):
                        compact_entry[key] = value
                if compact_entry:
                    compact_documents.append(compact_entry)
            if compact_documents:
                compact_result["documents"] = compact_documents

        content_preview = _clean_tool_text(str(result.get("content") or ""), limit=400)
        if content_preview:
            compact_result["content_preview"] = content_preview
        if result.get("content_truncated") is True:
            compact_result["content_truncated"] = True

        if compact_result:
            return compact_result
    serialized = _serialize_tool_message_content(result)
    if len(serialized) > AGENT_TOOL_RESULT_TRANSCRIPT_MAX_CHARS:
        clipped = serialized[:AGENT_TOOL_RESULT_TRANSCRIPT_MAX_CHARS].rstrip() + "…"
        return f"{clipped} [CLIPPED: original {len(serialized)} chars]"
    return result


def _coerce_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, str):
                if item:
                    parts.append(item)
                continue
            if isinstance(item, dict):
                text = item.get("text")
                if text:
                    parts.append(str(text))
        return "".join(parts)
    return str(value)


def _extract_reasoning_and_content(message) -> tuple[str, str]:
    reasoning_text = _extract_reasoning_text(message).strip()
    content_text = _coerce_text(getattr(message, "content", "")).strip()
    return reasoning_text, content_text


def _normalize_json_like(value, depth: int = 0):
    if depth >= 6:
        return None
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        normalized = {}
        for key, item in value.items():
            normalized[str(key)] = _normalize_json_like(item, depth + 1)
        return normalized
    if isinstance(value, (list, tuple)):
        return [_normalize_json_like(item, depth + 1) for item in value]
    if hasattr(value, "__dict__"):
        return _normalize_json_like(vars(value), depth + 1)
    return _coerce_text(value)


def _normalize_reasoning_details(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    normalized = []
    for item in value:
        candidate = _normalize_json_like(item)
        if isinstance(candidate, dict):
            normalized.append(candidate)
    return normalized


def _extract_reasoning_details_text(reasoning_details) -> str:
    parts = []
    for detail in _normalize_reasoning_details(reasoning_details):
        text = _coerce_text(detail.get("text") or "")
        if text:
            parts.append(text)
    return "".join(parts)


def _extract_reasoning_text(value) -> str:
    reasoning_text = _coerce_text(getattr(value, "reasoning_content", ""))
    if reasoning_text:
        return reasoning_text

    reasoning_text = _coerce_text(_read_api_field(value, "reasoning", ""))
    if reasoning_text:
        return reasoning_text

    # Check metadata.reasoning_content for stored messages (loaded from DB)
    metadata = _read_api_field(value, "metadata", {})
    if isinstance(metadata, dict):
        reasoning_text = _coerce_text(metadata.get("reasoning_content", ""))
        if reasoning_text:
            return reasoning_text

    return _extract_reasoning_details_text(_read_api_field(value, "reasoning_details", []))


def _merge_reasoning_details(target: list[dict], new_items) -> list[dict]:
    merged = list(target or [])
    for detail in _normalize_reasoning_details(new_items):
        detail_type = str(detail.get("type") or "").strip()
        detail_id = str(detail.get("id") or "").strip()
        detail_index = detail.get("index")
        detail_format = str(detail.get("format") or "").strip()
        text = _coerce_text(detail.get("text") or "")
        existing = None
        for candidate in merged:
            if not isinstance(candidate, dict):
                continue
            if str(candidate.get("type") or "").strip() != detail_type:
                continue
            if str(candidate.get("id") or "").strip() != detail_id:
                continue
            if candidate.get("index") != detail_index:
                continue
            if str(candidate.get("format") or "").strip() != detail_format:
                continue
            existing = candidate
            break
        if existing is None:
            merged.append(dict(detail))
            continue
        if text:
            existing["text"] = _coerce_text(existing.get("text") or "") + text
        for key, value in detail.items():
            if key == "text":
                continue
            if existing.get(key) in (None, "", []):
                existing[key] = value
    return merged


def _extract_stream_delta_texts(chunk) -> tuple[str, str, list[dict]]:
    if not getattr(chunk, "choices", None):
        return "", "", []
    delta = getattr(chunk.choices[0], "delta", None)
    if delta is None:
        return "", "", []
    reasoning_details = _normalize_reasoning_details(_read_api_field(delta, "reasoning_details", []))
    reasoning_text = _extract_reasoning_text(delta)
    content_text = _coerce_text(getattr(delta, "content", ""))
    return reasoning_text, content_text, reasoning_details


def _close_model_response(response) -> None:
    close_response = getattr(response, "close", None)
    if callable(close_response):
        try:
            close_response()
        except Exception:
            pass


def _read_api_field(value, key: str, default=None):
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _parse_json_like_text(text: str):
    raw_text = str(text or "").strip()
    if not raw_text:
        return None
    try:
        return json.loads(raw_text)
    except Exception:
        pass
    try:
        return ast.literal_eval(raw_text)
    except Exception:
        return None


def _strip_tool_argument_code_fence(text: str) -> str | None:
    match = TOOL_ARGUMENT_CODE_FENCE_RE.match(str(text or ""))
    if not match:
        return None
    return str(match.group("body") or "").strip()


def _strip_tool_argument_language_label(text: str) -> str | None:
    raw_text = str(text or "").strip()
    if not raw_text or "\n" not in raw_text:
        return None

    first_line, remainder = raw_text.split("\n", 1)
    if first_line.strip().lower() not in TOOL_ARGUMENT_LANGUAGE_LABELS:
        return None

    cleaned_remainder = remainder.strip()
    if not cleaned_remainder.startswith(("{", "[", "<")):
        return None
    return cleaned_remainder


def _iter_tool_argument_text_candidates(arguments_text: str):
    raw_text = str(arguments_text or "").strip()
    if not raw_text:
        return

    pending = [raw_text]
    seen = set()

    while pending:
        candidate = str(pending.pop(0) or "").strip()
        if not candidate or candidate in seen:
            continue

        seen.add(candidate)
        yield candidate

        html_unescaped = html.unescape(candidate).strip()
        if html_unescaped and html_unescaped not in seen and html_unescaped != candidate:
            pending.append(html_unescaped)

        fence_inner = _strip_tool_argument_code_fence(candidate)
        if fence_inner and fence_inner not in seen:
            pending.append(fence_inner)

        unlabeled = _strip_tool_argument_language_label(candidate)
        if unlabeled and unlabeled not in seen:
            pending.append(unlabeled)

        # Strict parsing mode: do not attempt custom fragment repair.


def _parse_dsml_argument_value(value_text: str, attrs_text: str = ""):
    raw_value = str(value_text or "")
    if DSML_STRING_ATTR_RE.search(str(attrs_text or "")):
        return raw_value

    parsed_value = _parse_json_like_text(raw_value)
    if parsed_value is not None:
        return parsed_value

    return raw_value.strip()


def _parse_dsml_argument_object(arguments_text: str) -> dict | None:
    raw_arguments = str(arguments_text or "")
    parsed_arguments = {}
    found_parameter = False

    for match in DSML_PARAMETER_TAG_RE.finditer(raw_arguments):
        found_parameter = True
        field_name = str(match.group("name") or "").strip()
        if not field_name:
            continue

        field_value = _parse_dsml_argument_value(match.group("value"), match.group("attrs"))
        existing_value = parsed_arguments.get(field_name)
        if existing_value is None:
            parsed_arguments[field_name] = field_value
            continue
        if isinstance(existing_value, list):
            existing_value.append(field_value)
            continue
        parsed_arguments[field_name] = [existing_value, field_value]

    if not found_parameter:
        return None
    return parsed_arguments


def _extract_dsml_tool_calls_from_content(content_text: str) -> tuple[str, list[dict] | None]:
    raw_content = str(content_text or "")
    invoke_matches = list(DSML_INVOKE_TAG_RE.finditer(raw_content))
    if not invoke_matches:
        return raw_content, None

    tool_calls = []
    dsml_start = invoke_matches[0].start()
    function_calls_tag_match = DSML_FUNCTION_CALLS_TAG_RE.search(raw_content)
    if function_calls_tag_match and function_calls_tag_match.start() < dsml_start:
        dsml_start = function_calls_tag_match.start()
    for index, match in enumerate(invoke_matches, start=1):
        tool_name = str(match.group("name") or "").strip()
        if not tool_name:
            continue

        next_start = invoke_matches[index].start() if index < len(invoke_matches) else len(raw_content)
        arguments_text = raw_content[match.end() : next_start]
        parsed_arguments = _parse_dsml_argument_object(arguments_text) or {}
        tool_calls.append(
            {
                "id": f"content-tool-call-{index}",
                "name": tool_name,
                "arguments": parsed_arguments,
            }
        )

    if not tool_calls:
        return raw_content, None

    return raw_content[:dsml_start].strip(), tool_calls


def _prefer_content_dsml_tool_calls(
    content_text: str,
    tool_calls: list[dict] | None,
    tool_call_error: str | None,
) -> tuple[str, list[dict] | None, str | None]:
    normalized_content, content_tool_calls = _extract_dsml_tool_calls_from_content(content_text)
    if content_tool_calls:
        return normalized_content, content_tool_calls, None
    return content_text, tool_calls, tool_call_error


def _parse_tool_call_arguments(arguments_text: str, label: str) -> tuple[dict | None, str | None]:
    raw_arguments = str(arguments_text or "").strip()
    if not raw_arguments:
        return {}, None

    json_error = None
    try:
        json.loads(raw_arguments)
    except json.JSONDecodeError as exc:
        json_error = exc.msg

    saw_non_object_candidate = False
    for candidate in _iter_tool_argument_text_candidates(raw_arguments):
        parsed_arguments = _parse_json_like_text(candidate)
        if parsed_arguments is None:
            parsed_arguments = _parse_dsml_argument_object(candidate)
        if parsed_arguments is None:
            continue
        if isinstance(parsed_arguments, dict):
            return parsed_arguments, None
        saw_non_object_candidate = True

    if saw_non_object_candidate:
        return None, f"Tool arguments for {label} must be an object"

    if raw_arguments.startswith("<"):
        return None, f"Invalid tool arguments JSON for {label}: {json_error or 'Could not parse arguments'}"

    if raw_arguments.lstrip().startswith("{"):
        return None, f"Invalid tool arguments JSON for {label}: {json_error or 'Could not parse arguments'}"
    return None, f"Invalid tool arguments JSON for {label}: {json_error or 'Could not parse arguments'}"


def _extract_native_tool_calls(message) -> tuple[list[dict] | None, str | None]:
    raw_tool_calls = _read_api_field(message, "tool_calls") or []
    if not raw_tool_calls:
        return None, None

    normalized_calls = []
    for index, raw_call in enumerate(raw_tool_calls, start=1):
        function = _read_api_field(raw_call, "function")
        tool_name = str(_read_api_field(function, "name") or "").strip()
        if not tool_name:
            return None, f"tool_calls[{index}] is missing a tool name"

        arguments_text = _coerce_text(_read_api_field(function, "arguments", ""))
        tool_args, parse_error = _parse_tool_call_arguments(arguments_text, tool_name)
        if parse_error:
            return None, parse_error

        normalized_calls.append(
            {
                "id": str(_read_api_field(raw_call, "id") or f"tool-call-{index}"),
                "name": tool_name,
                "arguments": tool_args or {},
            }
        )
    return normalized_calls, None


def _merge_stream_tool_call_delta(tool_call_parts: list[dict], delta) -> None:
    raw_tool_calls = _read_api_field(delta, "tool_calls") or []
    for fallback_index, raw_call in enumerate(raw_tool_calls):
        index_value = _read_api_field(raw_call, "index", fallback_index)
        try:
            index = max(0, int(index_value))
        except (TypeError, ValueError):
            index = fallback_index

        while len(tool_call_parts) <= index:
            tool_call_parts.append({"id": "", "name": "", "arguments_parts": []})

        entry = tool_call_parts[index]
        call_id = _read_api_field(raw_call, "id")
        if call_id:
            entry["id"] = str(call_id)

        function = _read_api_field(raw_call, "function")
        name_part = str(_read_api_field(function, "name") or "")
        if name_part:
            if not entry["name"]:
                entry["name"] = name_part
            elif not entry["name"].endswith(name_part):
                entry["name"] += name_part

        arguments_part = _coerce_text(_read_api_field(function, "arguments", ""))
        if arguments_part:
            entry["arguments_parts"].append(arguments_part)


def _stream_tool_call_entry_has_meaningful_content(raw_call: dict) -> bool:
    if not isinstance(raw_call, dict):
        return False
    if str(raw_call.get("name") or "").strip():
        return True
    arguments_parts = raw_call.get("arguments_parts") if isinstance(raw_call.get("arguments_parts"), list) else []
    return any(str(part or "") for part in arguments_parts)


def _has_meaningful_stream_tool_calls(tool_call_parts: list[dict]) -> bool:
    return any(_stream_tool_call_entry_has_meaningful_content(raw_call) for raw_call in tool_call_parts)


def _extract_partial_json_string_value(arguments_text: str, field_name: str) -> str | None:
    raw_arguments = str(arguments_text or "")
    raw_field_name = str(field_name or "").strip()
    if not raw_arguments or not raw_field_name:
        return None

    depth = 0
    in_string = False
    escape_next = False
    string_chars: list[str] = []
    value_start = None

    for index, char in enumerate(raw_arguments):
        if in_string:
            if escape_next:
                string_chars.append(char)
                escape_next = False
                continue
            if char == "\\":
                escape_next = True
                string_chars.append(char)
                continue
            if char == '"':
                in_string = False
                if depth == 1:
                    candidate_key = "".join(string_chars)
                    look_ahead = index + 1
                    while look_ahead < len(raw_arguments) and raw_arguments[look_ahead].isspace():
                        look_ahead += 1
                    if (
                        candidate_key == raw_field_name
                        and look_ahead < len(raw_arguments)
                        and raw_arguments[look_ahead] == ":"
                    ):
                        look_ahead += 1
                        while look_ahead < len(raw_arguments) and raw_arguments[look_ahead].isspace():
                            look_ahead += 1
                        if look_ahead < len(raw_arguments) and raw_arguments[look_ahead] == '"':
                            value_start = look_ahead + 1
                            break
                string_chars = []
                continue
            string_chars.append(char)
            continue

        if char == '"':
            in_string = True
            escape_next = False
            string_chars = []
            continue
        if char == "{":
            depth += 1
            continue
        if char == "}" and depth > 0:
            depth -= 1

    if value_start is None:
        return None

    value_chars = []
    index = value_start
    while index < len(raw_arguments):
        char = raw_arguments[index]
        if char == '"':
            return "".join(value_chars)
        if char != "\\":
            value_chars.append(char)
            index += 1
            continue

        index += 1
        if index >= len(raw_arguments):
            break

        escape_char = raw_arguments[index]
        if escape_char in {'"', "\\", "/"}:
            value_chars.append(escape_char)
            index += 1
            continue
        if escape_char == "b":
            value_chars.append("\b")
            index += 1
            continue
        if escape_char == "f":
            value_chars.append("\f")
            index += 1
            continue
        if escape_char == "n":
            value_chars.append("\n")
            index += 1
            continue
        if escape_char == "r":
            value_chars.append("\r")
            index += 1
            continue
        if escape_char == "t":
            value_chars.append("\t")
            index += 1
            continue
        if escape_char == "u":
            hex_value = raw_arguments[index + 1 : index + 5]
            if len(hex_value) < 4 or any(char not in string.hexdigits for char in hex_value):
                break
            value_chars.append(chr(int(hex_value, 16)))
            index += 5
            continue

        value_chars.append(escape_char)
        index += 1

    return "".join(value_chars)


def _coerce_streaming_canvas_preview_int(value) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _normalize_streaming_canvas_preview_lines(value) -> list[str] | None:
    if value is None:
        return []
    if not isinstance(value, list):
        return None
    return [str(line) for line in value]


def _build_streaming_canvas_line_edit_preview(
    canvas_state: dict | None,
    tool_name: str,
    tool_args: dict,
) -> tuple[str | None, dict | None]:
    if not isinstance(canvas_state, dict) or not isinstance(tool_args, dict):
        return None, None

    document_id = str(tool_args.get("document_id") or "").strip() or None
    document_path = str(tool_args.get("document_path") or "").strip() or None
    try:
        _, document = find_canvas_document(canvas_state, document_id=document_id, document_path=document_path)
    except Exception:
        return None, None

    existing_lines = list_canvas_lines(document.get("content") or "")
    next_lines: list[str] | None = None

    if tool_name == "insert_canvas_lines":
        after_line = _coerce_streaming_canvas_preview_int(tool_args.get("after_line"))
        additions = _normalize_streaming_canvas_preview_lines(tool_args.get("lines"))
        if after_line is None or additions is None or after_line < 0 or after_line > len(existing_lines):
            return None, document
        next_lines = [*existing_lines[:after_line], *additions, *existing_lines[after_line:]]
    else:
        start_line = _coerce_streaming_canvas_preview_int(tool_args.get("start_line"))
        end_line = _coerce_streaming_canvas_preview_int(tool_args.get("end_line"))
        if (
            start_line is None
            or end_line is None
            or start_line < 1
            or end_line < start_line
            or start_line > len(existing_lines)
            or end_line > len(existing_lines)
        ):
            return None, document

        replacement = (
            []
            if tool_name == "delete_canvas_lines"
            else _normalize_streaming_canvas_preview_lines(tool_args.get("lines"))
        )
        if replacement is None:
            return None, document
        next_lines = [*existing_lines[: start_line - 1], *replacement, *existing_lines[end_line:]]

    return join_canvas_lines(next_lines), document


def _build_streaming_canvas_batch_edit_preview(
    canvas_state: dict | None,
    tool_args: dict,
) -> tuple[str | None, dict | None]:
    if not isinstance(canvas_state, dict) or not isinstance(tool_args, dict):
        return None, None

    target_args = tool_args
    raw_targets = tool_args.get("targets")
    if isinstance(raw_targets, dict):
        target_args = raw_targets
    elif isinstance(raw_targets, list):
        if len(raw_targets) == 1 and isinstance(raw_targets[0], list):
            raw_targets = raw_targets[0]
        if len(raw_targets) != 1 or not isinstance(raw_targets[0], dict):
            return None, None
        target_args = raw_targets[0]

    document_id = str(target_args.get("document_id") or "").strip() or None
    document_path = str(target_args.get("document_path") or "").strip() or None
    try:
        _, document = find_canvas_document(canvas_state, document_id=document_id, document_path=document_path)
    except Exception:
        return None, None

    preview_state = create_canvas_runtime_state([dict(document)], active_document_id=document.get("id"))
    try:
        result = batch_canvas_edits(
            preview_state,
            target_args.get("operations") or [],
            document_id=document.get("id"),
            atomic=True,
        )
    except Exception:
        return None, document

    preview_document = result.get("document") if isinstance(result.get("document"), dict) else document
    return str(preview_document.get("content") or ""), preview_document


def _build_streaming_canvas_transform_preview(
    canvas_state: dict | None,
    tool_args: dict,
) -> tuple[str | None, dict | None]:
    if not isinstance(canvas_state, dict) or not isinstance(tool_args, dict):
        return None, None

    document_id = str(tool_args.get("document_id") or "").strip() or None
    document_path = str(tool_args.get("document_path") or "").strip() or None
    try:
        _, document = find_canvas_document(canvas_state, document_id=document_id, document_path=document_path)
    except Exception:
        return None, None

    if tool_args.get("pattern") in (None, "") or tool_args.get("replacement") is None:
        return None, document

    preview_state = create_canvas_runtime_state([dict(document)], active_document_id=document.get("id"))
    try:
        result = transform_canvas_lines(
            preview_state,
            tool_args.get("pattern", ""),
            tool_args.get("replacement", ""),
            document_id=document.get("id"),
            scope=tool_args.get("scope") or "all",
            is_regex=tool_args.get("is_regex") is True,
            case_sensitive=True if "case_sensitive" not in tool_args else tool_args.get("case_sensitive") is True,
            count_only=False,
        )
    except Exception:
        return None, document

    preview_document = result.get("document") if isinstance(result.get("document"), dict) else document
    return str(preview_document.get("content") or ""), preview_document


def _build_streaming_canvas_tool_preview(
    tool_call_parts: list[dict],
    canvas_state: dict | None = None,
) -> dict | None:
    for reverse_index, raw_call in enumerate(reversed(tool_call_parts)):
        tool_name = str(raw_call.get("name") or "").strip()
        if tool_name not in CANVAS_STREAM_OPEN_TOOL_NAMES:
            continue

        preview_index = len(tool_call_parts) - reverse_index - 1

        arguments_text = "".join(raw_call.get("arguments_parts") or [])
        snapshot = {}
        for field_name in ("title", "format", "language", "path", "role", "document_id", "document_path"):
            value = _extract_partial_json_string_value(arguments_text, field_name)
            if value is not None:
                snapshot[field_name] = value

        content = None
        content_mode = "append"
        parsed_arguments, parse_error = _parse_tool_call_arguments(arguments_text, tool_name)
        if parse_error is None and isinstance(parsed_arguments, dict):
            for field_name in ("title", "format", "language", "path", "role", "document_id", "document_path"):
                value = parsed_arguments.get(field_name)
                if value is not None:
                    snapshot[field_name] = str(value).strip()
        if tool_name in CANVAS_STREAM_CONTENT_TOOL_NAMES:
            if (
                parse_error is None
                and isinstance(parsed_arguments, dict)
                and parsed_arguments.get("content") is not None
            ):
                content = str(parsed_arguments.get("content") or "")
            else:
                content = _extract_partial_json_string_value(arguments_text, "content")
        elif tool_name in CANVAS_STREAM_REPLACE_CONTENT_TOOL_NAMES:
            if tool_name in {"replace_canvas_lines", "insert_canvas_lines", "delete_canvas_lines"}:
                content, resolved_document = _build_streaming_canvas_line_edit_preview(
                    canvas_state, tool_name, parsed_arguments or {}
                )
            elif tool_name == "batch_canvas_edits":
                content, resolved_document = _build_streaming_canvas_batch_edit_preview(
                    canvas_state, parsed_arguments or {}
                )
            else:
                content, resolved_document = _build_streaming_canvas_transform_preview(
                    canvas_state, parsed_arguments or {}
                )
            if resolved_document:
                resolved_document_id = str(resolved_document.get("id") or "").strip()
                resolved_document_path = str(resolved_document.get("path") or "").strip()
                if resolved_document_id:
                    snapshot.setdefault("document_id", resolved_document_id)
                if resolved_document_path:
                    snapshot.setdefault("document_path", resolved_document_path)
                for field_name in ("title", "path", "role", "format", "language"):
                    value = resolved_document.get(field_name)
                    if value is not None and not snapshot.get(field_name):
                        snapshot[field_name] = str(value).strip()
            if content is not None:
                content_mode = "replace"

        return {
            "tool": tool_name,
            "preview_key": f"canvas-call-{preview_index}",
            "snapshot": snapshot,
            "content": content,
            "content_mode": content_mode,
        }
    return None


def _finalize_stream_tool_calls(tool_call_parts: list[dict]) -> tuple[list[dict] | None, str | None]:
    meaningful_tool_call_parts = [
        raw_call for raw_call in tool_call_parts if _stream_tool_call_entry_has_meaningful_content(raw_call)
    ]
    if not meaningful_tool_call_parts:
        return None, None

    normalized_calls = []
    for index, raw_call in enumerate(meaningful_tool_call_parts, start=1):
        tool_name = str(raw_call.get("name") or "").strip()
        if not tool_name:
            return None, f"tool_calls[{index}] is missing a tool name"

        arguments_text = "".join(raw_call.get("arguments_parts") or [])
        tool_args, parse_error = _parse_tool_call_arguments(arguments_text, tool_name)
        if parse_error:
            return None, parse_error

        normalized_calls.append(
            {
                "id": str(raw_call.get("id") or f"tool-call-{index}"),
                "name": tool_name,
                "arguments": tool_args or {},
            }
        )
    return normalized_calls, None


def _build_assistant_tool_call_message(content_text: str, tool_calls: list[dict], reasoning_details=None) -> dict:
    serialized_tool_calls = []
    assistant_message_id = ""
    for tool_call in tool_calls:
        tool_call_id = str(tool_call.get("id") or "").strip()
        if not assistant_message_id and tool_call_id:
            assistant_message_id = tool_call_id
        serialized_tool_calls.append(
            {
                "id": tool_call_id,
                "type": "function",
                "function": {
                    "name": _normalize_tool_name(str(tool_call.get("name") or "").strip()),
                    "arguments": json.dumps(tool_call.get("arguments") or {}, ensure_ascii=False),
                },
            }
        )
    message = {
        "role": "assistant",
        "content": str(content_text or ""),
        "tool_calls": parse_message_tool_calls(serialized_tool_calls),
        **({"id": assistant_message_id} if assistant_message_id else {}),
    }
    normalized_reasoning_details = _normalize_reasoning_details(reasoning_details)
    if normalized_reasoning_details:
        message["reasoning_details"] = normalized_reasoning_details
    return message


def _strip_intermediate_tool_call_content(messages: list[dict]) -> list[dict]:
    """Return a copy of *messages* with ``content`` set to ``None`` for every
    assistant message that also carries ``tool_calls``.

    When a model writes planning/announcement text before a tool call (e.g.
    "Now I will expand the canvas document…"), that text is stored in the
    assistant message alongside the tool_calls.  On the next model turn the
    model sees its own earlier announcement in the conversation history and
    tends to reproduce it verbatim, causing the same text to appear multiple
    times across multi-step runs.  Nullifying the content of those intermediate
    messages prevents the reproduction while keeping all tool-call/result pairs
    intact for continuity.  The reasoning-replay mechanism already captures the
    model's step-by-step thinking, so nothing of value is lost.
    """
    result = []
    for msg in messages:
        if (
            isinstance(msg, dict)
            and str(msg.get("role") or "").strip() == "assistant"
            and msg.get("tool_calls")
            and str(msg.get("content") or "").strip()
        ):
            msg = {**msg, "content": None}
        result.append(msg)
    return result


def _has_native_reasoning_details(messages: list[dict]) -> bool:
    for message in reversed(messages or []):
        if not isinstance(message, dict):
            continue
        if str(message.get("role") or "").strip() != "assistant":
            continue
        if not isinstance(message.get("tool_calls"), list) or not message.get("tool_calls"):
            continue
        return bool(_normalize_reasoning_details(message.get("reasoning_details")))
    return False


def _serialize_tool_message_content(payload) -> str:
    if isinstance(payload, str):
        return payload
    try:
        return json.dumps(payload, ensure_ascii=False)
    except TypeError:
        return json.dumps({"value": str(payload)}, ensure_ascii=False)


def _validate_scalar_type(value, expected_type: str) -> bool:
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    return True


def _parse_json_like_value(value):
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return None
    return _parse_json_like_text(value)


def _drop_null_tool_fields(value):
    if isinstance(value, dict):
        normalized = {}
        for key, item in value.items():
            if item is None:
                continue
            normalized[key] = _drop_null_tool_fields(item)
        return normalized
    if isinstance(value, list):
        return [_drop_null_tool_fields(item) for item in value]
    return value


def _coerce_clarification_question_item(raw_question):
    if isinstance(raw_question, dict):
        return raw_question
    if not isinstance(raw_question, str):
        return None

    text = raw_question.strip()
    if not text:
        return None

    parsed = _parse_json_like_value(text)
    if isinstance(parsed, dict):
        return parsed

    return {
        "label": text,
        "input_type": "text",
    }


def _infer_create_canvas_document_title(tool_args: dict) -> str:
    raw_path = str(tool_args.get("path") or "").strip().replace("\\", "/")
    if raw_path:
        basename = raw_path.rstrip("/").split("/")[-1].strip()
        if basename:
            return basename
    return "Canvas"


def _validate_tool_arguments(tool_name: str, tool_args: dict) -> str | None:
    tool_name = _normalize_tool_name(tool_name)
    spec = TOOL_SPEC_BY_NAME.get(tool_name)
    if not spec:
        return f"Unknown tool: {tool_name}"
    if not isinstance(tool_args, dict):
        return f"Tool arguments for {tool_name} must be a JSON object"

    if tool_name == "append_scratchpad" and "notes" not in tool_args and "note" in tool_args:
        legacy_note = tool_args.pop("note")
        tool_args["notes"] = [legacy_note]
    if tool_name in {"append_scratchpad", "replace_scratchpad"} and "section" not in tool_args:
        tool_args["section"] = "notes"
    if tool_name in SEARCH_QUERY_BATCHED_TOOL_NAMES:
        _coerce_search_tool_queries(tool_args, ensure_key=True)
    if tool_name == "create_canvas_document" and not str(tool_args.get("title") or "").strip():
        tool_args["title"] = _infer_create_canvas_document_title(tool_args)

    # Models sometimes emit optional selectors like document_path as explicit null.
    # Treat those as omitted fields so otherwise-valid tool calls still execute.
    normalized_tool_args = _drop_null_tool_fields(tool_args)
    tool_args.clear()
    tool_args.update(normalized_tool_args)

    schema = spec.get("parameters") or {}
    properties = schema.get("properties") or {}
    required = schema.get("required") or []

    for field_name in required:
        if field_name not in tool_args:
            return f"Missing required argument '{field_name}' for {tool_name}"

    # Strip keys that are clearly not valid property names (e.g. code content that leaked
    # into a key position due to model serialisation errors: contains ';', '*', '=', spaces, etc.).
    bogus_keys = [k for k in list(tool_args) if k not in properties and not _VALID_IDENTIFIER_RE.match(k)]
    for bk in bogus_keys:
        del tool_args[bk]

    for key, value in tool_args.items():
        property_schema = properties.get(key)
        if not property_schema:
            return f"Unexpected argument '{key}' for {tool_name}"

        expected_type = property_schema.get("type")

        if expected_type == "array" and isinstance(value, str):
            parsed_value = _parse_json_like_value(value)
            if isinstance(parsed_value, list):
                value = parsed_value
            else:
                value = [value]
            tool_args[key] = value
        elif expected_type == "integer" and isinstance(value, str):
            try:
                coerced_value = int(value.strip())
            except (TypeError, ValueError):
                coerced_value = value
            else:
                value = coerced_value
                tool_args[key] = value
        elif expected_type == "object" and isinstance(value, str):
            parsed_value = _parse_json_like_value(value)
            if isinstance(parsed_value, dict):
                value = parsed_value
                tool_args[key] = value

        if expected_type and not _validate_scalar_type(value, expected_type):
            return f"Invalid type for '{key}' in {tool_name}: expected {expected_type}"
        if expected_type == "array":
            item_schema = property_schema.get("items") or {}
            item_type = item_schema.get("type")
            normalized_items = []
            for item in value:
                normalized_item = item
                if item_type == "object" and isinstance(item, str):
                    if tool_name == "ask_clarifying_question":
                        normalized_item = _coerce_clarification_question_item(item)
                    else:
                        parsed_item = _parse_json_like_value(item)
                        if isinstance(parsed_item, dict):
                            normalized_item = parsed_item
                normalized_items.append(normalized_item)
            if normalized_items != value:
                value = normalized_items
                tool_args[key] = value
            if item_type and any(not _validate_scalar_type(item, item_type) for item in value):
                if tool_name == "batch_canvas_edits" and key == "targets":
                    return (
                        "Invalid 'targets' format for batch_canvas_edits: every item in 'targets' must be a JSON object, "
                        "not a plain string or document ID. "
                        'Correct format: [{"document_path": "src/foo.py", "operations": [{"action": "replace", "start_line": 1, "end_line": 1, "lines": ["new"]}]}]. '
                        "Use 'operations' (not 'targets') when editing a single document."
                    )
                return f"Invalid array item type for '{key}' in {tool_name}: expected {item_type}"
            min_items = property_schema.get("minItems")
            max_items = property_schema.get("maxItems")
            if tool_name == "ask_clarifying_question" and key == "questions":
                max_items = get_clarification_max_questions(get_app_settings())
            if isinstance(min_items, int) and len(value) < min_items:
                if key == "queries" and tool_name in SEARCH_QUERY_BATCHED_TOOL_NAMES:
                    pass
                else:
                    return f"Argument '{key}' in {tool_name} requires at least {min_items} items"
            if isinstance(max_items, int) and len(value) > max_items:
                if key == "queries" and tool_name in SEARCH_QUERY_BATCHED_TOOL_NAMES:
                    pass
                elif tool_name == "ask_clarifying_question" and key == "questions":
                    value = value[:max_items]
                    tool_args[key] = value
                else:
                    return f"Argument '{key}' in {tool_name} allows at most {max_items} items"
        if expected_type in {"string", "integer", "number"}:
            minimum = property_schema.get("minimum")
            maximum = property_schema.get("maximum")
            if minimum is not None and value < minimum:
                if (tool_name == "grep_fetched_content" and key in {"context_lines", "max_matches"}) or (
                    tool_name == "scroll_fetched_content" and key == "window_lines"
                ):
                    value = minimum
                    tool_args[key] = value
                else:
                    return f"Argument '{key}' in {tool_name} must be >= {minimum}"
            if maximum is not None and value > maximum:
                if (tool_name == "grep_fetched_content" and key in {"context_lines", "max_matches"}) or (
                    tool_name == "scroll_fetched_content" and key == "window_lines"
                ):
                    value = maximum
                    tool_args[key] = value
                else:
                    return f"Argument '{key}' in {tool_name} must be <= {maximum}"
        enum_values = property_schema.get("enum")
        if enum_values and value not in enum_values:
            # For canvas document `role`, silently fall back to "note" rather than
            # erroring out — the model sometimes generates valid-sounding but
            # out-of-spec role labels (e.g. "readme", "data", "diagram").
            if key == "role" and "note" in enum_values:
                tool_args[key] = "note"
            else:
                return f"Argument '{key}' in {tool_name} must be one of: {', '.join(str(item) for item in enum_values)}"
    return None


def _build_final_answer_instruction() -> dict:
    return {
        "role": "system",
        "content": (
            "[FINAL ANSWER REQUIRED]\n\n"
            "Tool budget exhausted. Respond with the best final answer using available context.\n"
            "Do not claim completion unless confirmed by tool results. "
            "If work is unfinished, say so.\n"
            "Begin your answer directly. No step-by-step recap."
        ),
    }


def _build_minimal_final_answer_instruction() -> dict:
    return {
        "role": "system",
        "content": "[FINAL ANSWER ONLY] No tools.",
    }


def _build_missing_final_answer_instruction() -> dict:
    return {
        "role": "system",
        "content": (
            "[FINAL ANSWER REQUIRED]\n\n"
            "No final answer in assistant content yet. Respond now using assistant content only."
        ),
    }


def _build_tool_execution_result_message(transcript_results: list[dict]) -> dict | None:
    if not transcript_results:
        return None

    includes_fetch_results = any(str(item.get("tool_name") or "") == "fetch_url" for item in transcript_results)
    if not includes_fetch_results:
        return None

    parts = [
        f"{TOOL_EXECUTION_RESULTS_MARKER}\n",
        "**Fetch Guidance**: Use the retrieved page content from this step as the source of truth. "
        "This guidance is step-local, not a blanket rule for later turns. "
        "If the user later asks you to verify or refresh, call fetch_url again.\n",
    ]
    for item in transcript_results:
        tool_name = str(item.get("tool_name") or "unknown")
        ok = item.get("ok", False)
        summary = str(item.get("summary") or "").strip()
        status = "OK" if ok else "FAILED"
        line = f"- **{tool_name}** [{status}]"
        if summary:
            line += f": {summary}"
        parts.append(line)
        if tool_name == "fetch_url":
            result_payload = item.get("result") if isinstance(item.get("result"), dict) else {}
            recovery_hint = _clean_tool_text(
                result_payload.get("recovery_hint") or _build_recovery_hint_for_tool(tool_name, item.get("arguments")),
                limit=220,
            )
            summary_notice = _clean_tool_text(result_payload.get("summary_notice") or "", limit=220)
            if summary_notice and result_payload.get("content_mode") in {
                "clipped_text",
                "budget_compact",
                "budget_brief",
            }:
                parts.append(f"  Recovery: {summary_notice}")
            elif recovery_hint and result_payload.get("content_mode") in {
                "clipped_text",
                "budget_compact",
                "budget_brief",
            }:
                parts.append(f"  Recovery: {recovery_hint}")

    return {"role": "user", "content": "\n".join(parts)}


def _merge_tool_execution_result_message(messages: list[dict], tool_execution_result_message: dict | None) -> None:
    if tool_execution_result_message is None:
        return

    messages[:] = [
        message
        for message in messages
        if not (
            isinstance(message, dict) and str(message.get("content") or "").startswith(TOOL_EXECUTION_RESULTS_MARKER)
        )
    ]
    messages.append(tool_execution_result_message)


def _normalize_clarification_question(raw_question: dict, index: int) -> dict | None:
    raw_question = _coerce_clarification_question_item(raw_question)
    if not isinstance(raw_question, dict):
        return None

    question_id = _sanitize_clarification_id(
        str(raw_question.get("id") or raw_question.get("key") or f"question_{index}"),
        index,
    )
    label = _sanitize_clarification_text(
        str(raw_question.get("label") or raw_question.get("question") or raw_question.get("prompt") or ""),
        limit=240,
    )

    input_type_aliases = {
        "": "",
        "text": "text",
        "string": "text",
        "free_text": "text",
        "single": "single_select",
        "select": "single_select",
        "single_select": "single_select",
        "single-choice": "single_select",
        "single_choice": "single_select",
        "multiple": "multi_select",
        "multi": "multi_select",
        "multiselect": "multi_select",
        "multi_select": "multi_select",
        "multi-choice": "multi_select",
        "multi_choice": "multi_select",
    }
    raw_input_type = str(raw_question.get("input_type") or raw_question.get("type") or "").strip().lower()
    input_type = input_type_aliases.get(raw_input_type, raw_input_type)
    if not question_id or not label:
        return None

    normalized = {
        "id": question_id,
        "label": label,
        "required": raw_question.get("required") is not False,
    }

    placeholder = _sanitize_clarification_text(str(raw_question.get("placeholder") or ""), limit=200)
    if placeholder:
        normalized["placeholder"] = placeholder[:200]

    allow_free_text = raw_question.get("allow_free_text") is True or raw_question.get("allowFreeText") is True
    if allow_free_text:
        normalized["allow_free_text"] = True

    raw_options = raw_question.get("options") if isinstance(raw_question.get("options"), list) else []
    normalized_options = []
    for option in raw_options[:10]:
        if isinstance(option, str):
            label_text = _sanitize_clarification_text(option, limit=120)
            value_text = label_text
            description = ""
        elif isinstance(option, dict):
            label_text = _sanitize_clarification_text(str(option.get("label") or option.get("value") or ""), limit=120)
            value_text = _sanitize_clarification_text(str(option.get("value") or option.get("label") or ""), limit=120)
            description = _sanitize_clarification_text(str(option.get("description") or ""), limit=200)
        else:
            continue
        if not label_text or not value_text:
            continue
        normalized_option = {
            "label": label_text[:120],
            "value": value_text[:120],
        }
        if description:
            normalized_option["description"] = description[:200]
        normalized_options.append(normalized_option)

    if input_type not in {"text", "single_select", "multi_select"}:
        input_type = "single_select" if normalized_options else "text"
    if input_type in {"single_select", "multi_select"} and not normalized_options:
        return None

    normalized["input_type"] = input_type
    if normalized_options:
        normalized["options"] = normalized_options

    raw_dependency = raw_question.get("depends_on")
    if isinstance(raw_dependency, dict):
        dependency_question_id = _sanitize_clarification_id(
            str(raw_dependency.get("question_id") or raw_dependency.get("id") or raw_dependency.get("question") or ""),
            index,
        )
        dependency_values = raw_dependency.get("values") if isinstance(raw_dependency.get("values"), list) else []
        if raw_dependency.get("value") not in (None, ""):
            dependency_values = [raw_dependency.get("value"), *dependency_values]
        normalized_dependency_values = []
        seen_dependency_values = set()
        for dependency_value in dependency_values[:10]:
            cleaned_value = _sanitize_clarification_text(str(dependency_value or ""), limit=120)
            if not cleaned_value:
                continue
            dedupe_key = cleaned_value.casefold()
            if dedupe_key in seen_dependency_values:
                continue
            seen_dependency_values.add(dedupe_key)
            normalized_dependency_values.append(cleaned_value[:120])
        if dependency_question_id and normalized_dependency_values:
            normalized["depends_on"] = {
                "question_id": dependency_question_id,
                "values": normalized_dependency_values,
            }

    return normalized


def _dedupe_clarification_question_id(question_id: str, seen_ids: set[str], index: int) -> str:
    base_id = question_id.strip()[:80] or f"question_{index}"
    candidate = base_id
    suffix = 2
    while candidate in seen_ids:
        suffix_text = f"_{suffix}"
        candidate = f"{base_id[: max(1, 80 - len(suffix_text))]}{suffix_text}"
        suffix += 1
    seen_ids.add(candidate)
    return candidate


def _normalize_clarification_payload(tool_args: dict) -> dict:
    raw_questions = tool_args.get("questions") if isinstance(tool_args.get("questions"), list) else []
    questions = []
    seen_question_ids: set[str] = set()
    question_limit = get_clarification_max_questions(get_app_settings())
    for index, raw_question in enumerate(raw_questions[:question_limit], start=1):
        normalized_question = _normalize_clarification_question(raw_question, index)
        if normalized_question is not None:
            normalized_question["id"] = _dedupe_clarification_question_id(
                str(normalized_question.get("id") or ""),
                seen_question_ids,
                index,
            )
            questions.append(normalized_question)

    if not questions:
        raise ValueError("ask_clarifying_question requires at least one valid question.")

    payload = {"questions": questions}
    intro = _sanitize_clarification_text(str(tool_args.get("intro") or ""), limit=300)
    if intro:
        payload["intro"] = intro[:300]
    submit_label = _sanitize_clarification_text(str(tool_args.get("submit_label") or ""), limit=80)
    if submit_label:
        payload["submit_label"] = submit_label[:80]
    return payload


def _build_clarification_text(payload: dict) -> str:
    return _build_pending_clarification_message_content(payload)


def _get_canvas_runtime_state(runtime_state: dict) -> dict:
    return runtime_state.setdefault("canvas", create_canvas_runtime_state())


def _get_agent_state_mutation_context(runtime_state: dict) -> tuple[int | None, int | None]:
    if not isinstance(runtime_state, dict):
        return None, None

    agent_context = runtime_state.get("agent_context")
    if not isinstance(agent_context, dict):
        return None, None

    conversation_id = int(agent_context.get("conversation_id") or 0)
    source_message_id = agent_context.get("source_message_id")
    normalized_source_message_id = int(source_message_id) if source_message_id not in (None, "") else None
    return (
        conversation_id if conversation_id > 0 else None,
        normalized_source_message_id if normalized_source_message_id and normalized_source_message_id > 0 else None,
    )


def _run_append_scratchpad(tool_args: dict, runtime_state: dict):
    notes = tool_args.get("notes") or tool_args.get("note", "")
    section = tool_args.get("section") or "notes"
    conversation_id, source_message_id = _get_agent_state_mutation_context(runtime_state)
    return append_to_scratchpad(
        notes,
        section=section,
        conversation_id=conversation_id,
        source_message_id=source_message_id,
    )


def _run_replace_scratchpad(tool_args: dict, runtime_state: dict):
    section = tool_args.get("section") or "notes"
    conversation_id, source_message_id = _get_agent_state_mutation_context(runtime_state)
    return replace_scratchpad(
        tool_args.get("new_content", ""),
        section=section,
        conversation_id=conversation_id,
        source_message_id=source_message_id,
    )


def _run_read_scratchpad(tool_args: dict, runtime_state: dict):
    del tool_args, runtime_state
    settings = get_app_settings()
    scratchpad_sections = get_all_scratchpad_sections(settings)
    section_summaries = []
    for section_id in SCRATCHPAD_SECTION_ORDER:
        content = scratchpad_sections.get(section_id, "")
        section_summaries.append(
            {
                "id": section_id,
                "title": SCRATCHPAD_SECTION_METADATA[section_id]["title"],
                "content": content,
                "note_count": count_scratchpad_notes(content),
            }
        )
    note_count = sum(section["note_count"] for section in section_summaries)
    return {
        "status": "ok",
        "scratchpad": scratchpad_sections.get("notes", ""),
        "scratchpad_sections": scratchpad_sections,
        "sections": section_summaries,
        "note_count": note_count,
    }, "Scratchpad read"


def _is_parallel_safe_tool_call(tool_name: str, tool_args: dict) -> bool:
    normalized_tool_name = _normalize_tool_name(tool_name)
    return is_tool_parallel_safe(normalized_tool_name, tool_args)


def _build_search_memory_default_key(tool_name: str, query: str) -> str:
    label = "Knowledge base" if tool_name == "search_knowledge_base" else "Tool memory"
    cleaned_query = _clean_tool_text(query, limit=88)
    if cleaned_query:
        return f"{label}: {cleaned_query}"[:120]
    return label[:120]


def _build_search_memory_value(tool_name: str, result: dict) -> str:
    label = "Knowledge base search" if tool_name == "search_knowledge_base" else "Tool memory search"
    query = _clean_tool_text(result.get("query") or "", limit=120)
    matches = result.get("matches") if isinstance(result.get("matches"), list) else []
    count = max(0, int(result.get("count") or len(matches)))
    if not matches:
        return f'{label} for "{query or "unknown query"}" found no matches.'

    fragments: list[str] = []
    for index, match in enumerate(matches[:SEARCH_MEMORY_PROMOTION_MATCH_LIMIT], start=1):
        if not isinstance(match, dict):
            continue
        source_name = _clean_tool_text(match.get("source_name") or match.get("source") or f"Match {index}", limit=64)
        source_type = _clean_tool_text(match.get("source_type") or match.get("category") or "", limit=24)
        excerpt = _clean_tool_text(match.get("text") or "", limit=SEARCH_MEMORY_PROMOTION_EXCERPT_LIMIT)
        details: list[str] = []
        if source_name:
            details.append(source_name)
        if source_type:
            details.append(f"[{source_type}]")
        similarity = match.get("similarity")
        if isinstance(similarity, (int, float)):
            details.append(f"sim {float(similarity):.2f}")
        expiry_warning = _clean_tool_text(match.get("expiry_warning") or "", limit=48)
        if expiry_warning:
            details.append(expiry_warning)
        if excerpt:
            fragment = f"{fragment}: {excerpt}" if fragment else excerpt
        if fragment:
            fragments.append(f"#{index} {fragment}")

    prefix = f'{label} for "{query or "unknown query"}" found {count} match{"es" if count != 1 else ""}.'
    if not fragments:
        return prefix
    return f"{prefix} Top results: {' | '.join(fragments)}"


def _maybe_save_search_result_to_conversation_memory(
    tool_name: str, tool_args: dict, result: dict, runtime_state: dict
) -> dict | None:
    if not _coerce_tool_bool(tool_args.get("save_to_conversation_memory")):
        return None

    if not CONVERSATION_MEMORY_ENABLED:
        return {
            "status": "disabled",
            "error": "Conversation memory is disabled.",
        }

    matches = result.get("matches") if isinstance(result.get("matches"), list) else []
    count = max(0, int(result.get("count") or len(matches)))
    if count <= 0 or not matches:
        return {
            "status": "no_matches",
            "saved": False,
        }

    agent_context = runtime_state.get("agent_context") if isinstance(runtime_state.get("agent_context"), dict) else {}
    conversation_id = int(agent_context.get("conversation_id") or 0)
    if conversation_id <= 0:
        return {
            "status": "unavailable",
            "saved": False,
            "error": "No active conversation context was provided.",
        }

    source_message_id = agent_context.get("source_message_id")
    message_id = int(source_message_id) if source_message_id not in (None, "") else None
    key = str(tool_args.get("memory_key") or "").strip() or _build_search_memory_default_key(
        tool_name, result.get("query", "")
    )
    entry = insert_conversation_memory_entry(
        conversation_id,
        "tool_result",
        key,
        _build_search_memory_value(tool_name, result),
        message_id=message_id,
        mutation_context={"source_message_id": message_id},
    )
    updated = entry.get("updated_existing") is True
    return {
        "status": "ok",
        "saved": True,
        "key": entry.get("key") or key,
        "updated_existing": updated,
    }


def _build_search_summary(base_summary: str, conversation_memory_result: dict | None) -> str:
    if not isinstance(conversation_memory_result, dict):
        return base_summary

    status = str(conversation_memory_result.get("status") or "").strip().lower()
    key = str(conversation_memory_result.get("key") or "").strip()
    if status == "ok":
        action = "updated" if conversation_memory_result.get("updated_existing") else "saved"
        if key:
            return f"{base_summary}; conversation memory {action}: {key}"
        return f"{base_summary}; conversation memory {action}"
    if status == "no_matches":
        return f"{base_summary}; conversation memory skipped: no matches"
    if status == "disabled":
        return f"{base_summary}; conversation memory disabled"
    if status == "unavailable":
        return f"{base_summary}; conversation memory unavailable"
    return base_summary


def _run_save_to_conversation_memory(tool_args: dict, runtime_state: dict):
    if not CONVERSATION_MEMORY_ENABLED:
        return {"status": "error", "error": "Conversation memory is disabled."}, "Conversation memory disabled"

    agent_context = runtime_state.get("agent_context") if isinstance(runtime_state.get("agent_context"), dict) else {}
    conversation_id = int(agent_context.get("conversation_id") or 0)
    if conversation_id <= 0:
        return {
            "status": "error",
            "error": "No active conversation context was provided.",
        }, "Conversation memory unavailable"

    source_message_id = agent_context.get("source_message_id")
    message_id = int(source_message_id) if source_message_id not in (None, "") else None
    mutation_context = {"source_message_id": message_id}

    # Batch path: entries array
    raw_entries = tool_args.get("entries")
    if isinstance(raw_entries, list) and raw_entries:
        results = []
        summaries = []
        for item in raw_entries:
            if not isinstance(item, dict):
                continue
            entry = insert_conversation_memory_entry(
                conversation_id,
                item.get("entry_type", ""),
                item.get("key", ""),
                item.get("value", ""),
                message_id=message_id,
                mutation_context=mutation_context,
            )
            updated = entry.get("updated_existing") is True
            results.append({"key": entry.get("key") or item.get("key", ""), "updated_existing": updated})
            summaries.append(f"{'updated' if updated else 'saved'}: {entry.get('key') or item.get('key', '')}")
        return {"status": "ok", "saved": results}, "Conversation memory batch — " + ", ".join(summaries)

    # Single-entry fallback (original behaviour)
    entry = insert_conversation_memory_entry(
        conversation_id,
        tool_args.get("entry_type", ""),
        tool_args.get("key", ""),
        tool_args.get("value", ""),
        message_id=message_id,
        mutation_context=mutation_context,
    )
    updated = entry.get("updated_existing") is True
    return {
        "status": "ok",
        "key": entry.get("key") or tool_args.get("key", ""),
        "updated_existing": updated,
    }, (f"Conversation memory updated: {entry['key']}" if updated else f"Conversation memory saved: {entry['key']}")


def _run_delete_conversation_memory_entry(tool_args: dict, runtime_state: dict):
    if not CONVERSATION_MEMORY_ENABLED:
        return {"status": "error", "error": "Conversation memory is disabled."}, "Conversation memory disabled"

    agent_context = runtime_state.get("agent_context") if isinstance(runtime_state.get("agent_context"), dict) else {}
    conversation_id = int(agent_context.get("conversation_id") or 0)
    if conversation_id <= 0:
        return {
            "status": "error",
            "error": "No active conversation context was provided.",
        }, "Conversation memory unavailable"

    source_message_id = agent_context.get("source_message_id")
    message_id = int(source_message_id) if source_message_id not in (None, "") else None
    entry_id = int(tool_args.get("entry_id") or 0)
    deleted = delete_conversation_memory_entry(
        entry_id,
        conversation_id,
        mutation_context={"source_message_id": message_id},
    )
    return {
        "status": "ok" if deleted else "not_found",
        "deleted": deleted,
        "entry_id": entry_id,
    }, (f"Conversation memory deleted: {entry_id}" if deleted else f"Conversation memory not found: {entry_id}")


def _run_save_to_persona_memory(tool_args: dict, runtime_state: dict):
    agent_context = runtime_state.get("agent_context") if isinstance(runtime_state.get("agent_context"), dict) else {}
    conversation_id = int(agent_context.get("conversation_id") or 0)
    if conversation_id <= 0:
        return {
            "status": "error",
            "error": "No active conversation context was provided.",
        }, "Persona memory unavailable"

    persona = get_effective_conversation_persona(conversation_id)
    if not isinstance(persona, dict) or int(persona.get("id") or 0) <= 0:
        return {
            "status": "error",
            "error": "No active persona is available for this conversation.",
        }, "Persona memory unavailable"

    source_message_id = agent_context.get("source_message_id")
    message_id = int(source_message_id) if source_message_id not in (None, "") else None
    entry = insert_persona_memory_entry(
        int(persona["id"]),
        tool_args.get("key", ""),
        tool_args.get("value", ""),
        message_id=message_id,
        mutation_context={"conversation_id": conversation_id, "source_message_id": message_id},
    )
    updated = entry.get("updated_existing") is True
    return {
        "status": "ok",
        "persona_id": int(persona["id"]),
        "key": entry.get("key") or tool_args.get("key", ""),
        "updated_existing": updated,
    }, (f"Persona memory updated: {entry['key']}" if updated else f"Persona memory saved: {entry['key']}")


def _run_delete_persona_memory_entry(tool_args: dict, runtime_state: dict):
    agent_context = runtime_state.get("agent_context") if isinstance(runtime_state.get("agent_context"), dict) else {}
    conversation_id = int(agent_context.get("conversation_id") or 0)
    if conversation_id <= 0:
        return {
            "status": "error",
            "error": "No active conversation context was provided.",
        }, "Persona memory unavailable"

    persona = get_effective_conversation_persona(conversation_id)
    if not isinstance(persona, dict) or int(persona.get("id") or 0) <= 0:
        return {
            "status": "error",
            "error": "No active persona is available for this conversation.",
        }, "Persona memory unavailable"

    source_message_id = agent_context.get("source_message_id")
    message_id = int(source_message_id) if source_message_id not in (None, "") else None
    entry_id = int(tool_args.get("entry_id") or 0)
    deleted = delete_persona_memory_entry(
        entry_id,
        int(persona["id"]),
        mutation_context={"conversation_id": conversation_id, "source_message_id": message_id},
    )
    return {
        "status": "ok" if deleted else "not_found",
        "deleted": deleted,
        "entry_id": entry_id,
        "persona_id": int(persona["id"]),
    }, (f"Persona memory deleted: {entry_id}" if deleted else f"Persona memory not found: {entry_id}")


def _run_delete_tool_result(tool_args: dict, runtime_state: dict):
    if not TOOL_MEMORY_ENABLED:
        return {"status": "error", "error": "Tool memory is disabled."}, "Tool memory disabled"

    tool_call_id = str(tool_args.get("tool_call_id") or "").strip()
    if not tool_call_id:
        return {"status": "error", "error": "tool_call_id is required."}, "delete_tool_result: missing tool_call_id"

    reason_for_deletion = str(tool_args.get("reason_for_deletion") or "").strip()
    about_the_content = str(tool_args.get("about_the_content") or "").strip()
    context_before_deletion = str(tool_args.get("context_before_deletion") or "").strip() or None

    if not about_the_content:
        return {
            "status": "error",
            "error": "about_the_content is required.",
        }, "delete_tool_result: missing about_the_content"

    agent_context = runtime_state.get("agent_context") if isinstance(runtime_state.get("agent_context"), dict) else {}
    conversation_id = int(agent_context.get("conversation_id") or 0) or None
    source_message_id = agent_context.get("source_message_id")
    message_id = int(source_message_id) if source_message_id not in (None, "") else None

    messages = runtime_state.get("_accumulated_messages")
    deleted_content_preview = ""
    tool_name = "unknown"

    if isinstance(messages, list):
        for i, msg in enumerate(messages):
            if isinstance(msg, dict) and str(msg.get("tool_call_id") or "").strip() == tool_call_id:
                content = str(msg.get("content") or "").strip()
                deleted_content_preview = content[:500] if content else ""
                if i > 0:
                    prev_msg = messages[i - 1]
                    if isinstance(prev_msg, dict) and prev_msg.get("role") == "assistant":
                        tool_calls = prev_msg.get("tool_calls")
                        if isinstance(tool_calls, list):
                            for tc in tool_calls:
                                if isinstance(tc, dict) and str(tc.get("id") or "").strip() == tool_call_id:
                                    func = tc.get("function")
                                    if isinstance(func, dict):
                                        tool_name = str(func.get("name") or "unknown").strip()
                                    break
                        if tool_name == "unknown":
                            tc_id = prev_msg.get("tool_call_id")
                            if tc_id and str(tc_id).strip() == tool_call_id:
                                tool_name = str(prev_msg.get("tool_name") or "unknown").strip()
                break

    if "deleted_tool_call_ids" not in runtime_state:
        runtime_state["deleted_tool_call_ids"] = set()
    runtime_state["deleted_tool_call_ids"].add(tool_call_id)

    entry = insert_tool_memory_entry(
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        deleted_content_preview=deleted_content_preview,
        reason_for_deletion=reason_for_deletion,
        about_the_content=about_the_content,
        context_before_deletion=context_before_deletion,
        conversation_id=conversation_id,
        message_id=message_id,
    )

    return {
        "status": "ok",
        "deleted_tool_call_id": tool_call_id,
        "tool_memory_id": entry.get("id"),
        "preview": deleted_content_preview[:200] if deleted_content_preview else "",
    }, f"Tool result deleted and stored in tool memory: {tool_call_id}"


def _run_list_tool_memory(tool_args: dict, runtime_state: dict):
    if not TOOL_MEMORY_ENABLED:
        return {"status": "error", "error": "Tool memory is disabled."}, "Tool memory disabled"

    limit = max(1, min(50, int(tool_args.get("limit") or 10)))

    agent_context = runtime_state.get("agent_context") if isinstance(runtime_state.get("agent_context"), dict) else {}
    conversation_id = int(agent_context.get("conversation_id") or 0) or None

    entries = list_tool_memory_entries(conversation_id=conversation_id, limit=limit)

    return {
        "status": "ok",
        "entries": [
            {
                "id": e.get("id"),
                "tool_name": e.get("tool_name"),
                "tool_call_id": e.get("tool_call_id"),
                "about_the_content": e.get("about_the_content"),
                "reason_for_deletion": e.get("reason_for_deletion"),
                "deleted_content_preview": e.get("deleted_content_preview"),
                "context_before_deletion": e.get("context_before_deletion"),
                "created_at": e.get("created_at"),
            }
            for e in entries
        ],
        "count": len(entries),
    }, f"Listed {len(entries)} tool memory entries"


def _run_ask_clarifying_question(tool_args: dict, runtime_state: dict):
    del runtime_state
    payload = _normalize_clarification_payload(tool_args)
    return {
        "status": "needs_user_input",
        "clarification": payload,
        "text": _build_clarification_text(payload),
    }, "Awaiting user clarification"


def _build_sub_agent_stream_entry(
    task: str,
    model: str,
    tool_trace: list[dict],
    *,
    status: str = "running",
    summary: str = "",
    error: str = "",
    timed_out: bool = False,
) -> dict:
    normalized_status = status if status in {"running", "ok", "partial", "error"} else "running"
    entry = {
        "status": normalized_status,
        "tool_trace": _normalize_sub_agent_tool_trace(tool_trace),
    }
    cleaned_task = _clean_tool_text(task, limit=400)
    full_task = _clean_tool_text(task, limit=4_000)
    if cleaned_task:
        entry["task"] = cleaned_task
    if full_task and full_task != cleaned_task:
        entry["task_full"] = full_task
    cleaned_model = _clean_tool_text(model, limit=120)
    if cleaned_model:
        entry["model"] = cleaned_model
    cleaned_summary = _clean_tool_text(summary, limit=SUB_AGENT_MAX_SUMMARY_CHARS)
    if cleaned_summary:
        entry["summary"] = cleaned_summary
    cleaned_error = _clean_tool_text(error, limit=SUB_AGENT_MAX_ERROR_CHARS)
    if cleaned_error:
        entry["error"] = cleaned_error
    if timed_out:
        entry["timed_out"] = True
    return entry


def _run_sub_agent(tool_args: dict, runtime_state: dict):
    stream = _run_sub_agent_stream(tool_args, runtime_state)
    try:
        while True:
            next(stream)
    except StopIteration as stop:
        return stop.value


def _execute_streaming_tool_with_event_buffer(tool_name: str, tool_args: dict, runtime_state: dict):
    if tool_name != "sub_agent":
        result, summary = _execute_tool(tool_name, tool_args, runtime_state=runtime_state)
        return result, summary, []

    stream = _run_sub_agent_stream(tool_args, runtime_state)
    buffered_events: list[dict] = []
    try:
        while True:
            try:
                event = next(stream)
            except StopIteration as stop:
                result, summary = stop.value
                return result, summary, buffered_events
            if isinstance(event, dict):
                buffered_events.append(event)
    finally:
        close_method = getattr(stream, "close", None)
        if callable(close_method):
            close_method()


def _run_sub_agent_stream(tool_args: dict, runtime_state: dict):
    agent_context = runtime_state.get("agent_context") if isinstance(runtime_state.get("agent_context"), dict) else {}
    _raise_if_agent_cancelled(agent_context)
    sub_agent_depth = _coerce_int_range(agent_context.get("sub_agent_depth"), 0, 0, 4)
    if sub_agent_depth >= 1:
        error = "Recursive sub-agent delegation is disabled."
        return {"status": "error", "error": error}, f"Failed: {error}"

    task = str(tool_args.get("task") or "").strip()
    if not task:
        error = "sub_agent requires a non-empty task."
        return {"status": "error", "error": error}, f"Failed: {error}"

    settings = get_app_settings()
    parent_model = str(agent_context.get("model") or "").strip()
    child_model_candidates = get_operation_model_candidates("sub_agent", settings, fallback_model_id=parent_model)
    child_max_parallel_tools = get_sub_agent_max_parallel_tools(settings)
    search_tool_query_limit = get_search_tool_query_limit(settings)
    timeout_seconds = get_sub_agent_timeout_seconds(settings)
    retry_attempts = get_sub_agent_retry_attempts(settings)
    retry_delay_seconds = get_sub_agent_retry_delay_seconds(settings)
    child_tool_names = _resolve_sub_agent_tool_names(
        settings,
        parent_tool_names=(
            agent_context.get("prompt_tool_names")
            if isinstance(agent_context.get("prompt_tool_names"), list)
            else agent_context.get("enabled_tool_names")
        ),
    )
    if not child_tool_names:
        error = "No eligible read-only tools are available for sub-agent delegation."
        return {"status": "error", "error": error}, f"Failed: {error}"

    overall_deadline = time.monotonic() + timeout_seconds
    now = datetime.now().astimezone()
    child_max_steps = _resolve_sub_agent_max_steps(settings)
    child_messages = _build_sub_agent_messages(
        task,
        child_tool_names,
        max_parallel_tools=child_max_parallel_tools,
        search_tool_query_limit=search_tool_query_limit,
        now=now,
    )
    resume_messages: list[dict] = []
    fallback_attempts: list[dict[str, str]] = []
    final_result: dict | None = None
    final_summary = ""
    aggregate_tool_trace: list[dict] = []
    aggregate_history: list[dict] = []
    aggregate_tool_results: list[dict] = []
    aggregate_reasoning = ""
    saw_timeout = False
    latest_fallback_note = ""

    for attempt_index, child_model in enumerate(child_model_candidates, start=1):
        _raise_if_agent_cancelled(agent_context)
        retry_messages = [*child_messages, *resume_messages]
        retry_count = 0

        while True:
            _raise_if_agent_cancelled(agent_context)
            attempt_messages = list(retry_messages)
            attempt_started_at = time.monotonic()
            remaining_overall_seconds = max(0.0, overall_deadline - attempt_started_at)
            if remaining_overall_seconds <= 0:
                timeout_error = f"Sub-agent timed out after {timeout_seconds} seconds."
                final_result = {
                    "status": "error",
                    "summary": timeout_error,
                    "model": _clean_tool_text(
                        child_model_candidates[max(0, attempt_index - 2)] if child_model_candidates else parent_model,
                        limit=120,
                    ),
                    "error": timeout_error,
                    "timed_out": True,
                }
                if fallback_attempts:
                    final_result["fallback_attempts"] = list(fallback_attempts)
                return final_result, f"Failed: {timeout_error}"

            remaining_candidate_count = max(0, len(child_model_candidates) - attempt_index)
            reserve_per_candidate_seconds = min(60, max(5, timeout_seconds // 4))
            reserved_fallback_seconds = min(
                max(0.0, remaining_overall_seconds - 1.0),
                float(remaining_candidate_count * reserve_per_candidate_seconds),
            )
            attempt_timeout_seconds = max(1, int(math.ceil(remaining_overall_seconds - reserved_fallback_seconds)))
            attempt_deadline = attempt_started_at + attempt_timeout_seconds

            child_tool_trace: list[dict] = []
            child_tool_trace_map: dict[str, int] = {}
            child_history: list[dict] = []
            child_tool_results: list[dict] = []
            child_answer = ""
            child_reasoning = ""
            child_errors: list[str] = []
            missing_final_answer_output = False
            timed_out = False
            retryable_model_error = False
            fallback_attempt_logged = False

            yield {
                "type": "sub_agent_trace_update",
                "entry": _build_sub_agent_stream_entry(task, child_model, aggregate_tool_trace, status="running"),
            }

            try:
                child_events = run_agent_stream(
                    attempt_messages,
                    child_model,
                    child_max_steps,
                    child_tool_names,
                    prompt_tool_names=child_tool_names,
                    max_parallel_tools=child_max_parallel_tools,
                    temperature=get_model_temperature(settings),
                    fetch_url_token_threshold=get_fetch_url_token_threshold(settings),
                    fetch_url_clip_aggressiveness=get_fetch_url_clip_aggressiveness(settings),
                    initial_canvas_documents=get_canvas_runtime_documents(runtime_state.get("canvas")),
                    initial_canvas_active_document_id=get_canvas_runtime_active_document_id(
                        runtime_state.get("canvas")
                    ),
                    canvas_prompt_max_lines=(
                        (runtime_state.get("canvas_prompt") or {}).get("max_lines")
                        if isinstance(runtime_state.get("canvas_prompt"), dict)
                        else None
                    ),
                    canvas_prompt_max_chars=(
                        (runtime_state.get("canvas_prompt") or {}).get("max_chars")
                        if isinstance(runtime_state.get("canvas_prompt"), dict)
                        else None
                    ),
                    canvas_prompt_max_tokens=(
                        (runtime_state.get("canvas_prompt") or {}).get("max_tokens")
                        if isinstance(runtime_state.get("canvas_prompt"), dict)
                        else None
                    ),
                    canvas_prompt_code_line_max_chars=(
                        (runtime_state.get("canvas_prompt") or {}).get("code_line_max_chars")
                        if isinstance(runtime_state.get("canvas_prompt"), dict)
                        else None
                    ),
                    canvas_prompt_text_line_max_chars=(
                        (runtime_state.get("canvas_prompt") or {}).get("text_line_max_chars")
                        if isinstance(runtime_state.get("canvas_prompt"), dict)
                        else None
                    ),
                    canvas_expand_max_lines=(
                        (runtime_state.get("canvas_limits") or {}).get("expand_max_lines")
                        if isinstance(runtime_state.get("canvas_limits"), dict)
                        else None
                    ),
                    canvas_scroll_window_lines=(
                        (runtime_state.get("canvas_limits") or {}).get("scroll_window_lines")
                        if isinstance(runtime_state.get("canvas_limits"), dict)
                        else None
                    ),
                    workspace_runtime_state=runtime_state.get("workspace"),
                    agent_context={
                        "sub_agent_depth": sub_agent_depth + 1,
                        "conversation_id": agent_context.get("conversation_id"),
                        "source_message_id": agent_context.get("source_message_id"),
                        "cancel_event": agent_context.get("cancel_event"),
                        "cancel_reason": agent_context.get("cancel_reason"),
                    },
                    invocation_log_sink=(
                        runtime_state.get("invocation_log_sink")
                        if isinstance(runtime_state.get("invocation_log_sink"), list)
                        else None
                    ),
                )
                try:
                    for event in child_events:
                        _raise_if_agent_cancelled(agent_context)
                        if time.monotonic() >= attempt_deadline:
                            timed_out = True
                            child_errors.append(f"Sub-agent timed out after {attempt_timeout_seconds} seconds.")
                            break

                        event_type = str(event.get("type") or "").strip()
                        if event_type == "answer_delta":
                            child_answer += str(event.get("text") or "")
                        elif event_type == "reasoning_delta":
                            child_reasoning += str(event.get("text") or "")
                        elif event_type in {"step_update", "tool_result", "tool_error"}:
                            if event_type == "tool_error":
                                internal_error_text = _clean_tool_text(
                                    event.get("error") or "", limit=SUB_AGENT_MAX_ERROR_CHARS
                                )
                                if _is_sub_agent_internal_final_answer_error(
                                    event.get("tool") or "", internal_error_text
                                ):
                                    missing_final_answer_output = True
                                    continue
                            _upsert_sub_agent_tool_trace(child_tool_trace, child_tool_trace_map, event)
                            yield {
                                "type": "sub_agent_trace_update",
                                "entry": _build_sub_agent_stream_entry(
                                    task,
                                    child_model,
                                    [*aggregate_tool_trace, *_normalize_sub_agent_tool_trace(child_tool_trace)],
                                    status="running",
                                ),
                            }
                            if event_type == "tool_error":
                                error_text = _clean_tool_text(event.get("error") or "", limit=SUB_AGENT_MAX_ERROR_CHARS)
                                if error_text:
                                    if str(event.get("tool") or "").strip() == "api" and _is_retryable_model_error(
                                        error_text
                                    ) not in ("none", ""):
                                        retryable_model_error = True
                                        break
                                    child_errors.append(error_text)
                        elif event_type == "tool_capture":
                            child_tool_results = (
                                event.get("tool_results") if isinstance(event.get("tool_results"), list) else []
                            )
                        elif event_type == "tool_history":
                            raw_messages = event.get("messages") if isinstance(event.get("messages"), list) else []
                            for message in raw_messages:
                                normalized_message = _normalize_sub_agent_history_message(message)
                                if (
                                    normalized_message is not None
                                    and len(child_history) < SUB_AGENT_MAX_TRANSCRIPT_MESSAGES
                                ):
                                    child_history.append(normalized_message)
                finally:
                    close_method = getattr(child_events, "close", None)
                    if callable(close_method):
                        close_method()
            except Exception as exc:
                error_text = _clean_tool_text(str(exc), limit=SUB_AGENT_MAX_ERROR_CHARS)
                if _is_retryable_model_error(error_text) not in ("none", ""):
                    retryable_model_error = True
                else:
                    child_errors.append(error_text)

            child_answer = _clean_tool_text(child_answer, limit=SUB_AGENT_MAX_SUMMARY_CHARS)
            if _is_sub_agent_placeholder_answer(child_answer):
                missing_final_answer_output = True
                child_answer = ""
            child_reasoning = _clean_tool_text(child_reasoning, limit=SUB_AGENT_MAX_REASONING_CHARS)
            if child_answer:
                child_history.append({"role": "assistant", "content": child_answer})
            normalized_tool_trace = _normalize_sub_agent_tool_trace(child_tool_trace)
            aggregate_tool_trace = _append_sub_agent_tool_trace_entries(aggregate_tool_trace, normalized_tool_trace)
            aggregate_history = _append_sub_agent_history_entries(aggregate_history, child_history)
            aggregate_tool_results = _append_sub_agent_tool_results(aggregate_tool_results, child_tool_results)
            aggregate_reasoning = _combine_sub_agent_reasoning(aggregate_reasoning, child_reasoning)
            if timed_out:
                saw_timeout = True
            trace_error_text = next(
                (
                    _clean_tool_text(
                        entry.get("summary") or f"{entry.get('tool_name', 'tool')} failed.",
                        limit=SUB_AGENT_MAX_ERROR_CHARS,
                    )
                    for entry in reversed(normalized_tool_trace)
                    if isinstance(entry, dict) and entry.get("state") == "error"
                ),
                "",
            )
            if trace_error_text and trace_error_text not in child_errors:
                child_errors.append(trace_error_text)

            error_text = _clean_tool_text(child_errors[-1], limit=SUB_AGENT_MAX_ERROR_CHARS) if child_errors else ""

            artifacts = _build_sub_agent_artifacts(aggregate_history, aggregate_tool_results)
            summary_text = child_answer or error_text or "Sub-agent finished without a final summary."
            missing_final_answer_state = missing_final_answer_output and not child_answer
            if missing_final_answer_state:
                summary_text = _build_sub_agent_missing_final_answer_summary(
                    aggregate_tool_trace,
                    artifacts,
                    aggregate_history,
                )

            has_partial_output = bool(child_answer or aggregate_tool_trace or artifacts or aggregate_history)
            result_status = "ok"
            if timed_out or error_text or retryable_model_error or missing_final_answer_state:
                result_status = "partial" if has_partial_output else "error"
            if missing_final_answer_state and not has_partial_output and not error_text:
                error_text = "The delegated model did not return a final answer."

            if (
                (timed_out or retryable_model_error or missing_final_answer_state)
                and retry_count < retry_attempts
                and time.monotonic() < overall_deadline
            ):
                retry_reason = (
                    "a timeout"
                    if timed_out
                    else "a missing final answer"
                    if missing_final_answer_state
                    else "a model error"
                )
                resume_messages.extend(_build_sub_agent_retry_messages(aggregate_history))
                resume_messages.append(_build_sub_agent_resume_message(child_model, retry_reason))
                retry_count += 1
                sleep_for = min(float(retry_delay_seconds), max(0.0, overall_deadline - time.monotonic()))
                if sleep_for > 0:
                    _sleep_with_agent_cancel(agent_context, sleep_for)
                retry_messages = [*child_messages, *resume_messages]
                continue

            has_more_candidates = attempt_index < len(child_model_candidates)
            fallback_continues = has_more_candidates and result_status != "ok"
            fallback_note = ""
            if fallback_continues:
                next_model = _clean_tool_text(child_model_candidates[attempt_index], limit=120)
                reason_label = (
                    "timeout" if timed_out else "missing final answer" if missing_final_answer_state else "model error"
                )
                prompt_reason_label = (
                    "a timeout"
                    if timed_out
                    else "a missing final answer"
                    if missing_final_answer_state
                    else "a model error"
                )
                fallback_note = f"Continued on {next_model} after {reason_label}."
                latest_fallback_note = fallback_note
                if not fallback_attempt_logged:
                    fallback_attempts.append(
                        {
                            "model": child_model,
                            "error": error_text
                            or (
                                "The delegated model did not return a final answer."
                                if missing_final_answer_state
                                else ""
                            )
                            or fallback_note
                            or "Retryable model failure.",
                        }
                    )
                    fallback_attempt_logged = True
                resume_messages.extend(_build_sub_agent_retry_messages(aggregate_history))
                resume_messages.append(_build_sub_agent_resume_message(child_model, prompt_reason_label))
                result_status = "partial"

            if fallback_continues and not child_answer:
                summary_text = fallback_note or "Sub-agent paused before completion."
            cleaned_task = _clean_tool_text(task, limit=400)
            full_task = _clean_tool_text(task, limit=4_000)
            trace_entry = {
                "status": result_status,
                "summary": summary_text,
                "model": _clean_tool_text(child_model, limit=120),
                "tool_trace": aggregate_tool_trace,
                "artifacts": artifacts,
                "messages": aggregate_history[:SUB_AGENT_MAX_TRANSCRIPT_MESSAGES],
            }
            if cleaned_task:
                trace_entry["task"] = cleaned_task
            if full_task and full_task != cleaned_task:
                trace_entry["task_full"] = full_task
            if fallback_attempts:
                trace_entry["fallback_attempts"] = list(fallback_attempts)
            if fallback_note or latest_fallback_note:
                trace_entry["fallback_note"] = fallback_note or latest_fallback_note
            if aggregate_reasoning:
                trace_entry["reasoning"] = aggregate_reasoning
            if timed_out or saw_timeout:
                trace_entry["timed_out"] = True
            if fallback_continues:
                error_text = ""
            if error_text:
                trace_entry["error"] = error_text

            final_result = {
                "status": result_status,
                "summary": summary_text,
                "tool_trace": aggregate_tool_trace,
            }
            if artifacts:
                final_result["artifacts"] = artifacts
            if fallback_attempts:
                final_result["fallback_attempts"] = list(fallback_attempts)
            if error_text:
                final_result["error"] = error_text
            if timed_out or saw_timeout:
                final_result["timed_out"] = True
            if fallback_note or latest_fallback_note:
                final_result["fallback_note"] = fallback_note or latest_fallback_note
            final_result["model"] = _clean_tool_text(child_model, limit=120)
            final_summary = (
                f"Sub-agent continued: {_clean_tool_text(final_result['summary'], limit=180)}"
                if fallback_continues
                else f"Failed: {error_text or 'Sub-agent could not complete the delegated task.'}"
                if result_status == "error"
                else f"Sub-agent partial: {_clean_tool_text(final_result['summary'], limit=180)}"
                if result_status == "partial"
                else f"Sub-agent completed: {_clean_tool_text(final_result['summary'], limit=180)}"
            )
            if result_status == "ok":
                _append_sub_agent_trace(runtime_state, trace_entry)
                yield {"type": "sub_agent_trace_update", "entry": trace_entry}
                return final_result, final_summary

            if fallback_continues:
                break
            _append_sub_agent_trace(runtime_state, trace_entry)
            yield {"type": "sub_agent_trace_update", "entry": trace_entry}
            return final_result, final_summary

    if final_result is None:
        final_error = (
            fallback_attempts[-1]["error"] if fallback_attempts else "Sub-agent could not complete the delegated task."
        )
        final_result = {
            "status": "error",
            "summary": final_error,
            "model": _clean_tool_text(
                child_model_candidates[-1] if child_model_candidates else parent_model, limit=120
            ),
            "error": final_error,
        }
        if fallback_attempts:
            final_result["fallback_attempts"] = list(fallback_attempts)
        return final_result, f"Failed: {final_error}"

    return final_result, final_summary


def _run_image_explain(tool_args: dict, runtime_state: dict):
    image_id = str(tool_args.get("image_id") or "").strip()
    conversation_id = tool_args.get("conversation_id")
    question = str(tool_args.get("question") or "").strip()
    try:
        normalized_conversation_id = int(conversation_id)
    except (TypeError, ValueError):
        return {
            "status": "error",
            "error": "conversation_id must be an integer.",
        }, "Invalid conversation id"

    asset, image_bytes = read_image_asset_bytes(image_id, conversation_id=normalized_conversation_id)
    if not asset or not image_bytes:
        return {
            "status": "missing_image",
            "error": "Stored image not found. Ask the user to re-upload the image.",
            "image_id": image_id,
            "conversation_id": normalized_conversation_id,
        }, "Stored image not found"

    answer = answer_image_question(
        image_bytes,
        asset.get("mime_type", ""),
        question,
        initial_analysis=asset.get("initial_analysis"),
        settings=get_app_settings(),
        model_id=str(((runtime_state.get("agent_context") or {}).get("model") or "")).strip(),
        conversation_id=normalized_conversation_id,
        source_message_id=int(((runtime_state.get("agent_context") or {}).get("source_message_id") or 0)) or None,
    )
    return {
        "status": "ok",
        "image_id": image_id,
        "conversation_id": normalized_conversation_id,
        "answer": answer,
    }, "Image question answered"


def _run_transcribe_youtube_video(tool_args: dict, runtime_state: dict):
    del runtime_state
    raw_url = str(tool_args.get("url") or "").strip()
    if not raw_url:
        return {"status": "error", "error": "A YouTube URL is required."}, "Failed: missing YouTube URL"

    try:
        normalized_url = normalize_youtube_url(raw_url)
        transcript_payload = transcribe_youtube_video(normalized_url)
        transcript_text = str(transcript_payload.get("transcript_text") or "").strip()
        if not transcript_text:
            return {
                "status": "error",
                "error": "A readable speech transcript could not be extracted from the video.",
            }, "Failed: transcript extraction"

        context_block, transcript_truncated = build_video_transcript_context_block(
            str(transcript_payload.get("title") or "YouTube video").strip(),
            transcript_text,
            source_url=str(transcript_payload.get("source_url") or normalized_url).strip(),
            transcript_language=str(transcript_payload.get("transcript_language") or "").strip(),
            duration_seconds=transcript_payload.get("duration_seconds"),
        )
        result = {
            "status": "ok",
            "platform": "youtube",
            "source_url": str(transcript_payload.get("source_url") or normalized_url).strip(),
            "source_video_id": str(transcript_payload.get("source_video_id") or "").strip(),
            "title": str(transcript_payload.get("title") or "YouTube video").strip(),
            "duration_seconds": transcript_payload.get("duration_seconds"),
            "transcript_language": str(transcript_payload.get("transcript_language") or "").strip(),
            "transcript_text": transcript_text,
            "transcript_context_block": context_block,
            "transcript_truncated": transcript_truncated,
        }
        summary_title = _clean_tool_text(result.get("title") or "YouTube video", limit=80)
        summary = f"YouTube transcript ready: {summary_title}"
        if transcript_truncated:
            summary += " (truncated)"
        return result, summary
    except Exception as exc:
        error_text = _format_tool_execution_error(exc)
        return {"status": "error", "error": error_text}, f"Failed: {error_text}"


def _run_search_knowledge_base(tool_args: dict, runtime_state: dict):
    result = search_knowledge_base_tool(
        tool_args.get("query", ""),
        category=tool_args.get("category"),
        top_k=tool_args.get("top_k", RAG_SEARCH_DEFAULT_TOP_K),
        allowed_source_types=get_rag_source_types(),
        min_similarity=tool_args.get("min_similarity"),
    )
    conversation_memory_result = _maybe_save_search_result_to_conversation_memory(
        "search_knowledge_base",
        tool_args,
        result,
        runtime_state,
    )
    if conversation_memory_result is not None:
        result = dict(result)
        result["conversation_memory"] = conversation_memory_result
    return result, _build_search_summary(f"{result.get('count', 0)} knowledge chunks found", conversation_memory_result)


def _run_expand_truncated_tool_result(tool_args: dict, runtime_state: dict):
    del runtime_state
    message_id = str(tool_args.get("message_id") or "").strip()
    tool_call_id = str(tool_args.get("tool_call_id") or "").strip()
    if not message_id or not tool_call_id:
        return {
            "error": "message_id and tool_call_id are required"
        }, "expand_truncated_tool_result skipped: missing parameters"
    result_text = get_message_tool_result_content(int(message_id), tool_call_id)
    if result_text is None:
        return {"error": "Tool result not found or access denied."}, "expand_truncated_tool_result: not found"
    return {"content": result_text}, f"expand_truncated_tool_result: retrieved {len(result_text)} characters"


def _run_search_web(tool_args: dict, runtime_state: dict):
    del runtime_state
    query_limit = get_search_tool_query_limit(get_app_settings())
    query_batches = list(_iter_search_query_batches(_get_search_tool_queries(tool_args), batch_size=query_limit))
    if not query_batches:
        return [], "search_web skipped: no queries provided"
    result = _merge_batched_search_results([search_web_tool(batch) for batch in query_batches])
    ok_count = sum(1 for row in result if "error" not in row)
    return result, f"{ok_count} web results found"


def _run_search_news_ddgs(tool_args: dict, runtime_state: dict):
    del runtime_state
    query_limit = get_search_tool_query_limit(get_app_settings())
    query_batches = list(_iter_search_query_batches(_get_search_tool_queries(tool_args), batch_size=query_limit))
    if not query_batches:
        return [], "search_news_ddgs skipped: no queries provided"
    result = _merge_batched_search_results(
        [
            search_news_ddgs_tool(
                batch,
                lang=tool_args.get("lang", "tr"),
                when=tool_args.get("when"),
            )
            for batch in query_batches
        ]
    )
    ok_count = sum(1 for row in result if "error" not in row)
    return result, f"{ok_count} news articles found"


def _run_search_news_google(tool_args: dict, runtime_state: dict):
    del runtime_state
    query_limit = get_search_tool_query_limit(get_app_settings())
    query_batches = list(_iter_search_query_batches(_get_search_tool_queries(tool_args), batch_size=query_limit))
    if not query_batches:
        return [], "search_news_google skipped: no queries provided"
    result = _merge_batched_search_results(
        [
            search_news_google_tool(
                batch,
                lang=tool_args.get("lang", "tr"),
                when=tool_args.get("when"),
            )
            for batch in query_batches
        ]
    )
    ok_count = sum(1 for row in result if "error" not in row)
    return result, f"{ok_count} news articles found"


def _run_fetch_url(tool_args: dict, runtime_state: dict):
    del runtime_state
    result = fetch_url_tool(tool_args.get("url", ""))
    return result, _summarize_fetch_result(result, tool_args.get("url", ""))


def _run_scroll_fetched_content(tool_args: dict, runtime_state: dict):
    del runtime_state
    result = scroll_fetched_content_tool(
        url=tool_args.get("url", ""),
        start_line=tool_args.get("start_line", 1),
        window_lines=tool_args.get("window_lines", 120),
        refresh_if_missing=tool_args.get("refresh_if_missing", True),
    )
    if result.get("error"):
        summary = f"scroll_fetched_content error: {_clean_tool_text(result['error'], limit=120)}"
    else:
        target_label = _clean_tool_text(
            result.get("title") or result.get("url") or tool_args.get("url") or "page", limit=80
        )
        summary = f"scroll_fetched_content: {target_label} {result.get('start_line')}-{result.get('end_line_actual')}"
    return result, summary


def _run_fetch_url_summarized(tool_args: dict, runtime_state: dict):
    url = str(tool_args.get("url") or "").strip()
    focus = str(tool_args.get("focus") or "").strip()
    result = fetch_url_tool(url)
    if result.get("error") or not _clean_tool_text(result.get("content") or ""):
        error_result = {
            "url": str(result.get("url") or url).strip(),
            "title": str(result.get("title") or "").strip(),
            "summary": _summarize_fetch_result(result, url),
        }
        if result.get("error"):
            error_result["error"] = _clean_tool_text(result.get("error") or "", limit=400)
        if focus:
            error_result["focus"] = _clean_tool_text(focus, limit=600)
        return error_result, _summarize_fetch_result(result, url)

    agent_context = runtime_state.get("agent_context") if isinstance(runtime_state.get("agent_context"), dict) else {}
    parent_model = str(agent_context.get("model") or "").strip()
    invocation_log_sink = (
        runtime_state.get("invocation_log_sink") if isinstance(runtime_state.get("invocation_log_sink"), list) else None
    )
    return _summarize_fetched_page_result(
        result,
        focus,
        parent_model=parent_model,
        agent_context=agent_context,
        invocation_log_sink=invocation_log_sink,
    )


def _run_grep_fetched_content(tool_args: dict, runtime_state: dict):
    del runtime_state
    result = grep_fetched_content_tool(
        url=tool_args.get("url", ""),
        pattern=tool_args.get("pattern", ""),
        context_lines=tool_args.get("context_lines", 2),
        max_matches=tool_args.get("max_matches", 20),
        refresh_if_missing=tool_args.get("refresh_if_missing", True),
    )
    match_count = result.get("match_count", 0)
    if result.get("error"):
        summary = f"grep_fetched_content error: {_clean_tool_text(result['error'], limit=120)}"
    elif match_count == 0:
        summary = (
            f"grep_fetched_content: no matches for pattern '{_clean_tool_text(tool_args.get('pattern', ''), limit=60)}'"
        )
    else:
        summary = f"grep_fetched_content: {match_count} match(es) for pattern '{_clean_tool_text(tool_args.get('pattern', ''), limit=60)}'"
    return result, summary


def _run_create_canvas_document(tool_args: dict, runtime_state: dict):
    canvas_state = _get_canvas_runtime_state(runtime_state)
    document = create_canvas_document(
        canvas_state,
        title=tool_args.get("title", "Canvas"),
        content=tool_args.get("content", ""),
        format_name=tool_args.get("format", "markdown"),
        language_name=tool_args.get("language"),
        path=tool_args.get("path"),
        role=tool_args.get("role"),
        summary=tool_args.get("summary"),
        imports=tool_args.get("imports"),
        exports=tool_args.get("exports"),
        symbols=tool_args.get("symbols"),
        dependencies=tool_args.get("dependencies"),
        project_id=tool_args.get("project_id"),
        workspace_id=tool_args.get("workspace_id"),
    )
    return build_canvas_tool_result(document, action="created"), f"Canvas created: {document['title']}"


def _run_expand_canvas_document(tool_args: dict, runtime_state: dict):
    canvas_state = _get_canvas_runtime_state(runtime_state)
    skip_result = _build_already_visible_canvas_expand_result(tool_args, runtime_state)
    if skip_result is not None:
        target_label = str(skip_result.get("document_path") or skip_result.get("title") or "Canvas").strip()
        return skip_result, f"Canvas already fully visible: {target_label}"
    canvas_limits = runtime_state.get("canvas_limits") if isinstance(runtime_state.get("canvas_limits"), dict) else {}
    expand_max_lines = int(canvas_limits.get("expand_max_lines") or 0) or None
    result = build_canvas_document_context_result(
        canvas_state,
        document_id=tool_args.get("document_id"),
        document_path=tool_args.get("document_path"),
        max_lines=expand_max_lines,
        max_chars=scale_canvas_char_limit(expand_max_lines, default_lines=800, default_chars=20_000)
        if expand_max_lines
        else None,
    )
    target_label = str(result.get("document_path") or result.get("title") or "Canvas").strip()
    return result, f"Canvas expanded: {target_label}"


def _run_batch_read_canvas_documents(tool_args: dict, runtime_state: dict):
    canvas_state = _get_canvas_runtime_state(runtime_state)
    result = batch_read_canvas_documents(canvas_state, tool_args.get("documents") or [])
    return (
        result,
        f"Canvas batch read returned {result.get('success_count', 0)}/{result.get('requested_count', 0)} document(s)",
    )


def _run_scroll_canvas_document(tool_args: dict, runtime_state: dict):
    canvas_state = _get_canvas_runtime_state(runtime_state)
    canvas_limits = runtime_state.get("canvas_limits") if isinstance(runtime_state.get("canvas_limits"), dict) else {}
    scroll_window_lines = int(canvas_limits.get("scroll_window_lines") or 0) or 200
    result = scroll_canvas_document(
        canvas_state,
        start_line=int(tool_args.get("start_line") or 0),
        end_line=int(tool_args.get("end_line") or 0),
        document_id=tool_args.get("document_id"),
        document_path=tool_args.get("document_path"),
        max_window_lines=scroll_window_lines,
    )
    target_label = str(result.get("document_path") or result.get("title") or "Canvas").strip()
    return result, f"Canvas scrolled: {target_label} {result.get('start_line')}-{result.get('end_line_actual')}"


def _run_search_canvas_document(tool_args: dict, runtime_state: dict):
    canvas_state = _get_canvas_runtime_state(runtime_state)
    result = search_canvas_document(
        canvas_state,
        tool_args.get("query", ""),
        document_id=tool_args.get("document_id"),
        document_path=tool_args.get("document_path"),
        all_documents=tool_args.get("all_documents") is True,
        is_regex=tool_args.get("is_regex") is True,
        case_sensitive=tool_args.get("case_sensitive") is True,
        context_lines=tool_args.get("context_lines") or 0,
        offset=tool_args.get("offset") or 0,
        max_results=tool_args.get("max_results") or 10,
    )
    if result.get("all_documents"):
        scope_label = "all canvas documents"
    else:
        first_match = (result.get("matches") or [{}])[0]
        scope_label = str(first_match.get("document_path") or first_match.get("title") or "active canvas").strip()
    return (
        result,
        f"{result.get('returned_count', len(result.get('matches') or []))} canvas matches found in {scope_label}",
    )


def _run_validate_canvas_document(tool_args: dict, runtime_state: dict):
    canvas_state = _get_canvas_runtime_state(runtime_state)
    result = validate_canvas_document(
        canvas_state,
        document_id=tool_args.get("document_id"),
        document_path=tool_args.get("document_path"),
        validator=tool_args.get("validator"),
    )
    issue_count = int(result.get("issue_count") or 0)
    if result.get("is_valid"):
        return result, f"Canvas validation passed for {result.get('title') or 'Canvas'}"
    return result, f"Canvas validation found {issue_count} issue(s) in {result.get('title') or 'Canvas'}"


def _get_workspace_runtime_state(runtime_state: dict) -> dict:
    return runtime_state.setdefault("workspace", create_workspace_runtime_state())


def _run_create_directory(tool_args: dict, runtime_state: dict):
    result = workspace_create_directory(_get_workspace_runtime_state(runtime_state), tool_args.get("path", ""))
    return result, f"Directory created: {result.get('path', '')}"


def _run_create_file(tool_args: dict, runtime_state: dict):
    result = workspace_create_file(
        _get_workspace_runtime_state(runtime_state),
        tool_args.get("path", ""),
        tool_args.get("content", ""),
    )
    return result, f"File created: {result.get('path', '')}"


def _run_update_file(tool_args: dict, runtime_state: dict):
    result = workspace_update_file(
        _get_workspace_runtime_state(runtime_state),
        tool_args.get("path", ""),
        tool_args.get("content", ""),
    )
    return result, f"File updated: {result.get('path', '')}"


def _run_read_file(tool_args: dict, runtime_state: dict):
    result = workspace_read_file(
        _get_workspace_runtime_state(runtime_state),
        tool_args.get("path", ""),
        start_line=tool_args.get("start_line", 1),
        end_line=tool_args.get("end_line"),
    )
    return result, f"File read: {result.get('path', '')}"


def _run_list_dir(tool_args: dict, runtime_state: dict):
    result = workspace_list_dir(_get_workspace_runtime_state(runtime_state), tool_args.get("path"))
    return result, f"Directory listed: {result.get('path', '')}"


def _run_search_files(tool_args: dict, runtime_state: dict):
    result = workspace_search_files(
        _get_workspace_runtime_state(runtime_state),
        tool_args.get("query", ""),
        path_prefix=tool_args.get("path_prefix"),
        search_content=tool_args.get("search_content") is True,
    )
    return result, f"{len(result.get('matches') or [])} workspace matches found"


def _run_write_project_tree(tool_args: dict, runtime_state: dict):
    result = write_project_tree(
        _get_workspace_runtime_state(runtime_state),
        directories=tool_args.get("directories") or [],
        files=tool_args.get("files") or [],
        confirm=tool_args.get("confirm") is True,
    )
    return result, f"Project tree write: {len(result.get('files') or [])} files"


def _run_validate_project_workspace(tool_args: dict, runtime_state: dict):
    result = validate_project_workspace(
        _get_workspace_runtime_state(runtime_state),
        path=tool_args.get("path"),
    )
    return result, f"Workspace validation: {result.get('status', 'ok')}"


def _run_import_github_repository_to_canvas(tool_args: dict, runtime_state: dict):
    url = str(tool_args.get("url") or "").strip()
    if not url:
        error = "GitHub repository URL is required."
        return {"status": "error", "error": error}, error

    canvas_state = _get_canvas_runtime_state(runtime_state)
    result = import_github_repository_into_canvas(canvas_state, url)
    imported_count = int(result.get("imported_count") or 0)
    created_count = int(result.get("created_count") or 0)
    updated_count = int(result.get("updated_count") or 0)
    primary_document_path = str(result.get("primary_document_path") or "").strip()
    summary = f"GitHub repo imported: {imported_count} file(s) ({created_count} created, {updated_count} updated)"
    if primary_document_path:
        summary += f"; active file: {primary_document_path}"
    return result, summary


def _run_preview_github_import_to_canvas(tool_args: dict, runtime_state: dict):
    del runtime_state
    url = str(tool_args.get("url") or "").strip()
    if not url:
        error = "GitHub repository URL is required."
        return {"status": "error", "error": error}, error

    result = preview_github_repository_for_canvas(url)
    total_files = int(result.get("total_files") or 0)
    repo_label = f"{result.get('owner')}/{result.get('repo')}@{result.get('ref')}"
    summary = f"Preview: {repo_label} — {total_files} file(s) ready to import"
    return result, summary


def _run_rewrite_canvas_document(tool_args: dict, runtime_state: dict):
    canvas_state = _get_canvas_runtime_state(runtime_state)
    document = rewrite_canvas_document(
        canvas_state,
        content=tool_args.get("content", ""),
        document_id=tool_args.get("document_id"),
        document_path=tool_args.get("document_path"),
        title=tool_args.get("title"),
        format_name=tool_args.get("format"),
        language_name=tool_args.get("language"),
        path=tool_args.get("path"),
        role=tool_args.get("role"),
        summary=tool_args.get("summary"),
        imports=tool_args.get("imports"),
        exports=tool_args.get("exports"),
        symbols=tool_args.get("symbols"),
        dependencies=tool_args.get("dependencies"),
        project_id=tool_args.get("project_id"),
        workspace_id=tool_args.get("workspace_id"),
    )
    clear_canvas_viewport(
        canvas_state,
        document_id=document.get("id"),
        document_path=document.get("path"),
    )
    return build_canvas_tool_result(document, action="rewritten"), f"Canvas updated: {document['title']}"


def _run_replace_canvas_lines(tool_args: dict, runtime_state: dict):
    canvas_state = _get_canvas_runtime_state(runtime_state)
    start_line = int(tool_args.get("start_line") or 0)
    replacement_lines = tool_args.get("lines") or []
    expected_start_line, expected_lines = _build_canvas_expected_context(
        canvas_state,
        document_id=tool_args.get("document_id"),
        document_path=tool_args.get("document_path"),
        start_line=start_line,
        end_line=int(tool_args.get("end_line") or 0),
        mode="replace",
    )
    document = replace_canvas_lines(
        canvas_state,
        start_line=start_line,
        end_line=int(tool_args.get("end_line") or 0),
        lines=replacement_lines,
        document_id=tool_args.get("document_id"),
        document_path=tool_args.get("document_path"),
        expected_lines=tool_args.get("expected_lines"),
        expected_start_line=tool_args.get("expected_start_line"),
    )
    edit_end = start_line + len(replacement_lines) - 1 if replacement_lines else start_line
    result = build_canvas_tool_result(
        document,
        action="lines_replaced",
        edit_start_line=start_line,
        edit_end_line=max(start_line, edit_end),
        expected_start_line=expected_start_line,
        expected_lines=expected_lines,
    )
    clear_overlapping_canvas_viewports(
        canvas_state,
        document_id=document.get("id"),
        document_path=document.get("path"),
        edit_start_line=start_line,
        edit_end_line=max(start_line, edit_end),
    )
    return result, f"Canvas lines replaced in {document['title']}"


def _run_insert_canvas_lines(tool_args: dict, runtime_state: dict):
    canvas_state = _get_canvas_runtime_state(runtime_state)
    after_line = int(tool_args.get("after_line") or 0)
    insertion_lines = tool_args.get("lines") or []
    expected_start_line, expected_lines = _build_canvas_expected_context(
        canvas_state,
        document_id=tool_args.get("document_id"),
        document_path=tool_args.get("document_path"),
        after_line=after_line,
        mode="insert",
    )
    document = insert_canvas_lines(
        canvas_state,
        after_line=after_line,
        lines=insertion_lines,
        document_id=tool_args.get("document_id"),
        document_path=tool_args.get("document_path"),
        expected_lines=tool_args.get("expected_lines"),
        expected_start_line=tool_args.get("expected_start_line"),
    )
    edit_start = after_line + 1
    edit_end = after_line + len(insertion_lines)
    result = build_canvas_tool_result(
        document,
        action="lines_inserted",
        edit_start_line=edit_start,
        edit_end_line=max(edit_start, edit_end),
        expected_start_line=expected_start_line,
        expected_lines=expected_lines,
    )
    clear_overlapping_canvas_viewports(
        canvas_state,
        document_id=document.get("id"),
        document_path=document.get("path"),
        edit_start_line=edit_start,
        edit_end_line=max(edit_start, edit_end),
    )
    return result, f"Canvas lines inserted in {document['title']}"


def _run_delete_canvas_lines(tool_args: dict, runtime_state: dict):
    canvas_state = _get_canvas_runtime_state(runtime_state)
    start_line = int(tool_args.get("start_line") or 0)
    expected_start_line, expected_lines = _build_canvas_expected_context(
        canvas_state,
        document_id=tool_args.get("document_id"),
        document_path=tool_args.get("document_path"),
        start_line=start_line,
        end_line=int(tool_args.get("end_line") or 0),
        mode="delete",
    )
    document = delete_canvas_lines(
        canvas_state,
        start_line=start_line,
        end_line=int(tool_args.get("end_line") or 0),
        document_id=tool_args.get("document_id"),
        document_path=tool_args.get("document_path"),
        expected_lines=tool_args.get("expected_lines"),
        expected_start_line=tool_args.get("expected_start_line"),
    )
    # Show context around the deletion point so the model can verify placement.
    result = build_canvas_tool_result(
        document,
        action="lines_deleted",
        edit_start_line=start_line,
        edit_end_line=start_line,
        expected_start_line=expected_start_line,
        expected_lines=expected_lines,
    )
    clear_overlapping_canvas_viewports(
        canvas_state,
        document_id=document.get("id"),
        document_path=document.get("path"),
        edit_start_line=start_line,
        edit_end_line=int(tool_args.get("end_line") or 0),
    )
    return result, f"Canvas lines deleted in {document['title']}"


def _run_batch_canvas_edits(tool_args: dict, runtime_state: dict):
    canvas_state = _get_canvas_runtime_state(runtime_state)
    batch_result = batch_canvas_edits(
        canvas_state,
        tool_args.get("operations") or [],
        document_id=tool_args.get("document_id"),
        document_path=tool_args.get("document_path"),
        atomic=tool_args.get("atomic") is True,
        targets=tool_args.get("targets"),
    )
    if batch_result.get("action") == "batch_multi_edited":
        for entry in batch_result.get("results") or []:
            edit_start_line = entry.get("edit_start_line")
            edit_end_line = entry.get("edit_end_line")
            if edit_start_line is None or edit_end_line is None:
                continue
            clear_overlapping_canvas_viewports(
                canvas_state,
                document_id=entry.get("document_id"),
                document_path=entry.get("document_path"),
                edit_start_line=int(edit_start_line),
                edit_end_line=int(edit_end_line),
            )
        return {
            "status": "ok",
            "action": "lines_batch_multi_edited",
            "results": batch_result.get("results") or [],
            "target_count": batch_result.get("target_count", 0),
            "total_applied_count": batch_result.get("total_applied_count", 0),
        }, f"Canvas batch edit applied across {batch_result.get('target_count', 0)} documents"

    changed_ranges = batch_result.get("changed_ranges") or []
    edit_start_line = None
    edit_end_line = None
    if changed_ranges:
        edit_start_line = min(
            int(entry.get("edit_start_line") or 0) for entry in changed_ranges if entry.get("edit_start_line")
        )
        edit_end_line = max(
            int(entry.get("edit_end_line") or 0) for entry in changed_ranges if entry.get("edit_end_line")
        )
    result = build_canvas_tool_result(
        batch_result["document"],
        action="lines_batch_edited",
        edit_start_line=edit_start_line,
        edit_end_line=edit_end_line,
    )
    result["applied_count"] = batch_result.get("applied_count", 0)
    result["operation_count"] = batch_result.get("operation_count", 0)
    result["changed_ranges"] = changed_ranges
    if edit_start_line is not None and edit_end_line is not None:
        clear_overlapping_canvas_viewports(
            canvas_state,
            document_id=batch_result["document"].get("id"),
            document_path=batch_result["document"].get("path"),
            edit_start_line=edit_start_line,
            edit_end_line=edit_end_line,
        )
    return result, f"Canvas batch edit applied in {batch_result['document']['title']}"


def _run_preview_canvas_changes(tool_args: dict, runtime_state: dict):
    canvas_state = _get_canvas_runtime_state(runtime_state)
    result = preview_canvas_changes(
        canvas_state,
        tool_args.get("operations"),
        document_id=tool_args.get("document_id"),
        document_path=tool_args.get("document_path"),
    )
    preview = result.get("preview") if isinstance(result.get("preview"), dict) else {}
    target_label = str(preview.get("document_path") or preview.get("title") or "Canvas").strip()
    return result, f"Canvas changes previewed for {target_label}"


def _run_transform_canvas_lines(tool_args: dict, runtime_state: dict):
    canvas_state = _get_canvas_runtime_state(runtime_state)
    count_only = tool_args.get("count_only") is True
    case_sensitive = True if "case_sensitive" not in tool_args else tool_args.get("case_sensitive") is True
    result = transform_canvas_lines(
        canvas_state,
        tool_args.get("pattern", ""),
        tool_args.get("replacement", ""),
        document_id=tool_args.get("document_id"),
        document_path=tool_args.get("document_path"),
        scope=tool_args.get("scope") or "all",
        is_regex=tool_args.get("is_regex") is True,
        case_sensitive=case_sensitive,
        count_only=count_only,
    )
    if count_only:
        return result, f"Canvas transform matched {result.get('matches_found', 0)} line(s)"
    if int(result.get("matches_replaced") or 0) <= 0:
        return result, f"Canvas transform matched {result.get('matches_found', 0)} line(s)"
    document = result.get("document") if isinstance(result.get("document"), dict) else None
    if document and result.get("affected_lines"):
        clear_overlapping_canvas_viewports(
            canvas_state,
            document_id=document.get("id"),
            document_path=document.get("path"),
            edit_start_line=min(result.get("affected_lines") or [0]),
            edit_end_line=max(result.get("affected_lines") or [0]),
        )
    if document:
        tool_result = build_canvas_tool_result(document, action="lines_transformed")
        tool_result["matches_found"] = result.get("matches_found", 0)
        tool_result["matches_replaced"] = result.get("matches_replaced", 0)
        tool_result["affected_lines"] = result.get("affected_lines") or []
        tool_result["scope"] = result.get("scope")
        return tool_result, f"Canvas transformed in {document['title']}"
    return result, f"Canvas transform matched {result.get('matches_found', 0)} line(s)"


def _run_update_canvas_metadata(tool_args: dict, runtime_state: dict):
    canvas_state = _get_canvas_runtime_state(runtime_state)
    result = update_canvas_metadata(
        canvas_state,
        document_id=tool_args.get("document_id"),
        document_path=tool_args.get("document_path"),
        title=tool_args.get("title"),
        summary=tool_args.get("summary"),
        role=tool_args.get("role"),
        ignored=tool_args.get("ignored"),
        ignored_reason=tool_args.get("ignored_reason"),
        add_imports=tool_args.get("add_imports"),
        remove_imports=tool_args.get("remove_imports"),
        add_exports=tool_args.get("add_exports"),
        remove_exports=tool_args.get("remove_exports"),
        add_dependencies=tool_args.get("add_dependencies"),
        remove_dependencies=tool_args.get("remove_dependencies"),
        add_symbols=tool_args.get("add_symbols"),
    )
    tool_result = build_canvas_tool_result(result["document"], action="metadata_updated")
    tool_result["updated_fields"] = result.get("updated_fields") or []
    if result["document"].get("ignored") is True:
        return tool_result, f"Canvas document ignored: {result['document']['title']}"
    if "ignored" in (result.get("updated_fields") or []):
        return tool_result, f"Canvas document re-enabled: {result['document']['title']}"
    return tool_result, f"Canvas metadata updated for {result['document']['title']}"


def _run_set_canvas_viewport(tool_args: dict, runtime_state: dict):
    canvas_state = _get_canvas_runtime_state(runtime_state)
    auto_unpin_on_edit = True if "auto_unpin_on_edit" not in tool_args else tool_args.get("auto_unpin_on_edit") is True
    result = set_canvas_viewport(
        canvas_state,
        start_line=int(tool_args.get("start_line") or 0),
        end_line=int(tool_args.get("end_line") or 0),
        ttl_turns=int(tool_args.get("ttl_turns") or 0) if tool_args.get("ttl_turns") not in (None, "") else 3,
        permanent=tool_args.get("permanent") is True,
        auto_unpin_on_edit=auto_unpin_on_edit,
        document_id=tool_args.get("document_id"),
        document_path=tool_args.get("document_path"),
    )
    pinned = result.get("pinned") if isinstance(result.get("pinned"), dict) else {}
    target_label = str(pinned.get("document_path") or pinned.get("document_id") or "Canvas").strip()
    return result, f"Canvas viewport pinned for {target_label}"


def _run_focus_canvas_page(tool_args: dict, runtime_state: dict):
    canvas_state = _get_canvas_runtime_state(runtime_state)
    auto_unpin_on_edit = True if "auto_unpin_on_edit" not in tool_args else tool_args.get("auto_unpin_on_edit") is True
    result = focus_canvas_page(
        canvas_state,
        page_number=int(tool_args.get("page_number") or 0),
        ttl_turns=int(tool_args.get("ttl_turns") or 0) if tool_args.get("ttl_turns") not in (None, "") else 3,
        auto_unpin_on_edit=auto_unpin_on_edit,
        document_id=tool_args.get("document_id"),
        document_path=tool_args.get("document_path"),
    )
    target_label = str(result.get("document_path") or result.get("document_id") or "Canvas").strip()
    return result, f"Canvas focused on page {result.get('page_number')} for {target_label}"


def _run_clear_canvas_viewport(tool_args: dict, runtime_state: dict):
    canvas_state = _get_canvas_runtime_state(runtime_state)
    result = clear_canvas_viewport(
        canvas_state,
        document_id=tool_args.get("document_id"),
        document_path=tool_args.get("document_path"),
    )
    return result, f"Canvas viewport cleared ({result.get('cleared_count', 0)})"


def _run_delete_canvas_document(tool_args: dict, runtime_state: dict):
    canvas_state = _get_canvas_runtime_state(runtime_state)
    result = delete_canvas_document(
        canvas_state,
        document_id=tool_args.get("document_id"),
        document_path=tool_args.get("document_path"),
    )
    deleted_title = str(result.get("deleted_title") or "Canvas")
    return result, f"Canvas deleted: {deleted_title}"


def _run_clear_canvas(tool_args: dict, runtime_state: dict):
    del tool_args
    canvas_state = _get_canvas_runtime_state(runtime_state)
    result = clear_canvas(canvas_state)
    return result, f"Canvas cleared ({result.get('cleared_count', 0)} documents removed)"


def _normalize_conversation_title_for_tool(raw_title: str) -> str:
    text = re.sub(r"\s+", " ", str(raw_title or "").replace("\n", " ")).strip()
    if not text:
        return ""
    text = re.sub(r"^[\s\-*>#`\"'“”‘’\[\](){}:;,.!?]+", "", text)
    text = re.sub(r"[\s\-*>#`\"'“”‘’\[\](){}:;,.!?]+$", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    words = text.split(" ")
    if len(words) > 5:
        text = " ".join(words[:5]).strip()
    return text[:48].strip()


def _build_internal_title_generation_prompt(source_text: str) -> list[dict]:
    return [
        {
            "role": "system",
            "content": (
                "You generate a compact conversation title from the user's message. "
                "Return only a noun phrase or short topic label, not a sentence.\n\n"
                "Rules:\n"
                "- Return ONLY the title — nothing else.\n"
                "- Use 2-5 words when possible; 1 word is allowed if it is specific.\n"
                "- Match the user's language when clear.\n"
                "- Prefer the concrete topic over generic labels like 'Greeting', 'Question', 'Canvas', or 'Completed'.\n"
                "- Do NOT answer, explain, apologize, greet, or mention that you are generating a title.\n"
                "- No quotes, markdown, emojis, or punctuation at the end.\n"
                "- If the topic is unclear, return exactly: New Chat\n\n"
                "Examples:\n"
                "User: 'How do I sort a list in Python?' → Python List Sorting\n"
                "User: 'Hello, how are you?' → Hello\n"
                "User: 'What is the capital of France?' → Capital of France\n"
                "User: 'What's the weather like today?' → Weather Forecast"
            ),
        },
        {
            "role": "user",
            "content": str(source_text or "").strip(),
        },
    ]


def _generate_conversation_title_with_dedicated_model(conversation_id: int, fallback_model: str = "") -> str:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT role, content
               FROM messages
               WHERE conversation_id = ?
                 AND deleted_at IS NULL
                 AND role IN ('user', 'summary')
               ORDER BY position, id
               LIMIT 3""",
            (conversation_id,),
        ).fetchall()

    if not rows:
        return ""

    source_text = ""
    for row in rows:
        content = str(row["content"] or "").strip()
        if content:
            source_text = content
            break
    if not source_text:
        return ""

    settings = get_app_settings()
    fallback_model_id = str(fallback_model or "").strip() or "deepseek-chat"
    title_model = get_operation_model(
        "generate_title",
        settings,
        fallback_model_id=fallback_model_id,
    )
    result = collect_agent_response(
        _build_internal_title_generation_prompt(source_text),
        title_model,
        1,
        [],
        temperature=get_model_temperature(settings),
    )
    return _normalize_conversation_title_for_tool(result.get("content") or "")


def _run_set_conversation_title(tool_args: dict, runtime_state: dict):
    agent_context = runtime_state.get("agent_context") if isinstance(runtime_state.get("agent_context"), dict) else {}
    conv_id = _coerce_int_range(agent_context.get("conversation_id"), 0, 0, 2_147_483_647)
    if conv_id <= 0:
        return {"status": "error", "error": "Missing conversation id."}, "Missing conversation id"

    with get_db() as conn:
        row = conn.execute(
            "SELECT title, title_source, title_overridden FROM conversations WHERE id = ?",
            (conv_id,),
        ).fetchone()
        if not row:
            return {"status": "error", "error": "Conversation not found."}, "Conversation not found"

        current_title = str(row["title"] or "").strip()
        current_title_overridden = int(row["title_overridden"] or 0)
        if current_title_overridden == 1:
            return {
                "status": "ok",
                "updated": False,
                "title": current_title,
                "reason": "title_already_set",
            }, f"Conversation title already set: {current_title}"

    generated_title = _generate_conversation_title_with_dedicated_model(
        conv_id,
        fallback_model=str(agent_context.get("model") or "").strip(),
    )
    requested_title = _normalize_conversation_title_for_tool(tool_args.get("title", ""))
    final_title = generated_title or requested_title
    if not final_title:
        return {"status": "error", "error": "Title could not be generated."}, "Title could not be generated"

    with get_db() as conn:
        conn.execute(
            """
            UPDATE conversations
               SET title = ?,
                   title_source = 'system',
                   title_overridden = 0,
                   updated_at = datetime('now')
             WHERE id = ?
            """,
            (final_title, conv_id),
        )

    return {"status": "ok", "updated": True, "title": final_title}, f"Conversation title set: {final_title}"


_TOOL_EXECUTORS = {
    "append_scratchpad": _run_append_scratchpad,
    "replace_scratchpad": _run_replace_scratchpad,
    "read_scratchpad": _run_read_scratchpad,
    "save_to_conversation_memory": _run_save_to_conversation_memory,
    "delete_conversation_memory_entry": _run_delete_conversation_memory_entry,
    "save_to_persona_memory": _run_save_to_persona_memory,
    "delete_persona_memory_entry": _run_delete_persona_memory_entry,
    "delete_tool_result": _run_delete_tool_result,
    "list_tool_memory": _run_list_tool_memory,
    "ask_clarifying_question": _run_ask_clarifying_question,
    "set_conversation_title": _run_set_conversation_title,
    "sub_agent": _run_sub_agent,
    "image_explain": _run_image_explain,
    "transcribe_youtube_video": _run_transcribe_youtube_video,
    "search_knowledge_base": _run_search_knowledge_base,
    "expand_truncated_tool_result": _run_expand_truncated_tool_result,
    "search_web": _run_search_web,
    "search_news_ddgs": _run_search_news_ddgs,
    "search_news_google": _run_search_news_google,
    "fetch_url": _run_fetch_url,
    "fetch_url_summarized": _run_fetch_url_summarized,
    "scroll_fetched_content": _run_scroll_fetched_content,
    "grep_fetched_content": _run_grep_fetched_content,
    "expand_canvas_document": _run_expand_canvas_document,
    "batch_read_canvas_documents": _run_batch_read_canvas_documents,
    "scroll_canvas_document": _run_scroll_canvas_document,
    "search_canvas_document": _run_search_canvas_document,
    "validate_canvas_document": _run_validate_canvas_document,
    "create_directory": _run_create_directory,
    "create_file": _run_create_file,
    "update_file": _run_update_file,
    "read_file": _run_read_file,
    "list_dir": _run_list_dir,
    "search_files": _run_search_files,
    "write_project_tree": _run_write_project_tree,
    "validate_project_workspace": _run_validate_project_workspace,
    "import_github_repository_to_canvas": _run_import_github_repository_to_canvas,
    "preview_github_import_to_canvas": _run_preview_github_import_to_canvas,
    "create_canvas_document": _run_create_canvas_document,
    "rewrite_canvas_document": _run_rewrite_canvas_document,
    "preview_canvas_changes": _run_preview_canvas_changes,
    "transform_canvas_lines": _run_transform_canvas_lines,
    "update_canvas_metadata": _run_update_canvas_metadata,
    "set_canvas_viewport": _run_set_canvas_viewport,
    "focus_canvas_page": _run_focus_canvas_page,
    "clear_canvas_viewport": _run_clear_canvas_viewport,
    "replace_canvas_lines": _run_replace_canvas_lines,
    "insert_canvas_lines": _run_insert_canvas_lines,
    "delete_canvas_lines": _run_delete_canvas_lines,
    "batch_canvas_edits": _run_batch_canvas_edits,
    "delete_canvas_document": _run_delete_canvas_document,
    "clear_canvas": _run_clear_canvas,
}


def _execute_tool(tool_name: str, tool_args: dict, runtime_state: dict | None = None):
    runtime_state = runtime_state if isinstance(runtime_state, dict) else {}
    tool_name = _normalize_tool_name(tool_name)
    handler = _TOOL_EXECUTORS.get(tool_name)
    if handler is not None:
        return handler(tool_args if isinstance(tool_args, dict) else {}, runtime_state)
    return {"error": f"Unknown tool: {tool_name}"}, f"Unknown tool: {tool_name}"


def _build_active_canvas_prompt_payload(runtime_state: dict) -> dict | None:
    if not isinstance(runtime_state, dict):
        return None
    prompt_state = runtime_state.get("canvas_prompt") if isinstance(runtime_state.get("canvas_prompt"), dict) else {}
    max_lines = _coerce_int_range(prompt_state.get("max_lines"), 0, 0, 10_000)
    max_chars = _coerce_int_range(prompt_state.get("max_chars"), 0, 0, 1_000_000)
    max_tokens = _coerce_int_range(prompt_state.get("max_tokens"), 0, 0, 1_000_000)
    code_line_max_chars = _coerce_int_range(prompt_state.get("code_line_max_chars"), 0, 0, 10_000)
    text_line_max_chars = _coerce_int_range(prompt_state.get("text_line_max_chars"), 0, 0, 10_000)
    if max_lines <= 0 and max_chars <= 0 and max_tokens <= 0:
        return None

    canvas_state = _get_canvas_runtime_state(runtime_state)
    documents = get_canvas_runtime_documents(canvas_state)
    if not documents:
        return None

    return _build_canvas_prompt_payload(
        documents,
        active_document_id=get_canvas_runtime_active_document_id(canvas_state),
        canvas_viewports=get_canvas_viewport_payloads(canvas_state),
        max_lines=max_lines or 250,
        max_chars=max_chars or None,
        max_tokens=max_tokens or 0,
        code_line_max_chars=code_line_max_chars or None,
        text_line_max_chars=text_line_max_chars or None,
    )


def _refresh_latest_canvas_context_injection_message(messages: list[dict], runtime_state: dict) -> bool:
    if not isinstance(messages, list) or not messages or not isinstance(runtime_state, dict):
        return False

    canvas_state = _get_canvas_runtime_state(runtime_state)
    prompt_state = runtime_state.get("canvas_prompt") if isinstance(runtime_state.get("canvas_prompt"), dict) else {}
    agent_context = runtime_state.get("agent_context") if isinstance(runtime_state.get("agent_context"), dict) else {}
    active_tool_names = _normalize_tool_name_list(
        agent_context.get("prompt_tool_names")
        if isinstance(agent_context.get("prompt_tool_names"), list)
        else agent_context.get("enabled_tool_names")
    )
    canvas_documents = get_canvas_runtime_documents(canvas_state)
    canvas_active_document_id = get_canvas_runtime_active_document_id(canvas_state)
    canvas_viewports = get_canvas_viewport_payloads(canvas_state)

    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if str(message.get("role") or "").strip() != "system":
            continue
        content = str(message.get("content") or "")
        if not content:
            continue
        if not any(marker in content for marker in RUNTIME_CONTEXT_INJECTION_SECTION_MARKERS):
            continue

        refreshed_content = refresh_canvas_sections_in_context_injection(
            content,
            active_tool_names=active_tool_names,
            canvas_documents=canvas_documents,
            canvas_active_document_id=canvas_active_document_id,
            canvas_viewports=canvas_viewports,
            canvas_prompt_max_lines=_coerce_int_range(prompt_state.get("max_lines"), 0, 0, 10_000) or None,
            canvas_prompt_max_chars=_coerce_int_range(prompt_state.get("max_chars"), 0, 0, 1_000_000) or None,
            canvas_prompt_max_tokens=_coerce_int_range(prompt_state.get("max_tokens"), 0, 0, 1_000_000) or None,
            canvas_prompt_code_line_max_chars=_coerce_int_range(prompt_state.get("code_line_max_chars"), 0, 0, 10_000)
            or None,
            canvas_prompt_text_line_max_chars=_coerce_int_range(prompt_state.get("text_line_max_chars"), 0, 0, 10_000)
            or None,
        )
        if refreshed_content == content:
            return False
        messages[index] = {**message, "content": refreshed_content}
        return True

    return False


def _build_already_visible_canvas_expand_result(tool_args: dict, runtime_state: dict) -> dict | None:
    prompt_payload = _build_active_canvas_prompt_payload(runtime_state)
    if not isinstance(prompt_payload, dict) or prompt_payload.get("is_truncated") is not False:
        return None

    active_document = (
        prompt_payload.get("active_document") if isinstance(prompt_payload.get("active_document"), dict) else None
    )
    if not isinstance(active_document, dict):
        return None
    if prompt_payload.get("active_document_ignored") is True or active_document.get("ignored") is True:
        return None

    canvas_state = _get_canvas_runtime_state(runtime_state)
    target_document_id = tool_args.get("document_id")
    target_document_path = tool_args.get("document_path")
    if target_document_id or target_document_path:
        try:
            _, target_document = find_canvas_document(
                canvas_state,
                document_id=target_document_id,
                document_path=target_document_path,
            )
        except Exception:
            return None
        if str(target_document.get("id") or "") != str(active_document.get("id") or ""):
            return None

    target_label = str(active_document.get("path") or active_document.get("title") or "Canvas").strip() or "Canvas"
    return {
        "status": "ok",
        "action": "already_visible",
        "document_id": active_document.get("id"),
        "document_path": active_document.get("path"),
        "title": active_document.get("title"),
        "line_count": prompt_payload.get("total_lines"),
        "visible_lines": prompt_payload.get("visible_lines") or [],
        "visible_line_end": prompt_payload.get("visible_line_end"),
        "is_truncated": False,
        "reason": f"{target_label} is already fully visible in the current prompt excerpt; expand_canvas_document was skipped.",
    }


def _normalize_canvas_document_path_key(value) -> str:
    return str(value or "").strip().replace("\\", "/")


def _register_canvas_document_locator(
    document_id,
    document_path,
    *,
    doc_ids: set[str],
    doc_paths: set[str],
) -> None:
    normalized_document_id = str(document_id or "").strip()
    normalized_document_path = _normalize_canvas_document_path_key(document_path)
    if normalized_document_id:
        doc_ids.add(normalized_document_id)
    if normalized_document_path:
        doc_paths.add(normalized_document_path)


def _resolve_canvas_document_locator(
    canvas_state: dict,
    *,
    document_id=None,
    document_path=None,
) -> tuple[str, str]:
    resolved_document_id = ""
    resolved_document_path = ""
    try:
        _, resolved_document = find_canvas_document(
            canvas_state,
            document_id=document_id,
            document_path=document_path,
        )
    except Exception:
        resolved_document_id = str(document_id or "").strip()
        resolved_document_path = _normalize_canvas_document_path_key(document_path)
        return resolved_document_id, resolved_document_path

    resolved_document_id = str(resolved_document.get("id") or "").strip()
    resolved_document_path = _normalize_canvas_document_path_key(resolved_document.get("path"))
    return resolved_document_id, resolved_document_path


def _resolve_canvas_read_targets(tool_name: str, tool_args: dict, canvas_state: dict) -> list[dict]:
    normalized_tool_name = _normalize_tool_name(tool_name)
    normalized_tool_args = tool_args if isinstance(tool_args, dict) else {}

    if normalized_tool_name == "search_canvas_document" and normalized_tool_args.get("all_documents") is True:
        return []

    raw_targets: list[dict] = []
    if normalized_tool_name == "batch_read_canvas_documents":
        request_entries = (
            normalized_tool_args.get("documents") if isinstance(normalized_tool_args.get("documents"), list) else []
        )
        explicit_target_seen = False
        for request_entry in request_entries:
            if not isinstance(request_entry, dict):
                continue
            target_document_id = request_entry.get("document_id")
            target_document_path = request_entry.get("document_path")
            if target_document_id or target_document_path:
                explicit_target_seen = True
            raw_targets.append({"document_id": target_document_id, "document_path": target_document_path})
        if request_entries and not explicit_target_seen:
            raw_targets = [{"document_id": None, "document_path": None}]
    else:
        raw_targets = [
            {
                "document_id": normalized_tool_args.get("document_id"),
                "document_path": normalized_tool_args.get("document_path"),
            }
        ]

    resolved_targets: list[dict] = []
    seen_keys: set[tuple[str, str]] = set()
    for raw_target in raw_targets:
        resolved_document_id, resolved_document_path = _resolve_canvas_document_locator(
            canvas_state,
            document_id=raw_target.get("document_id"),
            document_path=raw_target.get("document_path"),
        )
        target_key = (resolved_document_id, resolved_document_path)
        if target_key in seen_keys:
            continue
        seen_keys.add(target_key)
        resolved_targets.append(
            {
                "document_id": resolved_document_id,
                "document_path": resolved_document_path,
            }
        )
    return resolved_targets


def _should_skip_canvas_read_after_same_turn_mutation(
    tool_name: str,
    tool_args: dict,
    canvas_state: dict,
    mutated_doc_ids: set[str],
    mutated_doc_paths: set[str],
) -> tuple[bool, str]:
    normalized_tool_name = _normalize_tool_name(tool_name)
    if normalized_tool_name not in CANVAS_ALL_READ_TOOL_NAMES:
        return False, ""
    if not mutated_doc_ids and not mutated_doc_paths:
        return False, ""

    read_targets = _resolve_canvas_read_targets(normalized_tool_name, tool_args, canvas_state)
    for target in read_targets:
        target_document_id = str(target.get("document_id") or "").strip()
        target_document_path = _normalize_canvas_document_path_key(target.get("document_path"))
        if target_document_id and target_document_id in mutated_doc_ids:
            target_label = target_document_path or target_document_id
        elif target_document_path and target_document_path in mutated_doc_paths:
            target_label = target_document_path
        else:
            continue
        guard_message = (
            f"Skipped: document '{target_label}' was already modified in this turn. "
            "The mutation result above contains the updated snapshot. "
            "Re-reading immediately is unnecessary."
        )
        return True, guard_message

    return False, ""


def _collect_canvas_mutation_locators(tool_name: str, tool_args: dict, result) -> tuple[set[str], set[str]]:
    normalized_tool_name = _normalize_tool_name(tool_name)
    if normalized_tool_name not in CANVAS_MUTATION_TOOL_NAMES:
        return set(), set()

    normalized_tool_args = tool_args if isinstance(tool_args, dict) else {}
    mutated_doc_ids: set[str] = set()
    mutated_doc_paths: set[str] = set()

    _register_canvas_document_locator(
        normalized_tool_args.get("document_id"),
        normalized_tool_args.get("document_path"),
        doc_ids=mutated_doc_ids,
        doc_paths=mutated_doc_paths,
    )

    targets = normalized_tool_args.get("targets") if isinstance(normalized_tool_args.get("targets"), list) else []
    for target in targets:
        if not isinstance(target, dict):
            continue
        _register_canvas_document_locator(
            target.get("document_id"),
            target.get("document_path"),
            doc_ids=mutated_doc_ids,
            doc_paths=mutated_doc_paths,
        )

    if isinstance(result, dict):
        _register_canvas_document_locator(
            result.get("document_id") or result.get("id"),
            result.get("document_path") or result.get("path"),
            doc_ids=mutated_doc_ids,
            doc_paths=mutated_doc_paths,
        )
        _register_canvas_document_locator(
            result.get("deleted_id"),
            None,
            doc_ids=mutated_doc_ids,
            doc_paths=mutated_doc_paths,
        )

        nested_document = result.get("document") if isinstance(result.get("document"), dict) else None
        if isinstance(nested_document, dict):
            _register_canvas_document_locator(
                nested_document.get("document_id") or nested_document.get("id"),
                nested_document.get("document_path") or nested_document.get("path"),
                doc_ids=mutated_doc_ids,
                doc_paths=mutated_doc_paths,
            )

        for list_key in ("documents", "results"):
            list_value = result.get(list_key) if isinstance(result.get(list_key), list) else []
            for entry in list_value:
                if not isinstance(entry, dict):
                    continue
                _register_canvas_document_locator(
                    entry.get("document_id") or entry.get("id"),
                    entry.get("document_path") or entry.get("path"),
                    doc_ids=mutated_doc_ids,
                    doc_paths=mutated_doc_paths,
                )

    return mutated_doc_ids, mutated_doc_paths


def collect_agent_response(
    api_messages: list,
    model: str,
    max_steps: int,
    enabled_tool_names: list[str],
    *,
    temperature: float = 0.7,
    fetch_url_token_threshold: int | None = None,
    fetch_url_clip_aggressiveness: int | None = None,
) -> dict:
    full_response = ""
    full_reasoning = ""
    usage_data = None
    tool_results = []
    errors = []

    for event in run_agent_stream(
        api_messages,
        model,
        max_steps,
        enabled_tool_names,
        temperature=temperature,
        fetch_url_token_threshold=fetch_url_token_threshold,
        fetch_url_clip_aggressiveness=fetch_url_clip_aggressiveness,
    ):
        if event["type"] == "answer_delta":
            full_response += event.get("text", "")
        elif event["type"] == "reasoning_delta":
            full_reasoning += event.get("text", "")
        elif event["type"] == "usage":
            usage_data = event
        elif event["type"] == "tool_capture":
            tool_results = event.get("tool_results") or []
        elif event["type"] == "tool_error":
            errors.append(event.get("error") or "Unknown tool error")

    return {
        "content": full_response,
        "reasoning_content": full_reasoning,
        "usage": usage_data,
        "tool_results": tool_results,
        "errors": errors,
    }


def _tool_input_preview(tool_name: str, tool_args: dict) -> str:
    tool_name = _normalize_tool_name(tool_name)
    tool_args = tool_args if isinstance(tool_args, dict) else {}
    if tool_name in {"save_to_conversation_memory", "save_to_persona_memory"}:
        entry_type = str(tool_args.get("entry_type") or "").strip()
        key = str(tool_args.get("key") or "").strip()
        value = str(tool_args.get("value") or "").strip()
        compact = ": ".join(part for part in (key, value) if part)
        if entry_type and compact:
            return f"{entry_type} | {compact}"[:300]
        return (compact or entry_type)[:300]
    if tool_name in {"delete_conversation_memory_entry", "delete_persona_memory_entry"}:
        return str(tool_args.get("entry_id") or "").strip()[:300]
    if tool_name in {"search_web", "search_news_ddgs", "search_news_google"}:
        values = _get_search_tool_queries(tool_args)
        if isinstance(values, list):
            return ", ".join(str(value).strip() for value in values if str(value).strip())[:300]
    if tool_name == "search_knowledge_base":
        query = str(tool_args.get("query") or "").strip()
        if _coerce_tool_bool(tool_args.get("save_to_conversation_memory")):
            memory_key = str(tool_args.get("memory_key") or "").strip()
            suffix = f"save:{memory_key}" if memory_key else "save:auto"
            if query:
                return f"{query} | {suffix}"[:300]
            return suffix[:300]
        return query[:300]
    if tool_name == "fetch_url":
        return str(tool_args.get("url") or "").strip()[:300]
    if tool_name == "fetch_url_summarized":
        url = str(tool_args.get("url") or "").strip()
        focus = str(tool_args.get("focus") or "").strip()
        if url and focus:
            return f"{url} | {focus}"[:300]
        return url[:300]
    if tool_name == "scroll_fetched_content":
        url = str(tool_args.get("url") or "").strip()
        start_line = _coerce_int_range(tool_args.get("start_line"), 1, 1, 1_000_000)
        window_lines = _coerce_int_range(tool_args.get("window_lines"), 120, 20, 400)
        preview = f"line {start_line} (+{window_lines})"
        if url:
            return f"{url} | {preview}"[:300]
        return preview[:300]
    if tool_name == "read_file":
        return str(tool_args.get("path") or "").strip()[:300]
    if tool_name == "list_dir":
        return str(tool_args.get("path") or ".").strip()[:300]
    if tool_name == "search_files":
        query = str(tool_args.get("query") or "").strip()
        path_prefix = str(tool_args.get("path_prefix") or "").strip()
        if query and path_prefix:
            return f"{query} @ {path_prefix}"[:300]
        return (query or path_prefix)[:300]
    if tool_name in {"import_github_repository_to_canvas", "preview_github_import_to_canvas"}:
        return str(tool_args.get("url") or "").strip()[:300]
    if tool_name in {"expand_canvas_document", "scroll_canvas_document"}:
        target = str(tool_args.get("document_path") or tool_args.get("document_id") or "active document").strip()
        if tool_name == "scroll_canvas_document":
            start_line = tool_args.get("start_line")
            end_line = tool_args.get("end_line")
            if start_line or end_line:
                return f"{target} {start_line}-{end_line}"[:300]
        return target[:300]
    if tool_name == "search_canvas_document":
        target = str(tool_args.get("document_path") or tool_args.get("document_id") or "active document").strip()
        query = str(tool_args.get("query") or "").strip()
        if tool_args.get("all_documents") is True:
            target = "all canvas documents"
        return f"{query} @ {target}"[:300]
    if tool_name == "sub_agent":
        return str(tool_args.get("task") or "").strip()[:300]
    if tool_name == "transcribe_youtube_video":
        return str(tool_args.get("url") or "").strip()[:300]
    return ""


def _build_compact_tool_message_content(
    tool_name: str,
    tool_args: dict,
    result,
    summary: str,
    transcript_result=None,
    storage_entry: dict | None = None,
) -> str:
    del result

    def _clip_serialized_tool_content(value) -> str:
        return _clean_tool_text(_serialize_tool_message_content(value), limit=RAG_TOOL_RESULT_MAX_TEXT_CHARS)

    if tool_name == "fetch_url" and isinstance(transcript_result, dict):
        return _build_fetch_tool_message_content(tool_args, summary, transcript_result)

    if isinstance(transcript_result, str):
        if len(transcript_result) <= RAG_TOOL_RESULT_MAX_TEXT_CHARS:
            return transcript_result
        clip_marker = " [CLIPPED: original "
        marker_index = transcript_result.find(clip_marker)
        if marker_index > 0:
            marker = transcript_result[marker_index:]
            prefix_limit = max(0, RAG_TOOL_RESULT_MAX_TEXT_CHARS - len(marker) - 1)
            prefix = transcript_result[:prefix_limit].rstrip()
            return f"{prefix}…{marker}"
        return _clean_tool_text(transcript_result, limit=RAG_TOOL_RESULT_MAX_TEXT_CHARS)

    preferred_entry = storage_entry if isinstance(storage_entry, dict) else None
    if preferred_entry:
        content = _clean_tool_text(preferred_entry.get("content") or "", limit=RAG_TOOL_RESULT_MAX_TEXT_CHARS)
        if content:
            return content

    try:
        return _clip_serialized_tool_content(transcript_result)
    except Exception:
        return _clip_serialized_tool_content({"tool_name": tool_name, "summary": _clean_tool_text(summary, limit=300)})


def _format_list_tool_result(items: list[dict], title: str, link_key: str, extra_keys: tuple[str, ...] = ()) -> str:
    lines = [title]
    added = 0
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict) or item.get("error"):
            continue
        entry_lines = [f"{index}. {str(item.get('title') or 'Untitled').strip()}"]
        link = str(item.get(link_key) or "").strip()
        if link:
            entry_lines.append(f"URL: {link}")
        snippet = str(item.get("snippet") or item.get("body") or "").strip()
        if snippet:
            entry_lines.append(f"Snippet: {snippet}")
        for extra_key in extra_keys:
            value = str(item.get(extra_key) or "").strip()
            if value:
                entry_lines.append(f"{extra_key.title()}: {value}")
        lines.append("\n".join(entry_lines))
        added += 1
    if added == 0:
        return ""
    return _clean_tool_text("\n\n".join(lines), limit=RAG_TOOL_RESULT_MAX_TEXT_CHARS)


def _build_tool_result_storage_entry(
    tool_name: str, tool_args: dict, result, summary: str, transcript_result=None
) -> dict | None:
    if tool_name == "search_knowledge_base":
        return None

    text = ""
    if tool_name == "fetch_url":
        if isinstance(result, dict):
            display_result = transcript_result if isinstance(transcript_result, dict) else result
            display_content = _clean_tool_text(
                display_result.get("content") or "", limit=RAG_TOOL_RESULT_MAX_TEXT_CHARS
            )
            raw_content = _clean_tool_text(
                result.get("raw_content") or result.get("content") or "",
                limit=FETCH_RAW_TOOL_RESULT_MAX_TEXT_CHARS,
            )
            parts = []
            title = str(result.get("title") or "").strip()
            url = str(result.get("url") or tool_args.get("url") or "").strip()
            summary_notice = str(display_result.get("summary_notice") or "").strip()
            fetch_diagnostic = str(display_result.get("fetch_diagnostic") or "").strip()
            meta_description = _clean_tool_text(display_result.get("meta_description") or "", limit=240)
            structured_data = _clean_tool_text(display_result.get("structured_data") or "", limit=500)
            recovery_hint = _clean_tool_text(display_result.get("recovery_hint") or "", limit=240)
            if title:
                parts.append(f"Title: {title}")
            if url:
                parts.append(f"URL: {url}")
            if summary_notice:
                parts.append(f"Note: {summary_notice}")
            if fetch_diagnostic:
                parts.append(f"Fetch status: {fetch_diagnostic}")
            if meta_description:
                parts.append(f"Description: {meta_description}")
            if structured_data:
                parts.append("Structured data:\n" + structured_data)
            if recovery_hint:
                parts.append(f"Recovery: {recovery_hint}")
            if display_content:
                parts.append(display_content)
            text = "\n\n".join(parts)
    elif tool_name == "fetch_url_summarized" and isinstance(result, dict):
        parts = []
        title = _clean_tool_text(result.get("title") or "", limit=160)
        url = _clean_tool_text(result.get("url") or tool_args.get("url") or "", limit=220)
        focus = _clean_tool_text(result.get("focus") or tool_args.get("focus") or "", limit=260)
        summary_text = _clean_tool_text(result.get("summary") or "", limit=RAG_TOOL_RESULT_MAX_TEXT_CHARS)
        if title:
            parts.append(f"Title: {title}")
        if url:
            parts.append(f"URL: {url}")
        if focus:
            parts.append(f"Focus: {focus}")
        if summary_text:
            parts.append("Summary:\n" + summary_text)
        text = "\n\n".join(parts)
    elif tool_name == "sub_agent" and isinstance(result, dict):
        parts = []
        task_preview = _clean_tool_text(_tool_input_preview(tool_name, tool_args), limit=300)
        summary_text = _clean_tool_text(result.get("summary") or summary or "", limit=RAG_TOOL_RESULT_MAX_TEXT_CHARS)
        if task_preview:
            parts.append(f"Task: {task_preview}")
        if summary_text:
            parts.append("Summary:\n" + summary_text)
        artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), list) else []
        artifact_lines = []
        for artifact in artifacts[:6]:
            if not isinstance(artifact, dict):
                continue
            label = _clean_tool_text(
                artifact.get("label") or artifact.get("title") or artifact.get("type") or "artifact", limit=80
            )
            artifact_summary = _clean_tool_text(artifact.get("summary") or artifact.get("content") or "", limit=160)
            if label and artifact_summary:
                artifact_lines.append(f"- {label}: {artifact_summary}")
        if artifact_lines:
            parts.append("Artifacts:\n" + "\n".join(artifact_lines))
        text = "\n\n".join(parts)
    elif tool_name == "transcribe_youtube_video" and isinstance(result, dict):
        parts = []
        title = _clean_tool_text(result.get("title") or "", limit=160)
        url = _clean_tool_text(result.get("source_url") or tool_args.get("url") or "", limit=220)
        language = _clean_tool_text(result.get("transcript_language") or "", limit=32)
        context_block = _clean_tool_text(
            result.get("transcript_context_block") or "", limit=RAG_TOOL_RESULT_MAX_TEXT_CHARS
        )
        if title:
            parts.append(f"Title: {title}")
        if url:
            parts.append(f"URL: {url}")
        if language:
            parts.append(f"Language: {language}")
        if context_block:
            parts.append(context_block)
        text = "\n\n".join(parts)
    elif tool_name == "search_web" and isinstance(result, list):
        text = _format_list_tool_result(result, "Web results", link_key="url")
    elif tool_name in {"search_news_ddgs", "search_news_google"} and isinstance(result, list):
        text = _format_list_tool_result(result, "News results", link_key="link", extra_keys=("time", "source"))

    text = _clean_tool_text(text, limit=RAG_TOOL_RESULT_MAX_TEXT_CHARS)
    if not text:
        return None

    entry = {
        "tool_name": tool_name,
        "content": text,
    }
    cleaned_summary = _clean_tool_text(summary, limit=RAG_TOOL_RESULT_SUMMARY_MAX_CHARS)
    if cleaned_summary:
        entry["summary"] = cleaned_summary
    input_preview = _tool_input_preview(tool_name, tool_args)
    if input_preview:
        entry["input_preview"] = input_preview
    if tool_name == "fetch_url" and isinstance(result, dict):
        display_result = transcript_result if isinstance(transcript_result, dict) else result
        raw_content = _clean_tool_text(
            result.get("raw_content") or result.get("content") or "",
            limit=FETCH_RAW_TOOL_RESULT_MAX_TEXT_CHARS,
        )
        display_content = _clean_tool_text(
            display_result.get("content") or "", limit=FETCH_RAW_TOOL_RESULT_MAX_TEXT_CHARS
        )
        content_mode = str(display_result.get("content_mode") or "").strip()
        summary_notice = _clean_tool_text(display_result.get("summary_notice") or "", limit=300)
        recovery_hint = _clean_tool_text(display_result.get("recovery_hint") or "", limit=240)
        meta_description = _clean_tool_text(display_result.get("meta_description") or "", limit=240)
        structured_data = _clean_tool_text(display_result.get("structured_data") or "", limit=500)
        token_estimate = display_result.get("content_token_estimate")
        fetch_outcome = _clean_tool_text(display_result.get("fetch_outcome") or "", limit=80)
        fetch_diagnostic = _clean_tool_text(display_result.get("fetch_diagnostic") or "", limit=500)
        content_char_count = display_result.get("content_char_count")
        if raw_content and raw_content != display_content:
            entry["raw_content"] = raw_content
        if content_mode:
            entry["content_mode"] = content_mode
        if summary_notice:
            entry["summary_notice"] = summary_notice
        if recovery_hint:
            entry["recovery_hint"] = recovery_hint
        if meta_description:
            entry["meta_description"] = meta_description
        if structured_data:
            entry["structured_data"] = structured_data
        if fetch_outcome:
            entry["fetch_outcome"] = fetch_outcome
        if fetch_diagnostic:
            entry["fetch_diagnostic"] = fetch_diagnostic
        if display_result.get("cleanup_applied"):
            entry["cleanup_applied"] = True
        if isinstance(token_estimate, int) and token_estimate >= 0:
            entry["content_token_estimate"] = token_estimate
        if isinstance(content_char_count, int) and content_char_count >= 0:
            entry["content_char_count"] = content_char_count
    elif tool_name == "fetch_url_summarized" and isinstance(result, dict):
        focus = _clean_tool_text(result.get("focus") or tool_args.get("focus") or "", limit=260)
        model = _clean_tool_text(result.get("model") or "", limit=120)
        content_char_count = result.get("content_char_count")
        if focus:
            entry["focus"] = focus
        if model:
            entry["model"] = model
        if isinstance(content_char_count, int) and content_char_count >= 0:
            entry["content_char_count"] = content_char_count
    elif tool_name == "sub_agent" and isinstance(result, dict):
        model = _clean_tool_text(result.get("model") or "", limit=120)
        error = _clean_tool_text(result.get("error") or "", limit=280)
        if model:
            entry["model"] = model
        if error:
            entry["error"] = error
    return entry


def _copy_tool_output_entry(entry: dict) -> dict:
    copied = dict(entry)
    if isinstance(entry.get("tool_args"), dict):
        copied["tool_args"] = dict(entry["tool_args"])
    if isinstance(entry.get("storage_entry"), dict):
        copied["storage_entry"] = dict(entry["storage_entry"])
    transcript_result = entry.get("transcript_result")
    if isinstance(transcript_result, dict):
        copied["transcript_result"] = dict(transcript_result)
    elif isinstance(transcript_result, list):
        copied["transcript_result"] = list(transcript_result)
    return copied


def _build_budget_compacted_transcript_result(entry: dict, char_limit: int, ultra_compact: bool = False):
    tool_name = str(entry.get("tool_name") or "").strip()
    tool_args = entry.get("tool_args") if isinstance(entry.get("tool_args"), dict) else {}
    transcript_result = entry.get("transcript_result")
    result = entry.get("result")
    summary = _clean_tool_text(entry.get("summary") or "", limit=120 if ultra_compact else 200)
    recovery_hint = _clean_tool_text(_build_recovery_hint_for_tool(tool_name, tool_args), limit=220)

    if tool_name == "fetch_url" and isinstance(result, dict):
        source_result = transcript_result if isinstance(transcript_result, dict) else result
        compacted = {
            "url": source_result.get("url") or result.get("url") or tool_args.get("url") or "",
            "title": source_result.get("title") or result.get("title") or "",
            "content_format": source_result.get("content_format") or result.get("content_format") or "html",
            "content": _clean_tool_text(
                source_result.get("content") or result.get("content") or "",
                limit=max(80, char_limit),
            ),
            "content_mode": "budget_brief" if ultra_compact else "budget_compact",
            "summary_notice": _clean_tool_text(source_result.get("summary_notice") or "", limit=260),
            "fetch_diagnostic": _clean_tool_text(source_result.get("fetch_diagnostic") or "", limit=260),
            "budget_notice": "Prompt budget required extra compaction for this tool result.",
        }
        clip_strategy = _clean_tool_text(source_result.get("clip_strategy") or "", limit=80)
        meta_description = _clean_tool_text(
            source_result.get("meta_description") or result.get("meta_description") or "",
            limit=220,
        )
        structured_data = _clean_tool_text(
            source_result.get("structured_data") or result.get("structured_data") or "",
            limit=320 if ultra_compact else 520,
        )
        outline = source_result.get("outline") if isinstance(source_result.get("outline"), list) else None
        if meta_description:
            compacted["meta_description"] = meta_description
        if structured_data and not ultra_compact:
            compacted["structured_data"] = structured_data
        if outline and not ultra_compact:
            compacted["outline"] = outline[:8]
        if clip_strategy:
            compacted["clip_strategy"] = clip_strategy
        if recovery_hint:
            compacted["recovery_hint"] = recovery_hint
        return compacted

    serialized = (
        transcript_result
        if isinstance(transcript_result, str)
        else _serialize_tool_message_content(transcript_result if transcript_result is not None else result)
    )
    parts = []
    if summary:
        parts.append(f"Summary: {summary}")
    parts.append("Prompt-budget compacted result.")
    if recovery_hint:
        parts.append(f"Recovery: {recovery_hint}")
    excerpt = _clean_tool_text(serialized, limit=max(80, char_limit))
    if excerpt and excerpt != summary:
        parts.append(f"{'Brief' if ultra_compact else 'Excerpt'}: {excerpt}")
    if not parts:
        return _clean_tool_text(serialized, limit=max(80, char_limit))
    return "\n\n".join(parts).strip()


def _build_budget_compacted_execution_error(entry: dict, char_limit: int, ultra_compact: bool = False) -> str:
    tool_name = str(entry.get("tool_name") or "").strip()
    tool_args = entry.get("tool_args") if isinstance(entry.get("tool_args"), dict) else {}
    error_text = _clean_tool_text(
        entry.get("execution_error") or "", limit=max(80, min(char_limit, 140 if ultra_compact else 240))
    )
    recovery_hint = _clean_tool_text(
        _build_recovery_hint_for_tool(tool_name, tool_args), limit=180 if ultra_compact else 220
    )

    parts = []
    if error_text:
        parts.append(error_text)
    if recovery_hint:
        parts.append(f"Recovery: {recovery_hint}")
    if not parts:
        parts.append("Tool execution failed.")
    return "\n".join(parts).strip()


def _render_tool_output_entries(tool_output_entries: list[dict]) -> tuple[list[dict], list[dict], dict | None]:
    tool_messages: list[dict] = []
    transcript_results: list[dict] = []

    for entry in tool_output_entries:
        tool_name = str(entry.get("tool_name") or "unknown").strip() or "unknown"
        tool_args = entry.get("tool_args") if isinstance(entry.get("tool_args"), dict) else {}
        call_id = str(entry.get("call_id") or "").strip()
        if not call_id:
            # tool messages require a non-empty tool_call_id; skip entries missing one.
            continue
        summary = str(entry.get("summary") or "").strip()
        cached = entry.get("cached") is True
        execution_error = str(entry.get("execution_error") or "").strip()

        if execution_error:
            tool_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": _serialize_tool_message_content({"ok": False, "error": execution_error}),
                }
            )
            transcript_item = {
                "tool_name": tool_name,
                "arguments": tool_args,
                "ok": False,
                "error": execution_error,
            }
            summary = str(entry.get("summary") or "").strip()
            if summary:
                transcript_item["summary"] = summary
            if cached:
                transcript_item["cached"] = True
            transcript_results.append(transcript_item)
            continue

        transcript_result = entry.get("transcript_result")
        tool_messages.append(
            {
                "role": "tool",
                "tool_call_id": call_id,
                "content": _build_compact_tool_message_content(
                    tool_name,
                    tool_args,
                    entry.get("result"),
                    summary,
                    transcript_result=transcript_result,
                    storage_entry=entry.get("storage_entry") if isinstance(entry.get("storage_entry"), dict) else None,
                ),
            }
        )
        transcript_item = {
            "tool_name": tool_name,
            "arguments": tool_args,
            "ok": bool(entry.get("ok", True)),
            "summary": summary,
            "result": transcript_result,
        }
        if cached:
            transcript_item["cached"] = True
        if entry.get("compacted_for_budget") is True:
            transcript_item["compacted_for_budget"] = True
        transcript_results.append(transcript_item)

    return tool_messages, transcript_results, _build_tool_execution_result_message(transcript_results)


def _apply_tool_output_budget(
    base_messages: list[dict],
    tool_output_entries: list[dict],
    prompt_max_input_tokens: int | None = None,
    context_compaction_threshold: float | None = None,
    fetch_url_token_threshold: int | None = None,
    fetch_url_clip_aggressiveness: int | None = None,
) -> tuple[list[dict], list[dict], dict | None, bool]:
    if not tool_output_entries:
        return [], [], None, False

    if prompt_max_input_tokens is None:
        prompt_max_input_tokens = PROMPT_MAX_INPUT_TOKENS
    if context_compaction_threshold is None:
        context_compaction_threshold = AGENT_CONTEXT_COMPACTION_THRESHOLD

    soft_limit = max(1, int(prompt_max_input_tokens * context_compaction_threshold))

    def _estimate_total_tokens(tool_messages: list[dict], tool_execution_result_message: dict | None) -> int:
        candidate_messages = [*base_messages, *tool_messages]
        if tool_execution_result_message is not None:
            candidate_messages.append(tool_execution_result_message)
        return _estimate_messages_tokens(candidate_messages)

    full_tool_messages, full_transcript_results, full_tool_execution_result_message = _render_tool_output_entries(
        tool_output_entries
    )
    if _estimate_total_tokens(full_tool_messages, full_tool_execution_result_message) <= soft_limit:
        return full_tool_messages, full_transcript_results, full_tool_execution_result_message, False

    available_tokens = max(120, soft_limit - _estimate_messages_tokens(base_messages))
    successful_entries = [entry for entry in tool_output_entries if not str(entry.get("execution_error") or "").strip()]

    per_entry_tokens = max(40, available_tokens // max(1, len(successful_entries)))
    compact_char_limit = max(160, min(900, per_entry_tokens * 4))
    fetch_char_limit = max(240, min(FETCH_SUMMARY_MAX_CHARS, per_entry_tokens * 5))
    base_threshold = _normalize_fetch_token_threshold(fetch_url_token_threshold)
    base_aggressiveness = _normalize_fetch_clip_aggressiveness(fetch_url_clip_aggressiveness)

    compacted_entries: list[dict] = []
    for original_entry in tool_output_entries:
        entry = _copy_tool_output_entry(original_entry)
        if str(entry.get("execution_error") or "").strip():
            entry["execution_error"] = _build_budget_compacted_execution_error(entry, compact_char_limit)
            entry["summary"] = entry["execution_error"]
            entry["compacted_for_budget"] = True
            compacted_entries.append(entry)
            continue

        if str(entry.get("tool_name") or "").strip() == "fetch_url" and isinstance(entry.get("result"), dict):
            dynamic_threshold = max(80, min(base_threshold, max(80, per_entry_tokens * 2)))
            entry["transcript_result"] = _prepare_tool_result_for_transcript(
                "fetch_url",
                entry.get("result"),
                fetch_url_token_threshold=dynamic_threshold,
                fetch_url_clip_aggressiveness=min(100, base_aggressiveness + 25),
            )
            fetch_rendered = _build_fetch_tool_message_content(
                entry.get("tool_args") if isinstance(entry.get("tool_args"), dict) else {},
                str(entry.get("summary") or ""),
                entry["transcript_result"] if isinstance(entry.get("transcript_result"), dict) else {},
            )
            if len(fetch_rendered) > max(360, fetch_char_limit):
                entry["transcript_result"] = _build_budget_compacted_transcript_result(entry, fetch_char_limit)
        else:
            entry["transcript_result"] = _build_budget_compacted_transcript_result(entry, compact_char_limit)

        entry["compacted_for_budget"] = True
        compacted_entries.append(entry)

    compact_tool_messages, compact_transcript_results, compact_tool_execution_result_message = (
        _render_tool_output_entries(compacted_entries)
    )
    if _estimate_total_tokens(compact_tool_messages, compact_tool_execution_result_message) <= soft_limit:
        return compact_tool_messages, compact_transcript_results, compact_tool_execution_result_message, True

    ultra_entries: list[dict] = []
    for original_entry in tool_output_entries:
        entry = _copy_tool_output_entry(original_entry)
        if str(entry.get("execution_error") or "").strip():
            entry["execution_error"] = _build_budget_compacted_execution_error(entry, 160, ultra_compact=True)
            entry["summary"] = entry["execution_error"]
            entry["compacted_for_budget"] = True
            ultra_entries.append(entry)
            continue

        entry["summary"] = _clean_tool_text(entry.get("summary") or "", limit=120)
        entry["transcript_result"] = _build_budget_compacted_transcript_result(
            entry,
            200 if str(entry.get("tool_name") or "").strip() == "fetch_url" else 140,
            ultra_compact=True,
        )
        entry["compacted_for_budget"] = True
        ultra_entries.append(entry)

    ultra_tool_messages, ultra_transcript_results, ultra_tool_execution_result_message = _render_tool_output_entries(
        ultra_entries
    )
    return ultra_tool_messages, ultra_transcript_results, ultra_tool_execution_result_message, True


def _prefix_cross_turn_tool_memory_summary(summary: str, fallback: str) -> str:
    prefix = "[Cached from an earlier conversation; not executed in this turn]"
    cleaned_summary = _clean_tool_text(summary or "", limit=RAG_TOOL_RESULT_SUMMARY_MAX_CHARS)
    if cleaned_summary:
        if cleaned_summary.startswith(prefix):
            return cleaned_summary
        return f"{prefix} {cleaned_summary}"
    return f"{prefix} {fallback}"


def _lookup_cross_turn_tool_memory(tool_name: str, tool_args: dict) -> tuple[object, str] | None:
    if tool_name in {"fetch_url", "fetch_url_summarized"}:
        url = _tool_input_preview(tool_name, tool_args)
        if not url:
            return None
        try:
            exact_match = get_exact_tool_memory_match(tool_name, url)
        except Exception:
            return None
        if not exact_match:
            return None
        excerpt = _clean_tool_text(exact_match.get("content") or "", limit=RAG_TOOL_RESULT_MAX_TEXT_CHARS)
        if not excerpt:
            return None
        summary = _prefix_cross_turn_tool_memory_summary(
            exact_match.get("summary") or "",
            f"Reused cached {tool_name} result for {url}",
        )
        return excerpt, summary

    if tool_name not in {"fetch_url", "fetch_url_summarized"}:
        return None


def _extract_clarification_event(result: dict) -> dict | None:
    if not isinstance(result, dict):
        return None
    if str(result.get("status") or "").strip() != "needs_user_input":
        return None
    payload = result.get("clarification") if isinstance(result.get("clarification"), dict) else None
    if not payload:
        return None
    text = str(result.get("text") or "").strip() or _build_clarification_text(payload)
    return {
        "type": "clarification_request",
        "clarification": payload,
        "text": text,
    }


def _extract_initial_goal(messages: list[dict]) -> str:
    for message in messages:
        if str(message.get("role") or "").strip() != "user":
            continue
        content = _clean_tool_text(message.get("content") or "", limit=180)
        if content:
            return content
    return ""


def _append_working_state_attempt(working_state: dict, tool_name: str, preview: str) -> None:
    attempts = working_state.setdefault("steps_tried", [])
    entry = {
        "tool_name": str(tool_name or "").strip() or "tool",
        "preview": _clean_tool_text(preview or "", limit=140),
    }
    if attempts and attempts[-1] == entry:
        return
    attempts.append(entry)
    if len(attempts) > 8:
        del attempts[:-8]


def _append_working_state_blocker(working_state: dict, tool_name: str, error: str) -> None:
    blockers = working_state.setdefault("blockers", [])
    entry = {
        "tool_name": str(tool_name or "").strip() or "tool",
        "error": _clean_tool_text(error or "", limit=220),
    }
    if blockers and blockers[-1] == entry:
        return
    blockers.append(entry)
    if len(blockers) > 6:
        del blockers[:-6]


def _append_reasoning_replay_entry(
    reasoning_state: dict, step: int, reasoning_text: str, tool_calls: list[dict] | None
) -> None:
    if not isinstance(reasoning_state, dict):
        return

    cleaned_reasoning = _clean_tool_text(reasoning_text or "", limit=MAX_REASONING_REPLAY_CHARS)
    if not cleaned_reasoning:
        return

    try:
        max_entries = max(MAX_REASONING_REPLAY_ENTRIES, int(reasoning_state.get("max_entries") or 0))
    except (TypeError, ValueError):
        max_entries = MAX_REASONING_REPLAY_ENTRIES

    entries = reasoning_state.setdefault("entries", [])
    tool_names = [
        _normalize_tool_name(str(tool_call.get("name") or "").strip())
        for tool_call in (tool_calls or [])
        if str(tool_call.get("name") or "").strip()
    ]
    entry = {
        "step": max(1, int(step or 0)),
        "reasoning": cleaned_reasoning,
        "tool_names": tool_names,
    }
    if entries and entries[-1] == entry:
        return
    entries.append(entry)
    if len(entries) > max_entries:
        del entries[:-max_entries]


def _build_reasoning_replay_instruction(reasoning_state: dict, current_goal: str = "") -> dict | None:
    if not isinstance(reasoning_state, dict):
        return None

    entries = reasoning_state.get("entries") if isinstance(reasoning_state.get("entries"), list) else []
    if not entries:
        return None

    try:
        max_entries = max(MAX_REASONING_REPLAY_ENTRIES, int(reasoning_state.get("max_entries") or 0))
    except (TypeError, ValueError):
        max_entries = MAX_REASONING_REPLAY_ENTRIES

    parts = [REASONING_REPLAY_MARKER]
    parts.append(
        "This is a compact memory of your own earlier thinking in the current run. Read it as a working note, not as new user input."
    )
    parts.append(
        "These entries capture prior planning and intermediate conclusions. Only actual tool results confirm that an action really happened."
    )
    parts.append(
        "Use it to keep the same plan across tool calls: remember what you already checked, what you concluded, and what the next step was."
    )
    parts.append(
        "If a tool result changes the situation, update the plan instead of restarting from zero. If it does not change the picture, continue where you left off."
    )

    normalized_goal = _clean_tool_text(current_goal or "", limit=180)
    if normalized_goal:
        parts.append(f"Current goal: {normalized_goal}")

    selected_sections = []
    remaining_chars = MAX_REASONING_REPLAY_TOTAL_CHARS
    for entry in reversed(entries[-max_entries:]):
        step_number = max(1, int(entry.get("step") or 0))
        tool_names = [
            str(tool_name or "").strip()
            for tool_name in (entry.get("tool_names") or [])
            if str(tool_name or "").strip()
        ]
        header = f"Step {step_number} reasoning"
        if tool_names:
            header += ": planned tools = " + ", ".join(tool_names)
        section = header + "\n" + str(entry.get("reasoning") or "")
        if selected_sections and len(section) > remaining_chars:
            break
        selected_sections.append(section)
        remaining_chars -= len(section)

    parts.extend(reversed(selected_sections))

    return {"role": "system", "content": "\n\n".join(parts)}


def _build_working_state_instruction(working_state: dict) -> dict | None:
    if not isinstance(working_state, dict):
        return None

    current_goal = _clean_tool_text(working_state.get("current_goal") or "", limit=180)
    attempts = working_state.get("steps_tried") if isinstance(working_state.get("steps_tried"), list) else []
    blockers = working_state.get("blockers") if isinstance(working_state.get("blockers"), list) else []
    if not blockers:
        return None

    parts = ["[AGENT WORKING MEMORY]"]
    if current_goal:
        parts.append(f"Current goal: {current_goal}")
    if attempts:
        lines = []
        for entry in attempts[-5:]:
            tool_name = _clean_tool_text(entry.get("tool_name") or "tool", limit=80)
            preview = _clean_tool_text(entry.get("preview") or "", limit=120)
            line = f"- {tool_name}"
            if preview:
                line += f": {preview}"
            lines.append(line)
        if lines:
            parts.append("Tried in this run:\n" + "\n".join(lines))
    if blockers:
        lines = []
        for entry in blockers[-4:]:
            tool_name = _clean_tool_text(entry.get("tool_name") or "tool", limit=80)
            error = _clean_tool_text(entry.get("error") or "", limit=180)
            line = f"- {tool_name}"
            if error:
                line += f": {error}"
            lines.append(line)
        if lines:
            parts.append("Failed paths to avoid repeating without a concrete reason:\n" + "\n".join(lines))
    parts.append(
        "Prefer a different tool or produce the best available answer if these blockers make repetition low-value."
    )
    return {"role": "system", "content": "\n\n".join(parts)}


def _get_tool_step_limit(tool_name: str, max_steps: int = 5) -> int:
    del tool_name
    try:
        limit = int(max_steps)
    except (TypeError, ValueError):
        limit = max_steps
    return max(1, limit)


def _normalize_parallel_tool_limit(value, default_value: int = DEFAULT_MAX_PARALLEL_TOOLS) -> int:
    try:
        limit = int(value) if value is not None else int(default_value)
    except (TypeError, ValueError):
        limit = int(default_value)
    return max(MAX_PARALLEL_TOOLS_MIN, min(MAX_PARALLEL_TOOLS_MAX, limit))


def run_agent_stream(
    api_messages: list,
    model: str,
    max_steps: int,
    enabled_tool_names: list[str],
    prompt_tool_names: list[str] | None = None,
    max_parallel_tools: int | None = None,
    *,
    buffer_clarification_answers: bool = True,
    temperature: float = 0.7,
    request_parameter_overrides: dict[str, int | float] | None = None,
    fetch_url_token_threshold: int | None = None,
    fetch_url_clip_aggressiveness: int | None = None,
    initial_canvas_documents: list[dict] | None = None,
    initial_canvas_active_document_id: str | None = None,
    canvas_prompt_max_lines: int | None = None,
    canvas_prompt_max_chars: int | None = None,
    canvas_prompt_max_tokens: int | None = None,
    canvas_prompt_code_line_max_chars: int | None = None,
    canvas_prompt_text_line_max_chars: int | None = None,
    canvas_expand_max_lines: int | None = None,
    canvas_scroll_window_lines: int | None = None,
    workspace_runtime_state: dict | None = None,
    agent_context: dict | None = None,
    invocation_log_sink: list[dict] | None = None,
):
    messages = list(api_messages)
    step = 0
    tool_result_cache = {}
    persisted_tool_results = []
    persisted_tool_cache_keys = set()
    reasoning_started = False
    answer_started = False
    pending_answer_separator = False
    fatal_api_error = None
    trace_id = uuid4().hex[:12]
    total_clean_content = ""
    fetch_attempt_counts: dict[str, int] = {}
    tool_call_counts: dict[str, int] = defaultdict(int)
    canvas_modified = False
    successful_canvas_mutation = False
    usage_totals = {
        "prompt_tokens": 0,
        "prompt_cache_hit_tokens": 0,
        "prompt_cache_miss_tokens": 0,
        "prompt_cache_write_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "estimated_input_tokens": 0,
        "input_breakdown": _empty_input_breakdown(),
        "model_call_count": 0,
        "model_calls": [],
        "cache_metrics_estimated": False,
    }
    openrouter_cache_estimate_state = {"previous_cacheable_text": ""}
    normalized_enabled_tool_names = _normalize_tool_name_list(enabled_tool_names)
    ui_hidden_tool_names = set(get_ui_hidden_tool_names(normalized_enabled_tool_names))
    normalized_prompt_tool_names = [
        name
        for name in _normalize_tool_name_list(
            prompt_tool_names if prompt_tool_names is not None else enabled_tool_names
        )
        if name in normalized_enabled_tool_names
    ]
    # Auto-ensure read_scratchpad is available whenever a scratchpad write tool is present.
    # This mirrors the same guard in db.get_active_tool_names() and protects direct callers
    # (e.g. tests) that pass only append_scratchpad/replace_scratchpad without read_scratchpad,
    # which would otherwise cause the system-prompt to reference the tool but the API not to
    # expose it, confusing the model's reasoning.
    _SCRATCHPAD_WRITE_TOOLS = {"append_scratchpad", "replace_scratchpad"}
    if any(name in _SCRATCHPAD_WRITE_TOOLS for name in normalized_enabled_tool_names):
        if "read_scratchpad" not in normalized_enabled_tool_names:
            normalized_enabled_tool_names.append("read_scratchpad")
    if any(name in _SCRATCHPAD_WRITE_TOOLS for name in normalized_prompt_tool_names):
        if "read_scratchpad" not in normalized_prompt_tool_names:
            normalized_prompt_tool_names.append("read_scratchpad")
    normalized_parallel_tool_limit = _normalize_parallel_tool_limit(max_parallel_tools)
    runtime_state = {
        "canvas": create_canvas_runtime_state(
            initial_canvas_documents,
            active_document_id=initial_canvas_active_document_id,
        ),
        "canvas_limits": {
            "expand_max_lines": int(canvas_expand_max_lines or 800),
            "scroll_window_lines": int(canvas_scroll_window_lines or 200),
        },
        "canvas_prompt": {
            "max_lines": int(canvas_prompt_max_lines or 0),
            "max_chars": int(canvas_prompt_max_chars or 0),
            "max_tokens": int(canvas_prompt_max_tokens or 0),
            "code_line_max_chars": int(canvas_prompt_code_line_max_chars or 0),
            "text_line_max_chars": int(canvas_prompt_text_line_max_chars or 0),
        },
        "workspace": workspace_runtime_state
        if isinstance(workspace_runtime_state, dict)
        else create_workspace_runtime_state(),
        "invocation_log_sink": invocation_log_sink if isinstance(invocation_log_sink, list) else None,
    }
    runtime_state["_accumulated_messages"] = messages
    runtime_state["agent_context"] = {
        "model": str(model or "").strip(),
        "enabled_tool_names": normalized_enabled_tool_names,
        "prompt_tool_names": normalized_prompt_tool_names,
        "max_parallel_tools": normalized_parallel_tool_limit,
        "sub_agent_depth": _coerce_int_range((agent_context or {}).get("sub_agent_depth"), 0, 0, 8),
        "conversation_id": _coerce_int_range((agent_context or {}).get("conversation_id"), 0, 0, 2_147_483_647),
        "source_message_id": _coerce_int_range((agent_context or {}).get("source_message_id"), 0, 0, 2_147_483_647),
        "cancel_event": (agent_context or {}).get("cancel_event"),
        "cancel_reason": str((agent_context or {}).get("cancel_reason") or "").strip() or USER_CANCELLED_ERROR_TEXT,
    }
    _raise_if_agent_cancelled(runtime_state.get("agent_context"))
    working_state = {
        "current_goal": _extract_initial_goal(messages),
        "steps_tried": [],
        "blockers": [],
    }
    try:
        reasoning_replay_entry_limit = max(MAX_REASONING_REPLAY_ENTRIES, int(max_steps or 0))
    except (TypeError, ValueError):
        reasoning_replay_entry_limit = MAX_REASONING_REPLAY_ENTRIES
    reasoning_state = {
        "entries": [],
        "max_entries": reasoning_replay_entry_limit,
    }
    model_settings = get_app_settings()

    def _uses_default_runtime_setting(key: str) -> bool:
        raw_value = model_settings.get(key)
        if raw_value in (None, ""):
            return True
        return str(raw_value).strip() == str(DEFAULT_SETTINGS.get(key, "")).strip()

    configured_prompt_max_input_tokens = (
        PROMPT_MAX_INPUT_TOKENS
        if _uses_default_runtime_setting("prompt_max_input_tokens")
        else get_prompt_max_input_tokens(model_settings)
    )
    configured_context_compaction_threshold = (
        AGENT_CONTEXT_COMPACTION_THRESHOLD
        if _uses_default_runtime_setting("context_compaction_threshold")
        else get_context_compaction_threshold(model_settings)
    )
    configured_context_compaction_keep_recent_rounds = (
        AGENT_CONTEXT_COMPACTION_KEEP_RECENT_ROUNDS
        if _uses_default_runtime_setting("context_compaction_keep_recent_rounds")
        else get_context_compaction_keep_recent_rounds(model_settings)
    )
    model_target = resolve_model_target(model, model_settings)
    native_reasoning_continuation = model_target_supports_native_reasoning_continuation(model_target)
    pricing = get_model_pricing(model, model_settings)
    pricing_known = has_known_model_pricing(model, model_settings)

    def build_tool_capture_event() -> dict:
        current_canvas_snapshot = get_canvas_runtime_snapshot(runtime_state.get("canvas"))
        current_canvas_documents = current_canvas_snapshot.get("documents") or []
        active_canvas_document_id = current_canvas_snapshot.get("active_document_id")
        sub_agent_traces = (
            runtime_state.get("sub_agent_traces") if isinstance(runtime_state.get("sub_agent_traces"), list) else []
        )
        visible_tool_results = [
            entry
            for entry in persisted_tool_results
            if str((entry or {}).get("tool_name") or "").strip() not in ui_hidden_tool_names
        ]
        # Compute hash from backend runtime state after mutations to ensure UI-backend sync
        canvas_content_hash = compute_canvas_content_hash(runtime_state.get("canvas")) if canvas_modified else None
        return {
            "type": "tool_capture",
            "tool_results": visible_tool_results,
            "canvas_documents": current_canvas_documents,
            "active_document_id": active_canvas_document_id,
            "canvas_viewports": current_canvas_snapshot.get("viewports") or {},
            "canvas_modified": canvas_modified,
            "successful_canvas_mutation": successful_canvas_mutation,
            "canvas_cleared": canvas_modified and not current_canvas_documents,
            "canvas_content_hash": canvas_content_hash,
            "sub_agent_traces": sub_agent_traces,
        }

    _trace_agent_event(
        "agent_run_started",
        trace_id=trace_id,
        model=model,
        max_steps=max_steps,
        enabled_tool_names=enabled_tool_names,
        prompt_tool_names=normalized_prompt_tool_names,
        max_parallel_tools=normalized_parallel_tool_limit,
        api_messages=_summarize_messages_for_log(messages),
        log_path=AGENT_TRACE_LOG_PATH,
        raw_fields={
            "messages": messages,
            "enabled_tool_names": normalized_enabled_tool_names,
            "prompt_tool_names": normalized_prompt_tool_names,
        },
    )

    def add_usage(usage):
        if not usage:
            return {
                "prompt_tokens": 0,
                "prompt_cache_hit_tokens": 0,
                "prompt_cache_miss_tokens": 0,
                "prompt_cache_write_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "received": False,
                "cache_hit_present": False,
                "cache_miss_present": False,
                "cache_write_present": False,
                "cache_metrics_present": False,
            }

        metrics = _extract_usage_metrics(usage)
        prompt_tokens = metrics["prompt_tokens"]
        prompt_cache_hit_tokens = metrics["prompt_cache_hit_tokens"]
        prompt_cache_miss_tokens = metrics["prompt_cache_miss_tokens"]
        prompt_cache_write_tokens = metrics["prompt_cache_write_tokens"]
        completion_tokens = metrics["completion_tokens"]
        total_tokens = metrics["total_tokens"]
        return {
            "prompt_tokens": prompt_tokens,
            "prompt_cache_hit_tokens": prompt_cache_hit_tokens,
            "prompt_cache_miss_tokens": prompt_cache_miss_tokens,
            "prompt_cache_write_tokens": prompt_cache_write_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "received": any(
                value > 0
                for value in (
                    prompt_tokens,
                    prompt_cache_hit_tokens,
                    prompt_cache_miss_tokens,
                    prompt_cache_write_tokens,
                    completion_tokens,
                    total_tokens,
                )
            )
            or bool(metrics.get("usage_fields_present")),
            "cache_hit_present": bool(metrics.get("cache_hit_present")),
            "cache_miss_present": bool(metrics.get("cache_miss_present")),
            "cache_write_present": bool(metrics.get("cache_write_present")),
            "cache_metrics_present": bool(metrics.get("cache_metrics_present")),
        }

    def calculate_cost(
        prompt_tokens,
        completion_tokens,
        prompt_cache_hit_tokens=0,
        prompt_cache_miss_tokens=None,
        prompt_cache_write_tokens=0,
    ):
        prompt_tokens = _coerce_usage_int(prompt_tokens)
        completion_tokens = _coerce_usage_int(completion_tokens)
        prompt_cache_hit_tokens = _coerce_usage_int(prompt_cache_hit_tokens)
        prompt_cache_write_tokens = _coerce_usage_int(prompt_cache_write_tokens)
        if prompt_cache_miss_tokens is None:
            prompt_cache_miss_tokens = (
                prompt_tokens if prompt_cache_hit_tokens <= 0 else max(0, prompt_tokens - prompt_cache_hit_tokens)
            )
        else:
            prompt_cache_miss_tokens = _coerce_usage_int(prompt_cache_miss_tokens)
            accounted_prompt_tokens = prompt_cache_hit_tokens + prompt_cache_miss_tokens
            if prompt_tokens > accounted_prompt_tokens:
                prompt_cache_miss_tokens += prompt_tokens - accounted_prompt_tokens

        cache_hit_input_rate = pricing.get("input_cache_hit", pricing["input"]) or pricing["input"]
        cache_write_input_rate = pricing.get("input_cache_write", pricing["input"]) or pricing["input"]
        input_cost = (prompt_cache_hit_tokens / 1_000_000) * cache_hit_input_rate
        input_cost += (prompt_cache_write_tokens / 1_000_000) * cache_write_input_rate
        input_cost += (prompt_cache_miss_tokens / 1_000_000) * pricing["input"]
        output_cost = (completion_tokens / 1_000_000) * pricing["output"]
        return round(input_cost + output_cost, 6)

    def _filter_deleted_tool_results(msg_list: list[dict]) -> list[dict]:
        deleted_ids = (
            runtime_state.get("deleted_tool_call_ids")
            if isinstance(runtime_state.get("deleted_tool_call_ids"), set)
            else set()
        )
        if not deleted_ids:
            return msg_list
        filtered = []
        for msg in msg_list:
            if isinstance(msg, dict) and msg.get("role") == "tool":
                if str(msg.get("tool_call_id") or "").strip() in deleted_ids:
                    continue
            filtered.append(msg)
        return filtered

    def apply_context_compaction(extra_messages: list[dict] | None = None, reason: str = "", force: bool = False):
        nonlocal messages
        extra_messages = list(extra_messages or [])
        filtered_messages = _filter_deleted_tool_results(messages)
        turn_messages = [*filtered_messages, *extra_messages]
        threshold = max(1, int(configured_prompt_max_input_tokens * configured_context_compaction_threshold))
        before_tokens = _estimate_messages_tokens(turn_messages)
        before_message_count = len(turn_messages)
        before_exchange_count = _count_exchange_blocks(messages)
        if not force and before_tokens <= threshold:
            return turn_messages, False

        target_budget = max(1, int(configured_prompt_max_input_tokens * 0.75))
        configured_keep_recent = max(0, int(configured_context_compaction_keep_recent_rounds))
        if force:
            keep_recent_candidates = list(range(max(0, configured_keep_recent - 1), -1, -1)) or [0]
        else:
            keep_recent_candidates = [configured_keep_recent]

        compacted_messages = None
        chosen_keep_recent = None
        chosen_tokens = None
        for keep_recent in keep_recent_candidates:
            candidate_messages = _try_compact_messages(
                messages,
                target_budget,
                keep_recent=keep_recent,
            )
            if candidate_messages is None:
                continue
            candidate_turn_messages = [*candidate_messages, *extra_messages]
            candidate_tokens = _estimate_messages_tokens(candidate_turn_messages)
            if chosen_tokens is None or candidate_tokens < chosen_tokens:
                compacted_messages = candidate_messages
                chosen_keep_recent = keep_recent
                chosen_tokens = candidate_tokens
            if candidate_tokens <= target_budget:
                break

        if compacted_messages is None:
            return turn_messages, False

        filtered_compacted = _filter_deleted_tool_results(compacted_messages)
        messages = filtered_compacted
        runtime_state["_accumulated_messages"] = messages
        compacted_turn_messages = [*filtered_compacted, *extra_messages]
        after_tokens = _estimate_messages_tokens(compacted_turn_messages)
        after_message_count = len(compacted_turn_messages)
        after_exchange_count = _count_exchange_blocks(messages)
        _trace_agent_event(
            "context_compacted",
            trace_id=trace_id,
            step=step,
            reason=reason,
            before_tokens=before_tokens,
            after_tokens=after_tokens,
            threshold=threshold,
            force=force,
            before_message_count=before_message_count,
            after_message_count=after_message_count,
            compacted_exchange_count=max(0, before_exchange_count - after_exchange_count),
            merged_message_delta=max(0, before_message_count - after_message_count),
            keep_recent=chosen_keep_recent,
        )
        return compacted_turn_messages, True

    def usage_event():
        prompt_tokens_total = max(0, int(usage_totals["prompt_tokens"] or 0))
        input_breakdown = dict(usage_totals["input_breakdown"])
        estimated_input_tokens = max(0, int(usage_totals["estimated_input_tokens"] or 0))
        provider_usage_partial = any(bool(call.get("missing_provider_usage")) for call in usage_totals["model_calls"])
        if prompt_tokens_total > 0 and not provider_usage_partial:
            input_breakdown = _align_breakdown_to_provider_total(input_breakdown, prompt_tokens_total)
            estimated_input_tokens = prompt_tokens_total
        elif input_breakdown:
            estimated_input_tokens = sum(max(0, int(value or 0)) for value in input_breakdown.values())

        call_usage_summary = _summarize_model_call_usage(
            usage_totals["model_calls"],
            fallback_input_tokens=usage_totals["prompt_tokens"],
        )
        cache_usage_available = (
            usage_totals["prompt_cache_hit_tokens"] > 0 or usage_totals["prompt_cache_miss_tokens"] > 0
        )
        total_cost = None
        if pricing_known:
            total_cost = calculate_cost(
                usage_totals["prompt_tokens"],
                usage_totals["completion_tokens"],
                prompt_cache_hit_tokens=usage_totals["prompt_cache_hit_tokens"],
                prompt_cache_miss_tokens=usage_totals["prompt_cache_miss_tokens"] if cache_usage_available else None,
                prompt_cache_write_tokens=usage_totals["prompt_cache_write_tokens"],
            )
        return {
            "type": "usage",
            "prompt_tokens": prompt_tokens_total,
            "prompt_cache_hit_tokens": usage_totals["prompt_cache_hit_tokens"],
            "prompt_cache_miss_tokens": usage_totals["prompt_cache_miss_tokens"],
            "prompt_cache_write_tokens": usage_totals["prompt_cache_write_tokens"],
            "completion_tokens": usage_totals["completion_tokens"],
            "total_tokens": usage_totals["total_tokens"],
            "estimated_input_tokens": estimated_input_tokens,
            "input_breakdown": input_breakdown,
            "model_call_count": usage_totals["model_call_count"],
            "model_calls": list(usage_totals["model_calls"]),
            "max_input_tokens_per_call": call_usage_summary["max_input_tokens_per_call"],
            "configured_prompt_max_input_tokens": configured_prompt_max_input_tokens,
            "cost": total_cost,
            "cost_available": pricing_known,
            "currency": "USD",
            "model": model,
            "provider": model_target["record"]["provider"],
            "cache_metrics_estimated": usage_totals["cache_metrics_estimated"],
            "provider_usage_partial": provider_usage_partial,
        }

    def remember_tool_result(
        tool_name: str, tool_args: dict, result, summary: str, cache_key: str, transcript_result=None
    ):
        if cache_key in persisted_tool_cache_keys:
            return
        entry = _build_tool_result_storage_entry(
            tool_name, tool_args, result, summary, transcript_result=transcript_result
        )
        if not entry:
            return
        persisted_tool_cache_keys.add(cache_key)
        persisted_tool_results.append(entry)

    def emit_reasoning(reasoning_text: str):
        nonlocal reasoning_started
        if not reasoning_text:
            return
        if not reasoning_started:
            yield {"type": "reasoning_start"}
            reasoning_started = True
        yield {"type": "reasoning_delta", "text": reasoning_text}

    def emit_reasoning_separator():
        if not reasoning_started:
            return
        yield {"type": "reasoning_delta", "text": "\n\n"}

    def emit_answer(answer_text: str):
        nonlocal answer_started, pending_answer_separator
        if pending_answer_separator and str(answer_text or "").strip():
            yield {"type": "answer_delta", "text": "\n\n"}
            pending_answer_separator = False
        if not answer_started:
            yield {"type": "answer_start"}
            answer_started = True
        yield {"type": "answer_delta", "text": answer_text}

    def stream_model_turn(
        messages_to_send: list[dict],
        allow_tools: bool = True,
        *,
        buffer_answer: bool = False,
        call_type: str = "agent_step",
        retry_reason: str | None = None,
    ) -> dict:
        turn_reasoning_emitted = False
        answer_emitted = False
        turn_tools = []
        turn_reasoning_details = []
        provider_usage = {
            "prompt_tokens": 0,
            "prompt_cache_hit_tokens": 0,
            "prompt_cache_miss_tokens": 0,
            "prompt_cache_write_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "received": False,
            "cache_hit_present": False,
            "cache_miss_present": False,
            "cache_write_present": False,
            "cache_metrics_present": False,
        }
        _trace_agent_event(
            "model_turn_started",
            trace_id=trace_id,
            step=step,
            message_count=len(messages_to_send),
            messages=_summarize_messages_for_log(messages_to_send),
        )
        _raise_if_agent_cancelled(runtime_state.get("agent_context"))

        def emit_turn_reasoning(reasoning_text: str):
            nonlocal turn_reasoning_emitted
            if not reasoning_text:
                return
            if not turn_reasoning_emitted and reasoning_started:
                for event in emit_reasoning_separator():
                    yield event
            turn_reasoning_emitted = True
            for event in emit_reasoning(reasoning_text):
                yield event

        def emit_turn_answer(answer_text: str):
            nonlocal answer_emitted
            for event in emit_answer(answer_text):
                answer_emitted = True
                yield event

        request_kwargs = {
            "model": model_target["api_model"],
            "messages": messages_to_send,
            "stream": True,
            "stream_options": {"include_usage": True},
            "temperature": max(0.0, min(2.0, float(temperature))),
        }
        if allow_tools:
            current_canvas_documents = get_canvas_runtime_documents(runtime_state.get("canvas"))
            prompt_enabled_tool_names = enabled_tool_names if prompt_tool_names is None else prompt_tool_names
            workspace_root = get_workspace_root(runtime_state.get("workspace"))
            turn_tools = get_openai_tool_specs(
                prompt_enabled_tool_names,
                canvas_documents=current_canvas_documents,
                clarification_max_questions=get_clarification_max_questions(model_settings),
                search_tool_query_limit=get_search_tool_query_limit(model_settings),
                workspace_root=workspace_root,
            )
            if turn_tools:
                request_kwargs["tools"] = turn_tools
                request_kwargs["tool_choice"] = "auto"
        request_kwargs = apply_chat_parameter_overrides(request_kwargs, request_parameter_overrides)
        request_kwargs = apply_model_target_request_options(request_kwargs, model_target)
        cache_estimate_context = build_openrouter_cache_estimate_context(
            request_kwargs.get("messages"),
            model_target.get("record") if isinstance(model_target, dict) else None,
            model_settings,
        )
        _trace_agent_event(
            "model_request_started",
            trace_id=trace_id,
            step=step,
            call_type=call_type,
            retry_reason=retry_reason,
            model=model_target.get("api_model"),
            raw_fields={
                "request_payload": request_kwargs,
                "messages_to_send": messages_to_send,
                "turn_tools": turn_tools,
            },
        )

        def append_turn_invocation(response_summary, *, request_payload=None):
            _append_model_invocation_log(
                runtime_state.get("invocation_log_sink"),
                agent_context=runtime_state.get("agent_context"),
                step=step,
                call_type=call_type,
                retry_reason=retry_reason,
                model_target=model_target,
                request_payload=request_payload if request_payload is not None else request_kwargs,
                response_summary=response_summary,
            )

        try:
            _raise_if_agent_cancelled(runtime_state.get("agent_context"))
            response = model_target["client"].chat.completions.create(**request_kwargs)
        except Exception as exc:
            append_turn_invocation(
                {
                    "status": "error",
                    "error": str(exc),
                    "usage": {"missing_provider_usage": True},
                }
            )
            # Per Coding Principles: Minimize Forced Retries - Do not use backend override
            # to force repeated failed paths. Allow the model to evaluate the error
            # and reason about next steps rather than injecting a fallback retry.
            raise

        def finalize_call_usage() -> tuple[dict[str, int], int, int]:
            nonlocal provider_usage
            estimated_breakdown, estimated_input_tokens, tool_schema_tokens = _estimate_input_breakdown(
                messages_to_send,
                provider_prompt_tokens=provider_usage["prompt_tokens"] if provider_usage["received"] else None,
                request_tools=turn_tools,
            )
            prompt_token_basis = (
                provider_usage["prompt_tokens"] if provider_usage["prompt_tokens"] > 0 else estimated_input_tokens
            )
            cache_hit_tokens = (
                provider_usage["prompt_cache_hit_tokens"] if provider_usage["cache_hit_present"] else None
            )
            cache_miss_tokens = (
                provider_usage["prompt_cache_miss_tokens"] if provider_usage["cache_miss_present"] else None
            )
            cache_write_tokens = (
                provider_usage["prompt_cache_write_tokens"] if provider_usage["cache_write_present"] else 0
            )
            cache_metrics_estimated = False

            if cache_hit_tokens is None and cache_miss_tokens is None:
                estimated_cache_metrics = _estimate_openrouter_cache_metrics(
                    openrouter_cache_estimate_state,
                    cache_estimate_context,
                    prompt_token_basis,
                )
                if estimated_cache_metrics is not None:
                    cache_hit_tokens = estimated_cache_metrics["prompt_cache_hit_tokens"]
                    cache_miss_tokens = estimated_cache_metrics["prompt_cache_miss_tokens"]
                    cache_metrics_estimated = bool(estimated_cache_metrics["cache_metrics_estimated"])
            else:
                if cache_hit_tokens is None:
                    cache_hit_tokens = max(0, prompt_token_basis - _coerce_usage_int(cache_miss_tokens))
                    cache_metrics_estimated = True
                if cache_miss_tokens is None:
                    cache_miss_tokens = max(0, prompt_token_basis - _coerce_usage_int(cache_hit_tokens))
                    cache_metrics_estimated = True
                accounted_prompt_tokens = _coerce_usage_int(cache_hit_tokens) + _coerce_usage_int(cache_miss_tokens)
                if prompt_token_basis > accounted_prompt_tokens:
                    cache_miss_tokens = _coerce_usage_int(cache_miss_tokens) + (
                        prompt_token_basis - accounted_prompt_tokens
                    )
                    cache_metrics_estimated = True
                if isinstance(cache_estimate_context, dict):
                    openrouter_cache_estimate_state["previous_cacheable_text"] = str(
                        cache_estimate_context.get("cacheable_text") or ""
                    )

            final_cache_hit_tokens = _coerce_usage_int(cache_hit_tokens)
            final_cache_miss_tokens = _coerce_usage_int(cache_miss_tokens)
            final_cache_write_tokens = _coerce_usage_int(cache_write_tokens)

            usage_totals["prompt_tokens"] += provider_usage["prompt_tokens"]
            if provider_usage["received"]:
                usage_totals["prompt_cache_hit_tokens"] += final_cache_hit_tokens
                usage_totals["prompt_cache_miss_tokens"] += final_cache_miss_tokens
                usage_totals["prompt_cache_write_tokens"] += final_cache_write_tokens
            usage_totals["completion_tokens"] += provider_usage["completion_tokens"]
            usage_totals["total_tokens"] += provider_usage["total_tokens"]
            if cache_metrics_estimated:
                usage_totals["cache_metrics_estimated"] = True

            usage_totals["model_call_count"] += 1
            usage_totals["model_calls"].append(
                {
                    "index": usage_totals["model_call_count"],
                    "call_type": call_type,
                    "step": step,
                    "is_retry": bool(retry_reason),
                    "retry_reason": str(retry_reason or "").strip() or None,
                    "message_count": len(messages_to_send),
                    "tool_schema_tokens": tool_schema_tokens,
                    "prompt_tokens": provider_usage["prompt_tokens"] if provider_usage["received"] else None,
                    "prompt_cache_hit_tokens": final_cache_hit_tokens,
                    "prompt_cache_miss_tokens": final_cache_miss_tokens,
                    "prompt_cache_write_tokens": final_cache_write_tokens,
                    "completion_tokens": provider_usage["completion_tokens"] if provider_usage["received"] else None,
                    "total_tokens": provider_usage["total_tokens"] if provider_usage["received"] else None,
                    "estimated_input_tokens": estimated_input_tokens,
                    "input_breakdown": dict(estimated_breakdown),
                    "missing_provider_usage": not provider_usage["received"],
                    "cache_metrics_estimated": cache_metrics_estimated,
                }
            )
            usage_totals["estimated_input_tokens"] += estimated_input_tokens
            for key, value in estimated_breakdown.items():
                usage_totals["input_breakdown"][key] += value
            return estimated_breakdown, estimated_input_tokens, tool_schema_tokens

        try:
            if getattr(response, "choices", None):
                provider_usage = add_usage(getattr(response, "usage", None))
                estimated_breakdown, estimated_input_tokens, tool_schema_tokens = finalize_call_usage()
                message = response.choices[0].message
                reasoning_text, content_text = _extract_reasoning_and_content(message)
                turn_reasoning_details = _merge_reasoning_details([], _read_api_field(message, "reasoning_details", []))
                tool_calls, tool_call_error = _extract_native_tool_calls(message)
                content_text, tool_calls, tool_call_error = _prefer_content_dsml_tool_calls(
                    content_text,
                    tool_calls,
                    tool_call_error,
                )
                _trace_agent_event(
                    "model_turn_completed",
                    trace_id=trace_id,
                    step=step,
                    reasoning_excerpt=reasoning_text,
                    content_excerpt=content_text,
                    tool_calls=tool_calls or [],
                )
                append_turn_invocation(
                    {
                        "status": "ok",
                        "usage": _build_model_invocation_usage_summary(
                            provider_usage,
                            estimated_input_tokens=estimated_input_tokens,
                            estimated_breakdown=estimated_breakdown,
                            tool_schema_tokens=tool_schema_tokens,
                        ),
                        "reasoning_text": reasoning_text,
                        "reasoning_details": turn_reasoning_details,
                        "content_text": content_text,
                        "tool_calls": tool_calls or [],
                        "tool_call_error": str(tool_call_error or "").strip() or None,
                    }
                )
                for event in emit_turn_reasoning(reasoning_text):
                    yield event
                return {
                    "reasoning_text": reasoning_text,
                    "reasoning_details": turn_reasoning_details,
                    "content_text": content_text,
                    "tool_calls": tool_calls,
                    "tool_call_error": tool_call_error,
                    "answer_emitted": answer_emitted,
                    "stream_error": None,
                }

            reasoning_parts = []
            content_parts = []
            buffered_content_deltas = []
            tool_call_parts = []
            content_streaming_live = False
            stream_error = None
            announced_canvas_preview_key = None
            streamed_canvas_content_length = 0
            streamed_canvas_preview_content = None

            try:
                for chunk in response:
                    _raise_if_agent_cancelled(runtime_state.get("agent_context"))
                    reasoning_delta, content_delta, reasoning_details_delta = _extract_stream_delta_texts(chunk)
                    if reasoning_details_delta:
                        turn_reasoning_details = _merge_reasoning_details(
                            turn_reasoning_details, reasoning_details_delta
                        )
                    if reasoning_delta:
                        reasoning_parts.append(reasoning_delta)
                        for event in emit_turn_reasoning(reasoning_delta):
                            yield event
                    if getattr(chunk, "choices", None):
                        delta = getattr(chunk.choices[0], "delta", None)
                        if delta is not None:
                            _merge_stream_tool_call_delta(tool_call_parts, delta)
                            canvas_preview = _build_streaming_canvas_tool_preview(
                                tool_call_parts, runtime_state.get("canvas")
                            )
                            if canvas_preview is not None:
                                preview_tool_name = canvas_preview["tool"]
                                preview_key = str(canvas_preview.get("preview_key") or "").strip()
                                if announced_canvas_preview_key != preview_key:
                                    announced_canvas_preview_key = preview_key
                                    streamed_canvas_content_length = 0
                                    streamed_canvas_preview_content = None
                                    yield {
                                        "type": "canvas_tool_starting",
                                        "tool": preview_tool_name,
                                        "preview_key": preview_key,
                                        "snapshot": canvas_preview["snapshot"],
                                    }
                                preview_content = canvas_preview.get("content")
                                preview_content_mode = (
                                    str(canvas_preview.get("content_mode") or "append").strip().lower()
                                )
                                if preview_content is not None:
                                    if preview_content_mode == "replace":
                                        if preview_content != streamed_canvas_preview_content:
                                            streamed_canvas_preview_content = preview_content
                                            streamed_canvas_content_length = len(preview_content)
                                            yield {
                                                "type": "canvas_content_delta",
                                                "tool": preview_tool_name,
                                                "preview_key": preview_key,
                                                "delta": preview_content,
                                                "snapshot": canvas_preview["snapshot"],
                                                "replace_content": True,
                                            }
                                    elif len(preview_content) > streamed_canvas_content_length:
                                        next_content_delta = preview_content[streamed_canvas_content_length:]
                                        streamed_canvas_content_length = len(preview_content)
                                        streamed_canvas_preview_content = preview_content
                                        if next_content_delta:
                                            yield {
                                                "type": "canvas_content_delta",
                                                "tool": preview_tool_name,
                                                "preview_key": preview_key,
                                                "delta": next_content_delta,
                                                "snapshot": canvas_preview["snapshot"],
                                            }
                    if content_delta:
                        content_parts.append(content_delta)
                        if buffer_answer:
                            buffered_content_deltas.append(content_delta)
                        elif not turn_tools:
                            for event in emit_turn_answer(content_delta):
                                yield event
                        elif content_streaming_live:
                            for event in emit_turn_answer(content_delta):
                                yield event
                        elif _has_meaningful_stream_tool_calls(tool_call_parts):
                            buffered_content_deltas.append(content_delta)
                        else:
                            content_streaming_live = True
                            for event in emit_turn_answer(content_delta):
                                yield event
                    if getattr(chunk, "usage", None):
                        usage_snapshot = add_usage(chunk.usage)
                        provider_usage["prompt_tokens"] += usage_snapshot["prompt_tokens"]
                        provider_usage["prompt_cache_hit_tokens"] += usage_snapshot["prompt_cache_hit_tokens"]
                        provider_usage["prompt_cache_miss_tokens"] += usage_snapshot["prompt_cache_miss_tokens"]
                        provider_usage["prompt_cache_write_tokens"] += usage_snapshot["prompt_cache_write_tokens"]
                        provider_usage["completion_tokens"] += usage_snapshot["completion_tokens"]
                        provider_usage["total_tokens"] += usage_snapshot["total_tokens"]
                        provider_usage["received"] = provider_usage["received"] or usage_snapshot["received"]
                        provider_usage["cache_hit_present"] = (
                            provider_usage["cache_hit_present"] or usage_snapshot["cache_hit_present"]
                        )
                        provider_usage["cache_miss_present"] = (
                            provider_usage["cache_miss_present"] or usage_snapshot["cache_miss_present"]
                        )
                        provider_usage["cache_write_present"] = (
                            provider_usage["cache_write_present"] or usage_snapshot["cache_write_present"]
                        )
                        provider_usage["cache_metrics_present"] = (
                            provider_usage["cache_metrics_present"] or usage_snapshot["cache_metrics_present"]
                        )
            except Exception as exc:
                stream_error = str(exc)
                _trace_agent_event(
                    "model_stream_interrupted",
                    trace_id=trace_id,
                    step=step,
                    error=stream_error,
                    partial_content_excerpt="".join(content_parts),
                )

            final_reasoning = "".join(reasoning_parts).strip()
            final_content = "".join(content_parts).strip()
            tool_calls, tool_call_error = _finalize_stream_tool_calls(tool_call_parts)
            final_content, tool_calls, tool_call_error = _prefer_content_dsml_tool_calls(
                final_content,
                tool_calls,
                tool_call_error,
            )
            estimated_breakdown, estimated_input_tokens, tool_schema_tokens = finalize_call_usage()
            if buffered_content_deltas and not buffer_answer and not tool_calls and not tool_call_error:
                for pending_delta in buffered_content_deltas:
                    for event in emit_turn_answer(pending_delta):
                        yield event

            # MiniMax streaming: capture usage from the stream iterator after iteration ends
            if not provider_usage.get("received"):
                stream_usage = _extract_usage_metrics(getattr(response, "usage", None))
                if stream_usage.get("usage_fields_present"):
                    provider_usage = add_usage(getattr(response, "usage", None))
                    usage_totals["prompt_tokens"] += provider_usage["prompt_tokens"]
                    usage_totals["prompt_cache_hit_tokens"] += provider_usage["prompt_cache_hit_tokens"]
                    usage_totals["prompt_cache_miss_tokens"] += provider_usage["prompt_cache_miss_tokens"]
                    usage_totals["prompt_cache_write_tokens"] += provider_usage["prompt_cache_write_tokens"]
                    usage_totals["completion_tokens"] += provider_usage["completion_tokens"]
                    usage_totals["total_tokens"] += provider_usage["total_tokens"]

                    # Update the existing model_calls record with actual streaming usage
                    if usage_totals["model_calls"]:
                        last_call = usage_totals["model_calls"][-1]
                        last_call.update(
                            {
                                "prompt_tokens": provider_usage["prompt_tokens"],
                                "prompt_cache_hit_tokens": provider_usage["prompt_cache_hit_tokens"],
                                "prompt_cache_miss_tokens": provider_usage["prompt_cache_miss_tokens"],
                                "prompt_cache_write_tokens": provider_usage["prompt_cache_write_tokens"],
                                "completion_tokens": provider_usage["completion_tokens"],
                                "total_tokens": provider_usage["total_tokens"],
                                "missing_provider_usage": not provider_usage["received"],
                                "cache_metrics_estimated": False,
                            }
                        )

            _trace_agent_event(
                "model_turn_completed",
                trace_id=trace_id,
                step=step,
                reasoning_excerpt=final_reasoning,
                content_excerpt=final_content,
                tool_calls=tool_calls or [],
                stream_error=stream_error,
            )
            append_turn_invocation(
                {
                    "status": "stream_error" if stream_error else "ok",
                    "usage": _build_model_invocation_usage_summary(
                        provider_usage,
                        estimated_input_tokens=estimated_input_tokens,
                        estimated_breakdown=estimated_breakdown,
                        tool_schema_tokens=tool_schema_tokens,
                    ),
                    "reasoning_text": final_reasoning,
                    "reasoning_details": turn_reasoning_details,
                    "content_text": final_content,
                    "tool_calls": tool_calls or [],
                    "tool_call_error": str(tool_call_error or "").strip() or None,
                    "stream_error": stream_error,
                }
            )
            return {
                "reasoning_text": final_reasoning,
                "reasoning_details": turn_reasoning_details,
                "content_text": final_content,
                "tool_calls": tool_calls,
                "tool_call_error": tool_call_error,
                "answer_emitted": answer_emitted,
                "stream_error": stream_error,
            }
        finally:
            _close_model_response(response)

    pending_step_retry_reason: str | None = None
    while step < max_steps:
        _raise_if_agent_cancelled(runtime_state.get("agent_context"))
        step += 1
        runtime_state["agent_context"]["current_step"] = step
        yield {"type": "step_started", "step": step, "max_steps": max_steps}
        _trace_agent_event("agent_step_started", trace_id=trace_id, step=step, max_steps=max_steps)
        context_compacted_this_step = False
        needs_separator_for_sync = pending_answer_separator
        step_retry_reason = pending_step_retry_reason
        pending_step_retry_reason = None
        reasoning_replay_instruction = None
        if not (native_reasoning_continuation and _has_native_reasoning_details(messages)):
            reasoning_replay_instruction = _build_reasoning_replay_instruction(
                reasoning_state,
                current_goal=working_state.get("current_goal") or "",
            )
        working_memory_instruction = _build_working_state_instruction(working_state)
        extra_messages = []
        if reasoning_replay_instruction:
            extra_messages.append(reasoning_replay_instruction)
            _trace_agent_event(
                "reasoning_replay_injected",
                trace_id=trace_id,
                step=step,
                entry_count=len(reasoning_state.get("entries") or []),
            )
        if working_memory_instruction:
            extra_messages.append(working_memory_instruction)
        turn_messages, _ = apply_context_compaction(extra_messages, reason="pre_model_turn")
        turn_messages = _strip_intermediate_tool_call_content(turn_messages)

        try:
            turn_result = yield from stream_model_turn(
                turn_messages,
                buffer_answer=buffer_clarification_answers
                and "ask_clarifying_question" in set(normalized_prompt_tool_names),
                call_type="agent_step",
                retry_reason=step_retry_reason,
            )
        except Exception as exc:
            fatal_api_error = str(exc)
            if _is_context_overflow_error(fatal_api_error) != "none" and not context_compacted_this_step:
                _, compacted = apply_context_compaction(extra_messages, reason="reactive_model_turn", force=True)
                if compacted:
                    context_compacted_this_step = True
                    _trace_agent_event(
                        "context_overflow_recovered",
                        trace_id=trace_id,
                        step=step,
                        phase="main_loop",
                        source="model_turn_exception",
                    )
                    pending_step_retry_reason = "context_overflow_recovery"
                    step -= 1
                    continue
                _trace_agent_event(
                    "context_overflow_unrecoverable",
                    trace_id=trace_id,
                    step=step,
                    phase="main_loop",
                    source="model_turn_exception",
                    error=fatal_api_error,
                    message_count=len(turn_messages),
                )
                fatal_api_error = _build_context_overflow_recovery_error(turn_messages)
            _trace_agent_event("agent_api_error", trace_id=trace_id, step=step, error=fatal_api_error)
            yield {"type": "tool_error", "step": step, "tool": "api", "error": fatal_api_error}
            break

        reasoning_text = turn_result.get("reasoning_text") or ""
        reasoning_details = _normalize_reasoning_details(turn_result.get("reasoning_details"))
        content_text = turn_result.get("content_text") or ""
        tool_calls = turn_result.get("tool_calls")
        tool_call_error = turn_result.get("tool_call_error")
        stream_error = turn_result.get("stream_error")

        if tool_call_error:
            _trace_agent_event(
                "tool_parse_error",
                trace_id=trace_id,
                step=step,
                parse_error=tool_call_error,
                content_excerpt=content_text,
            )
            yield {"type": "tool_error", "step": step, "tool": "parser", "error": tool_call_error}
            break

        # If content was buffered (not streamed live) because the model co-produced tool
        # calls in the same turn, emit it now before tool execution so the user sees
        # any pre-tool commentary the model generated.
        answer_emitted = bool(turn_result.get("answer_emitted"))
        if content_text.strip() and not answer_emitted and tool_calls and not tool_call_error:
            for event in emit_answer(content_text):
                yield event

        if content_text and not tool_calls:
            if needs_separator_for_sync and content_text.strip():
                total_clean_content += "\n\n"
            total_clean_content += content_text

        _trace_agent_event(
            "tool_parse_result",
            trace_id=trace_id,
            step=step,
            tool_calls=tool_calls or [],
            content_excerpt=content_text,
        )

        if not tool_calls:
            if content_text:
                _trace_agent_event("final_answer_received", trace_id=trace_id, step=step, content_excerpt=content_text)
                if not answer_started:
                    for event in emit_answer(content_text):
                        yield event
                if stream_error and not _is_truncated_stream_disconnect_error(stream_error):
                    yield {"type": "tool_error", "step": step, "tool": "api", "error": stream_error}
                if usage_totals["total_tokens"]:
                    yield usage_event()
                yield build_tool_capture_event()
                yield {"type": "done"}
                return

            if stream_error:
                if _is_context_overflow_error(stream_error) != "none" and not context_compacted_this_step:
                    _, compacted = apply_context_compaction(extra_messages, reason="reactive_stream_error", force=True)
                    if compacted:
                        context_compacted_this_step = True
                        _trace_agent_event(
                            "context_overflow_recovered",
                            trace_id=trace_id,
                            step=step,
                            phase="main_loop",
                            source="stream_error",
                        )
                        pending_step_retry_reason = "context_overflow_recovery"
                        step -= 1
                        continue
                    _trace_agent_event(
                        "context_overflow_unrecoverable",
                        trace_id=trace_id,
                        step=step,
                        phase="main_loop",
                        source="stream_error",
                        error=stream_error,
                        message_count=len(turn_messages),
                    )
                    fatal_api_error = _build_context_overflow_recovery_error(turn_messages)
                else:
                    fatal_api_error = stream_error
                _trace_agent_event("agent_api_error", trace_id=trace_id, step=step, error=fatal_api_error)
                yield {"type": "tool_error", "step": step, "tool": "api", "error": fatal_api_error}
                break

            _trace_agent_event("missing_final_answer", trace_id=trace_id, step=step)
            yield {
                "type": "tool_error",
                "step": step,
                "tool": "agent",
                "error": "The model returned no final answer content. Retrying and waiting for a final answer.",
            }
            if not _has_missing_final_answer_instruction(messages):
                messages.append(_build_missing_final_answer_instruction())
            pending_step_retry_reason = "missing_final_answer"
            continue

        _append_reasoning_replay_entry(reasoning_state, step, reasoning_text, tool_calls)
        if reasoning_text:
            _trace_agent_event(
                "reasoning_replay_updated",
                trace_id=trace_id,
                step=step,
                chars=len(reasoning_text),
                tool_names=[
                    _normalize_tool_name(str(tool_call.get("name") or "").strip())
                    for tool_call in (tool_calls or [])
                    if str(tool_call.get("name") or "").strip()
                ],
            )
        assistant_tool_call_message = _build_assistant_tool_call_message(content_text, tool_calls, reasoning_details)
        messages.append(assistant_tool_call_message)
        if content_text.strip() and answer_started:
            pending_answer_separator = True
        transcript_results = []
        tool_messages = []
        tool_output_entries = []
        canvas_context_refresh_needed = False

        # ---- Phase 1: validate, pre-check, build execution slots (sequential) ----
        slots = []
        for call_index, tool_call in enumerate(tool_calls, start=1):
            tool_name = _normalize_tool_name(tool_call["name"])
            tool_args = tool_call["arguments"]
            call_id = str(tool_call.get("id") or f"step-{step}-call-{call_index}-{tool_name}")
            slot = {
                "call_index": call_index,
                "tool_name": tool_name,
                "tool_args": tool_args,
                "call_id": call_id,
                "preview": "",
                "cache_key": "",
                "has_step_update": False,
            }

            if tool_name not in enabled_tool_names:
                slot["kind"] = "error"
                slot["error"] = f"Tool not available in current context: {tool_name}"
                slots.append(slot)
                continue

            validation_error = _validate_tool_arguments(tool_name, tool_args)
            if validation_error:
                slot["kind"] = "error"
                slot["error"] = validation_error
                slots.append(slot)
                continue

            cache_key = build_tool_cache_key(tool_name, tool_args)
            slot["cache_key"] = cache_key
            preview = _truncate_preview_text(_tool_input_preview(tool_name, tool_args), limit=80)
            slot["preview"] = preview

            if tool_name == "fetch_url":
                fetch_url_val = str(tool_args.get("url") or "").strip()
                fetch_attempt_counts[fetch_url_val] = fetch_attempt_counts.get(fetch_url_val, 0) + 1
                _trace_agent_event(
                    "fetch_url_requested",
                    trace_id=trace_id,
                    step=step,
                    url=fetch_url_val,
                    attempt_count=fetch_attempt_counts[fetch_url_val],
                    repeated=fetch_attempt_counts[fetch_url_val] > 1,
                    call_id=call_id,
                )
                if fetch_attempt_counts[fetch_url_val] > 1:
                    _trace_agent_event(
                        "duplicate_fetch_attempt",
                        trace_id=trace_id,
                        step=step,
                        url=fetch_url_val,
                        attempt_count=fetch_attempt_counts[fetch_url_val],
                        call_id=call_id,
                    )

            _trace_agent_event(
                "tool_call_started",
                trace_id=trace_id,
                step=step,
                tool_name=tool_name,
                tool_args=tool_args,
                preview=preview,
                cache_key=cache_key,
                raw_fields={"tool_args": tool_args},
            )
            _append_working_state_attempt(working_state, tool_name, preview)
            slot["has_step_update"] = True

            tool_limit = _get_tool_step_limit(tool_name, max_steps)
            step_key = f"{step}"
            tool_step_key = f"{tool_name}:{step_key}"
            step_tool_call_counts = runtime_state.setdefault("step_tool_call_counts", {})
            if step_tool_call_counts.get(tool_step_key, 0) >= tool_limit:
                error = f"Per-tool step limit reached for {tool_name}. Try a different tool or produce the best available answer."
                _append_working_state_blocker(working_state, tool_name, error)
                slot["kind"] = "error"
                slot["error"] = error
                slots.append(slot)
                continue
            step_tool_call_counts[tool_step_key] = step_tool_call_counts.get(tool_step_key, 0) + 1

            if _is_session_cacheable_tool(tool_name) and cache_key in tool_result_cache:
                cached_result, cached_summary = tool_result_cache[cache_key]
                transcript_result = _prepare_tool_result_for_transcript(
                    tool_name,
                    cached_result,
                    fetch_url_token_threshold=fetch_url_token_threshold,
                    fetch_url_clip_aggressiveness=fetch_url_clip_aggressiveness,
                )
                remember_tool_result(
                    tool_name,
                    tool_args,
                    cached_result,
                    cached_summary,
                    cache_key,
                    transcript_result=transcript_result,
                )
                storage_entry = _build_tool_result_storage_entry(
                    tool_name,
                    tool_args,
                    cached_result,
                    cached_summary,
                    transcript_result=transcript_result,
                )
                _trace_agent_event(
                    "tool_cache_hit",
                    trace_id=trace_id,
                    step=step,
                    tool_name=tool_name,
                    tool_args=tool_args,
                    summary=cached_summary,
                    transcript_result=transcript_result,
                )
                slot["kind"] = "session_cache_hit"
                slot["result"] = cached_result
                slot["summary"] = cached_summary
                slot["transcript_result"] = transcript_result
                slot["storage_entry"] = storage_entry
                slots.append(slot)
                continue

            cross_turn_cache_hit = _lookup_cross_turn_tool_memory(tool_name, tool_args)
            if cross_turn_cache_hit is not None:
                cached_excerpt, cached_summary = cross_turn_cache_hit
                _trace_agent_event(
                    "tool_memory_cache_hit",
                    trace_id=trace_id,
                    step=step,
                    tool_name=tool_name,
                    tool_args=tool_args,
                    summary=cached_summary,
                )
                slot["kind"] = "memory_cache_hit"
                slot["result"] = cached_excerpt
                slot["summary"] = cached_summary
                slot["transcript_result"] = cached_excerpt
                slots.append(slot)
                continue

            slot["kind"] = "execute"
            slot["is_canvas"] = tool_name in CANVAS_TOOL_NAMES
            slots.append(slot)

        hidden_tool_call_ids = {
            str(slot.get("call_id") or "").strip()
            for slot in slots
            if str(slot.get("tool_name") or "").strip() in ui_hidden_tool_names
        }

        def _build_public_tool_history_messages(assistant_message: dict, tool_msgs: list[dict]) -> list[dict]:
            if not hidden_tool_call_ids:
                return [assistant_message, *tool_msgs]

            visible_tool_calls = [
                tool_call
                for tool_call in (
                    assistant_message.get("tool_calls") if isinstance(assistant_message.get("tool_calls"), list) else []
                )
                if str(tool_call.get("id") or "").strip() not in hidden_tool_call_ids
            ]

            public_messages: list[dict] = []
            public_assistant_message = dict(assistant_message)
            if visible_tool_calls:
                public_assistant_message["tool_calls"] = visible_tool_calls
            else:
                public_assistant_message.pop("tool_calls", None)

            if str(public_assistant_message.get("content") or "").strip() or public_assistant_message.get("tool_calls"):
                public_messages.append(public_assistant_message)

            public_messages.extend(
                message
                for message in tool_msgs
                if str(message.get("tool_call_id") or "").strip() not in hidden_tool_call_ids
            )
            return public_messages

        # ---- Phase 1b: yield step_update events for all non-error, non-disabled calls ----
        for slot in slots:
            if slot.get("has_step_update") and str(slot.get("tool_name") or "").strip() not in ui_hidden_tool_names:
                yield {
                    "type": "step_update",
                    "step": step,
                    "tool": slot["tool_name"],
                    "preview": slot["preview"],
                    "call_id": slot["call_id"],
                }

        # ---- Phase 2: execute pending slots (parallel for safe read-only tools, sequential for mutators) ----
        pending_slots = [s for s in slots if s["kind"] == "execute"]
        if pending_slots:
            _raise_if_agent_cancelled(runtime_state.get("agent_context"))
            parallel_slots = [
                s for s in pending_slots if _is_parallel_safe_tool_call(s["tool_name"], s.get("tool_args") or {})
            ]
            sequential_slots = [
                s for s in pending_slots if not _is_parallel_safe_tool_call(s["tool_name"], s.get("tool_args") or {})
            ]

            # Canvas dependency barrier: when the batch contains both canvas
            # mutations and canvas reads, the reads must not run in the
            # parallel pool (they would observe stale pre-mutation state).
            # Move them to the sequential queue so they execute *after* the
            # mutations in their original request order.
            _has_canvas_mutation = any(s["tool_name"] in CANVAS_MUTATION_TOOL_NAMES for s in pending_slots)
            if _has_canvas_mutation:
                _canvas_read_slots = [s for s in parallel_slots if s["tool_name"] in CANVAS_ALL_READ_TOOL_NAMES]
                if _canvas_read_slots:
                    parallel_slots = [s for s in parallel_slots if s not in _canvas_read_slots]
                    sequential_slots.extend(_canvas_read_slots)

            sub_agent_parallel_slots = [s for s in parallel_slots if s["tool_name"] == "sub_agent"]
            direct_parallel_slots = [s for s in parallel_slots if s["tool_name"] != "sub_agent"]
            buffered_sub_agent_slots = (
                sub_agent_parallel_slots
                if sub_agent_parallel_slots and (len(sub_agent_parallel_slots) > 1 or bool(direct_parallel_slots))
                else []
            )
            if not buffered_sub_agent_slots and sub_agent_parallel_slots:
                sequential_slots.extend(sub_agent_parallel_slots)
            parallel_slots = [*direct_parallel_slots, *buffered_sub_agent_slots]

            if len(parallel_slots) > 1 and normalized_parallel_tool_limit > 1:

                def _run_slot(s):
                    try:
                        res, summ, events = _execute_streaming_tool_with_event_buffer(
                            s["tool_name"],
                            s["tool_args"],
                            runtime_state,
                        )
                        return {"ok": True, "result": res, "summary": summ, "events": events}
                    except Exception as exc:
                        return {"ok": False, "error": _format_tool_execution_error(exc)}

                with ThreadPoolExecutor(
                    max_workers=min(normalized_parallel_tool_limit, len(parallel_slots))
                ) as executor:
                    futures_list = [(executor.submit(_run_slot, s), s) for s in parallel_slots]
                for future, s in futures_list:
                    s["exec_result"] = future.result()
            else:
                for s in parallel_slots:
                    try:
                        res, summ, events = _execute_streaming_tool_with_event_buffer(
                            s["tool_name"],
                            s["tool_args"],
                            runtime_state,
                        )
                        s["exec_result"] = {"ok": True, "result": res, "summary": summ, "events": events}
                    except Exception as exc:
                        s["exec_result"] = {"ok": False, "error": _format_tool_execution_error(exc)}

            for s in parallel_slots:
                buffered_events = (
                    s.get("exec_result", {}).get("events") if isinstance(s.get("exec_result"), dict) else []
                )
                if isinstance(buffered_events, list):
                    for event in buffered_events:
                        if isinstance(event, dict):
                            yield event

            # Canvas self-read guard: track which document IDs/paths were mutated
            # in this batch so that a subsequent same-batch read of the same
            # document can be short-circuited with a helpful message instead
            # of wasting tokens on a redundant inspection.
            _canvas_mutated_doc_ids: set[str] = set()
            _canvas_mutated_doc_paths: set[str] = set()

            for s in sequential_slots:
                try:
                    _raise_if_agent_cancelled(runtime_state.get("agent_context"))
                    _tool_name = s["tool_name"]
                    _tool_args = s.get("tool_args") or {}

                    # Self-read guard: if this is a canvas read targeting a
                    # document that was just mutated in the same batch,
                    # return a short-circuit result instead of executing.
                    should_skip_read, guard_message = _should_skip_canvas_read_after_same_turn_mutation(
                        _tool_name,
                        _tool_args,
                        runtime_state.get("canvas") if isinstance(runtime_state.get("canvas"), dict) else {},
                        _canvas_mutated_doc_ids,
                        _canvas_mutated_doc_paths,
                    )
                    if should_skip_read:
                        s["exec_result"] = {"ok": True, "result": guard_message, "summary": guard_message}
                        continue

                    if _tool_name == "sub_agent":
                        res, summ = yield from _run_sub_agent_stream(_tool_args, runtime_state)
                    else:
                        if s.get("is_canvas"):
                            yield {"type": "canvas_executing", "tool": _tool_name, "call_id": s["call_id"]}
                        res, summ = _execute_tool(_tool_name, _tool_args, runtime_state=runtime_state)
                    s["exec_result"] = {"ok": True, "result": res, "summary": summ}

                    # Track mutated canvas document IDs/paths for the self-read guard.
                    if _tool_name in CANVAS_MUTATION_TOOL_NAMES and s["exec_result"].get("ok"):
                        tracked_doc_ids, tracked_doc_paths = _collect_canvas_mutation_locators(
                            _tool_name, _tool_args, res
                        )
                        _canvas_mutated_doc_ids.update(tracked_doc_ids)
                        _canvas_mutated_doc_paths.update(tracked_doc_paths)
                except Exception as exc:
                    s["exec_result"] = {"ok": False, "error": _format_tool_execution_error(exc)}

        # ---- Phase 3: post-process all slots in original order ----
        for slot in slots:
            _raise_if_agent_cancelled(runtime_state.get("agent_context"))
            kind = slot["kind"]
            tool_name = slot["tool_name"]
            tool_args = slot["tool_args"]
            call_id = slot["call_id"]
            preview = slot["preview"]
            cache_key = slot["cache_key"]

            if kind == "error":
                error = slot["error"]
                if tool_name not in ui_hidden_tool_names:
                    yield {"type": "tool_error", "step": step, "tool": tool_name, "error": error, "call_id": call_id}
                tool_messages.append(
                    {
                        "id": call_id,
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": _serialize_tool_message_content({"ok": False, "error": error}),
                    }
                )
                transcript_results.append({"tool_name": tool_name, "arguments": tool_args, "ok": False, "error": error})
                tool_output_entries.append(
                    {
                        "tool_name": tool_name,
                        "tool_args": tool_args,
                        "call_id": call_id,
                        "execution_error": error,
                        "ok": False,
                    }
                )

            elif kind == "session_cache_hit":
                result = slot["result"]
                summary = slot["summary"]
                transcript_result = slot["transcript_result"]
                storage_entry = slot["storage_entry"]
                if tool_name not in ui_hidden_tool_names:
                    yield {
                        "type": "tool_result",
                        "step": step,
                        "tool": tool_name,
                        "summary": f"{summary} (cached)",
                        "call_id": call_id,
                        "cached": True,
                    }
                tool_messages.append(
                    {
                        "id": call_id,
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": _build_compact_tool_message_content(
                            tool_name,
                            tool_args,
                            result,
                            f"{summary} (cached)",
                            transcript_result=transcript_result,
                            storage_entry=storage_entry,
                        ),
                    }
                )
                transcript_results.append(
                    {
                        "tool_name": tool_name,
                        "arguments": tool_args,
                        "ok": not _tool_result_has_error(tool_name, result),
                        "summary": f"{summary} (cached)",
                        "result": transcript_result,
                        "cached": True,
                    }
                )
                tool_output_entries.append(
                    {
                        "tool_name": tool_name,
                        "tool_args": tool_args,
                        "call_id": call_id,
                        "result": result,
                        "summary": f"{summary} (cached)",
                        "transcript_result": transcript_result,
                        "storage_entry": storage_entry,
                        "cached": True,
                        "ok": not _tool_result_has_error(tool_name, result),
                    }
                )

            elif kind == "memory_cache_hit":
                result = slot["result"]
                summary = slot["summary"]
                transcript_result = slot["transcript_result"]
                if tool_name not in ui_hidden_tool_names:
                    yield {
                        "type": "tool_result",
                        "step": step,
                        "tool": tool_name,
                        "summary": f"{summary} (cached)",
                        "call_id": call_id,
                        "cached": True,
                    }
                tool_messages.append(
                    {
                        "id": call_id,
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": _build_compact_tool_message_content(
                            tool_name,
                            tool_args,
                            result,
                            f"{summary} (cached)",
                            transcript_result=transcript_result,
                        ),
                    }
                )
                transcript_results.append(
                    {
                        "tool_name": tool_name,
                        "arguments": tool_args,
                        "ok": True,
                        "summary": f"{summary} (cached)",
                        "result": transcript_result,
                        "cached": True,
                    }
                )
                tool_output_entries.append(
                    {
                        "tool_name": tool_name,
                        "tool_args": tool_args,
                        "call_id": call_id,
                        "result": result,
                        "summary": f"{summary} (cached)",
                        "transcript_result": transcript_result,
                        "cached": True,
                        "ok": True,
                    }
                )

            elif kind == "execute":
                exec_result = slot["exec_result"]
                if exec_result["ok"]:
                    result = exec_result["result"]
                    summary = exec_result["summary"]
                    transcript_result = _prepare_tool_result_for_transcript(
                        tool_name,
                        result,
                        fetch_url_token_threshold=fetch_url_token_threshold,
                        fetch_url_clip_aggressiveness=fetch_url_clip_aggressiveness,
                    )
                    if _is_session_cacheable_tool(tool_name):
                        tool_result_cache[cache_key] = (result, summary)
                    storage_entry = _build_tool_result_storage_entry(
                        tool_name,
                        tool_args,
                        result,
                        summary,
                        transcript_result=transcript_result,
                    )
                    if storage_entry and cache_key not in persisted_tool_cache_keys:
                        persisted_tool_cache_keys.add(cache_key)
                        persisted_tool_results.append(storage_entry)
                    if tool_name in (WEB_TOOL_NAMES | {"sub_agent"}) and storage_entry:
                        try:
                            if tool_name == "fetch_url":
                                # Use raw_content when available so the full (unclipped) page
                                # text is indexed in tool memory and can be found later by
                                # tool memory and can be found later by grep_fetched_content.
                                memory_content = storage_entry.get("raw_content") or storage_entry.get("content", "")
                            else:
                                memory_content = storage_entry.get("content", "")
                            upsert_tool_memory_result(
                                tool_name,
                                storage_entry.get("input_preview", ""),
                                memory_content,
                                storage_entry.get("summary", ""),
                            )
                        except Exception as exc:
                            _trace_agent_event(
                                "tool_memory_upsert_failed",
                                trace_id=trace_id,
                                step=step,
                                tool_name=tool_name,
                                tool_args=tool_args,
                                error=str(exc),
                            )
                    _trace_agent_event(
                        "tool_call_completed",
                        trace_id=trace_id,
                        step=step,
                        tool_name=tool_name,
                        tool_args=tool_args,
                        summary=summary,
                        result=result,
                        transcript_result=transcript_result,
                        raw_fields={
                            "tool_args": tool_args,
                            "result": result,
                            "transcript_result": transcript_result,
                            "storage_entry": storage_entry,
                        },
                    )
                    if tool_name not in ui_hidden_tool_names:
                        yield {
                            "type": "tool_result",
                            "step": step,
                            "tool": tool_name,
                            "summary": summary,
                            "call_id": call_id,
                            "cached": False,
                        }
                    tool_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": _build_compact_tool_message_content(
                                tool_name,
                                tool_args,
                                result,
                                summary,
                                transcript_result=transcript_result,
                                storage_entry=storage_entry,
                            ),
                        }
                    )
                    transcript_results.append(
                        {
                            "tool_name": tool_name,
                            "arguments": tool_args,
                            "ok": not _tool_result_has_error(tool_name, result),
                            "summary": summary,
                            "result": transcript_result,
                        }
                    )
                    tool_output_entries.append(
                        {
                            "tool_name": tool_name,
                            "tool_args": tool_args,
                            "call_id": call_id,
                            "result": result,
                            "summary": summary,
                            "transcript_result": transcript_result,
                            "storage_entry": storage_entry,
                            "ok": not _tool_result_has_error(tool_name, result),
                        }
                    )
                    if tool_name in CANVAS_MUTATION_TOOL_NAMES:
                        canvas_modified = True
                        if not _tool_result_has_error(tool_name, result):
                            successful_canvas_mutation = True
                            canvas_context_refresh_needed = True
                            # Emit the committed canvas snapshot immediately so
                            # the frontend can replace the live preview with the
                            # final rendered document before the assistant's
                            # prose finishes streaming.
                            yield build_tool_capture_event()
                    clarification_event = _extract_clarification_event(result)
                    if clarification_event is not None:
                        _trace_agent_event(
                            "clarification_requested",
                            trace_id=trace_id,
                            step=step,
                            clarification=clarification_event.get("clarification"),
                            raw_fields={"clarification_event": clarification_event, "tool_result": result},
                        )
                        public_history_messages = _build_public_tool_history_messages(
                            assistant_tool_call_message, tool_messages
                        )
                        if public_history_messages:
                            yield {
                                "type": "tool_history",
                                "step": step,
                                "messages": public_history_messages,
                            }
                        yield clarification_event
                        if usage_totals["total_tokens"]:
                            yield usage_event()
                        yield build_tool_capture_event()
                        yield {"type": "done"}
                        return
                else:
                    error = exec_result["error"]
                    _append_working_state_blocker(working_state, tool_name, error)
                    _trace_agent_event(
                        "tool_call_failed",
                        trace_id=trace_id,
                        step=step,
                        tool_name=tool_name,
                        tool_args=tool_args,
                        error=error,
                        raw_fields={"tool_args": tool_args, "error": error},
                    )
                    if tool_name not in ui_hidden_tool_names:
                        yield {
                            "type": "tool_error",
                            "step": step,
                            "tool": tool_name,
                            "error": error,
                            "call_id": call_id,
                        }
                    tool_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": _serialize_tool_message_content({"ok": False, "error": error}),
                        }
                    )
                    transcript_results.append(
                        {
                            "tool_name": tool_name,
                            "arguments": tool_args,
                            "ok": False,
                            "error": error,
                        }
                    )
                    tool_output_entries.append(
                        {
                            "tool_name": tool_name,
                            "tool_args": tool_args,
                            "call_id": call_id,
                            "execution_error": error,
                            "ok": False,
                        }
                    )

        if tool_output_entries:
            tool_messages, transcript_results, tool_execution_result_message, tool_results_budget_compacted = (
                _apply_tool_output_budget(
                    messages,
                    tool_output_entries,
                    prompt_max_input_tokens=configured_prompt_max_input_tokens,
                    context_compaction_threshold=configured_context_compaction_threshold,
                    fetch_url_token_threshold=fetch_url_token_threshold,
                    fetch_url_clip_aggressiveness=fetch_url_clip_aggressiveness,
                )
            )
            if tool_results_budget_compacted:
                _trace_agent_event(
                    "tool_results_budget_compacted",
                    trace_id=trace_id,
                    step=step,
                    tool_count=len(tool_output_entries),
                    estimated_total_tokens=_estimate_messages_tokens([*messages, *tool_messages]),
                )

        _trace_agent_event(
            "tool_transcript_appended",
            trace_id=trace_id,
            step=step,
            transcript_results=transcript_results,
            raw_fields={"transcript_results": transcript_results, "tool_messages": tool_messages},
        )
        public_history_messages = _build_public_tool_history_messages(assistant_tool_call_message, tool_messages)
        if public_history_messages:
            yield {
                "type": "tool_history",
                "step": step,
                "messages": public_history_messages,
            }
        messages.extend(tool_messages)
        runtime_state["_accumulated_messages"] = messages
        _merge_tool_execution_result_message(messages, tool_execution_result_message)
        if canvas_context_refresh_needed:
            _refresh_latest_canvas_context_injection_message(messages, runtime_state)

    if fatal_api_error is not None:
        if not answer_started:
            for event in emit_answer(FINAL_ANSWER_ERROR_TEXT):
                yield event
        if usage_totals["total_tokens"]:
            yield usage_event()
        yield build_tool_capture_event()
        yield {"type": "done"}
        return

    final_phase_compaction_used = False
    final_instruction_builder = _build_final_answer_instruction
    pending_final_retry_reason: str | None = None
    while True:
        final_extra_messages = []
        try:
            _trace_agent_event("final_answer_phase_started", trace_id=trace_id, step=step)
            final_retry_reason = pending_final_retry_reason
            pending_final_retry_reason = None
            working_memory_instruction = _build_working_state_instruction(working_state)
            final_extra_messages = [working_memory_instruction] if working_memory_instruction is not None else []
            final_messages, _ = apply_context_compaction(final_extra_messages, reason="pre_final_answer")
            final_messages = [*final_messages, final_instruction_builder()]
            final_messages = _strip_intermediate_tool_call_content(final_messages)
            turn_result = yield from stream_model_turn(
                final_messages,
                allow_tools=False,
                buffer_answer=True,
                call_type="final_answer",
                retry_reason=final_retry_reason,
            )
            content_text = turn_result.get("content_text") or ""
            tool_calls = turn_result.get("tool_calls")
            stream_error = turn_result.get("stream_error")
            answer_emitted = bool(turn_result.get("answer_emitted"))
            if stream_error and _is_context_overflow_error(stream_error) != "none" and not final_phase_compaction_used:
                _, compacted = apply_context_compaction(
                    final_extra_messages, reason="reactive_final_stream", force=True
                )
                if compacted:
                    final_phase_compaction_used = True
                    _trace_agent_event(
                        "context_overflow_recovered",
                        trace_id=trace_id,
                        step=step,
                        phase="final_answer",
                        source="stream_error",
                    )
                    pending_final_retry_reason = "context_overflow_recovery"
                    continue
                if final_instruction_builder is _build_final_answer_instruction:
                    _trace_agent_event(
                        "context_overflow_minimal_final_instruction",
                        trace_id=trace_id,
                        step=step,
                        phase="final_answer",
                        source="stream_error",
                    )
                    final_phase_compaction_used = True
                    final_instruction_builder = _build_minimal_final_answer_instruction
                    pending_final_retry_reason = "minimal_final_instruction"
                    continue
                _trace_agent_event(
                    "context_overflow_unrecoverable",
                    trace_id=trace_id,
                    step=step,
                    phase="final_answer",
                    source="stream_error",
                    error=stream_error,
                    message_count=len(final_messages),
                )
                stream_error = _build_context_overflow_recovery_error(final_messages)
            if tool_calls:
                if content_text:
                    final_text = content_text
                else:
                    yield {
                        "type": "tool_error",
                        "step": step,
                        "tool": "agent",
                        "error": "Tool limit reached before the model produced a final answer.",
                    }
                    final_text = FINAL_ANSWER_ERROR_TEXT
            elif not content_text:
                yield {
                    "type": "tool_error",
                    "step": step,
                    "tool": "agent",
                    "error": "The model still did not provide a final answer in assistant content.",
                }
                final_text = FINAL_ANSWER_MISSING_TEXT
            else:
                final_text = content_text
            if stream_error and not _is_truncated_stream_disconnect_error(stream_error):
                yield {"type": "tool_error", "step": step, "tool": "final_answer", "error": stream_error}
            if not answer_emitted:
                for event in emit_answer(final_text):
                    yield event
            break
        except Exception as exc:
            error = str(exc)
            if _is_context_overflow_error(error) != "none" and not final_phase_compaction_used:
                _, compacted = apply_context_compaction(
                    final_extra_messages, reason="reactive_final_answer", force=True
                )
                if compacted:
                    final_phase_compaction_used = True
                    _trace_agent_event(
                        "context_overflow_recovered",
                        trace_id=trace_id,
                        step=step,
                        phase="final_answer",
                        source="exception",
                    )
                    pending_final_retry_reason = "context_overflow_recovery"
                    continue
                if final_instruction_builder is _build_final_answer_instruction:
                    _trace_agent_event(
                        "context_overflow_minimal_final_instruction",
                        trace_id=trace_id,
                        step=step,
                        phase="final_answer",
                        source="exception",
                    )
                    final_phase_compaction_used = True
                    final_instruction_builder = _build_minimal_final_answer_instruction
                    pending_final_retry_reason = "minimal_final_instruction"
                    continue
                _trace_agent_event(
                    "context_overflow_unrecoverable",
                    trace_id=trace_id,
                    step=step,
                    phase="final_answer",
                    source="exception",
                    error=error,
                    message_count=len([*messages, *final_extra_messages]),
                )
                error = _build_context_overflow_recovery_error([*messages, *final_extra_messages])
            yield {"type": "tool_error", "step": step, "tool": "final_answer", "error": error}
            for event in emit_answer(FINAL_ANSWER_ERROR_TEXT):
                yield event
            break

    if usage_totals["total_tokens"]:
        yield usage_event()
    yield build_tool_capture_event()
    yield {"type": "compaction_applied", "messages": messages}
    yield {"type": "done"}
