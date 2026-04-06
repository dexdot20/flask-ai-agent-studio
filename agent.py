from __future__ import annotations

import ast
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import hashlib
import html
import json
import logging
import math
import os
import time
try:
    from json_repair import repair_json as _repair_json
except ImportError:  # pragma: no cover
    _repair_json = None
import re
import string
from logging.handlers import RotatingFileHandler
from uuid import uuid4

from canvas_service import (
    batch_canvas_edits,
    build_canvas_document_context_result,
    build_canvas_tool_result,
    clear_canvas_viewport,
    clear_overlapping_canvas_viewports,
    clear_canvas,
    create_canvas_document,
    create_canvas_runtime_state,
    delete_canvas_document,
    delete_canvas_lines,
    get_canvas_runtime_active_document_id,
    get_canvas_runtime_documents,
    get_canvas_runtime_snapshot,
    insert_canvas_lines,
    list_canvas_lines,
    _find_canvas_document,
    preview_canvas_changes,
    replace_canvas_lines,
    rewrite_canvas_document,
    search_canvas_document,
    set_canvas_viewport,
    scroll_canvas_document,
    scale_canvas_char_limit,
    transform_canvas_lines,
    update_canvas_metadata,
)
from project_workspace_service import (
    create_directory as workspace_create_directory,
    create_file as workspace_create_file,
    create_workspace_runtime_state,
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
    AGENT_TOOL_RESULT_TRANSCRIPT_MAX_CHARS,
    AGENT_TRACE_LOG_PATH,
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
    SUB_AGENT_DEFAULT_TIMEOUT_SECONDS,
    SUB_AGENT_TIMEOUT_MAX_SECONDS,
    SUB_AGENT_TIMEOUT_MIN_SECONDS,
)
from db import (
    MESSAGE_USAGE_BREAKDOWN_PROTECTED_KEYS,
    MESSAGE_USAGE_BREAKDOWN_REDUCTION_ORDER,
    append_to_scratchpad,
    count_scratchpad_notes,
    get_fetch_url_clip_aggressiveness,
    get_fetch_url_token_threshold,
    get_all_scratchpad_sections,
    get_app_settings,
    get_clarification_max_questions,
    get_model_temperature,
    get_rag_source_types,
    get_sub_agent_max_parallel_tools,
    get_sub_agent_retry_attempts,
    get_sub_agent_retry_delay_seconds,
    get_sub_agent_timeout_seconds,
    parse_message_tool_calls,
    read_image_asset_bytes,
    normalize_scratchpad_text,
    replace_scratchpad,
)
from model_registry import (
    DEEPSEEK_PROVIDER,
    OPENROUTER_PROVIDER,
    apply_model_target_request_options,
    build_openrouter_cache_estimate_context,
    get_operation_model_candidates,
    get_operation_model,
    get_model_pricing as lookup_model_pricing,
    get_provider_client,
    has_known_model_pricing as lookup_has_known_model_pricing,
    resolve_model_target,
)
from rag_service import get_exact_tool_memory_match, search_knowledge_base_tool, search_tool_memory, upsert_tool_memory_result
from tool_registry import TOOL_SPEC_BY_NAME, get_openai_tool_specs
from token_utils import estimate_text_tokens
from vision import answer_image_question
from web_tools import (
    fetch_url_tool,
    grep_fetched_content_tool,
    search_news_ddgs_tool,
    search_news_google_tool,
    search_web_tool,
)

FINAL_ANSWER_ERROR_TEXT = "The model returned an invalid tool instruction and no final answer could be produced."
FINAL_ANSWER_MISSING_TEXT = "The model did not produce a final answer in assistant content."
CONTEXT_OVERFLOW_RECOVERY_ERROR_TEXT = (
    "Context window is full and cannot be compacted further. "
    "Try starting a new conversation, disabling RAG or large canvas content, or reducing the request size."
)
MISSING_FINAL_ANSWER_MARKER = "[INSTRUCTION: MISSING FINAL ANSWER"
CLARIFICATION_RETRY_MARKER = "[INSTRUCTION: CLARIFICATION TOOL REQUIRED"
CLARIFICATION_TOOL_REPAIR_MARKER = "[INSTRUCTION: CLARIFICATION TOOL REPAIR"
TOOL_EXECUTION_RESULTS_MARKER = "[TOOL EXECUTION RESULTS]"
REASONING_REPLAY_MARKER = "[AGENT REASONING CONTEXT]"
MAX_REASONING_REPLAY_ENTRIES = 2
MAX_REASONING_REPLAY_CHARS = 4_000
MAX_REASONING_REPLAY_TOTAL_CHARS = 10_000
CANVAS_TOOL_NAMES = {
    "expand_canvas_document",
    "scroll_canvas_document",
    "search_canvas_document",
    "create_canvas_document",
    "rewrite_canvas_document",
    "preview_canvas_changes",
    "batch_canvas_edits",
    "transform_canvas_lines",
    "update_canvas_metadata",
    "set_canvas_viewport",
    "clear_canvas_viewport",
    "replace_canvas_lines",
    "insert_canvas_lines",
    "delete_canvas_lines",
    "delete_canvas_document",
    "clear_canvas",
}
CANVAS_MUTATION_TOOL_NAMES = {
    "create_canvas_document",
    "rewrite_canvas_document",
    "batch_canvas_edits",
    "transform_canvas_lines",
    "update_canvas_metadata",
    "set_canvas_viewport",
    "clear_canvas_viewport",
    "replace_canvas_lines",
    "insert_canvas_lines",
    "delete_canvas_lines",
    "delete_canvas_document",
    "clear_canvas",
}
CANVAS_STREAM_OPEN_TOOL_NAMES = {
    "create_canvas_document",
    "rewrite_canvas_document",
    "expand_canvas_document",
    "replace_canvas_lines",
    "insert_canvas_lines",
    "delete_canvas_lines",
}
CANVAS_STREAM_CONTENT_TOOL_NAMES = {
    "create_canvas_document",
    "rewrite_canvas_document",
}
DSML_INVOKE_TAG_RE = re.compile(r'<[^>]*invoke\s+name="(?P<name>[^"]+)"[^>]*>', re.IGNORECASE)
DSML_FUNCTION_CALLS_TAG_RE = re.compile(r'<[^>]*function_calls[^>]*>', re.IGNORECASE)
DSML_PARAMETER_TAG_RE = re.compile(
    r'<[^>]*parameter\s+name="(?P<name>[^"]+)"(?P<attrs>[^>]*)>(?P<value>.*?)</[^>]*parameter\s*>',
    re.IGNORECASE | re.DOTALL,
)
DSML_STRING_ATTR_RE = re.compile(r'\bstring\s*=\s*["\']true["\']', re.IGNORECASE)
TOOL_ARGUMENT_CODE_FENCE_RE = re.compile(
    r'^\s*```(?:json|javascript|js|python|py)?\s*(?P<body>.*?)\s*```\s*$',
    re.IGNORECASE | re.DOTALL,
)
_VALID_IDENTIFIER_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
TOOL_ARGUMENT_LANGUAGE_LABELS = {"json", "javascript", "js", "python", "py"}
WEB_TOOL_NAMES = {
    "search_web",
    "fetch_url",
    "fetch_url_summarized",
    "search_news_ddgs",
    "search_news_google",
}
SEARCH_QUERY_BATCHED_TOOL_NAMES = {
    "search_web",
    "search_news_ddgs",
    "search_news_google",
}
SEARCH_TOOL_QUERY_BATCH_SIZE = 5
PARALLEL_SAFE_TOOL_NAMES = WEB_TOOL_NAMES | {
    "image_explain",
    # RAG / memory reads
    "search_knowledge_base",
    "search_tool_memory",
    "read_scratchpad",
    # Fetch content grep (read-only, cache-based)
    "grep_fetched_content",
    # Workspace reads
    "read_file",
    "list_dir",
    "search_files",
    "validate_project_workspace",
    # Canvas inspection (non-mutating)
    "expand_canvas_document",
    "scroll_canvas_document",
    "search_canvas_document",
    # Delegated read-only helper
    "sub_agent",
}
SUB_AGENT_ALLOWED_TOOL_NAMES = {
    "search_knowledge_base",
    "search_tool_memory",
    "read_scratchpad",
    "search_web",
    "fetch_url",
    "fetch_url_summarized",
    "grep_fetched_content",
    "search_news_ddgs",
    "search_news_google",
    "expand_canvas_document",
    "scroll_canvas_document",
    "search_canvas_document",
    "read_file",
    "list_dir",
    "search_files",
}
SUB_AGENT_DEFAULT_MAX_STEPS = 6
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
SYSTEM_BREAKDOWN_SECTION_KEY_BY_HEADING = {
    "## Scratchpad (AI Persistent Memory)": "scratchpad",
    "## Tool Execution History": "tool_trace",
    "## Tool Memory": "tool_memory",
    "## Knowledge Base": "rag_context",
    "## Canvas Workspace Summary": "canvas",
    "## Canvas Editing Guidance": "canvas",
    "## Canvas Decision Matrix": "canvas",
    "## Canvas Project Manifest": "canvas",
    "## Canvas Relationship Map": "canvas",
    "## Active Canvas Document": "canvas",
    "## Other Canvas Documents": "canvas",
    "## Available Tools": "tool_specs",
    "## Tool Calling": "core_instructions",
}
SYSTEM_BREAKDOWN_REDUCTION_ORDER = MESSAGE_USAGE_BREAKDOWN_REDUCTION_ORDER
_AGENT_TRACE_LOGGER = None
client = get_provider_client(DEEPSEEK_PROVIDER)


def _get_agent_trace_logger():
    global _AGENT_TRACE_LOGGER
    if _AGENT_TRACE_LOGGER is not None:
        return _AGENT_TRACE_LOGGER

    logger = logging.getLogger("chatbot.agent.trace")
    if not logger.handlers:
        log_dir = os.path.dirname(AGENT_TRACE_LOG_PATH)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        handler = RotatingFileHandler(AGENT_TRACE_LOG_PATH, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
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

    prompt_cache_hit_present = "prompt_cache_hit_tokens" in payload and payload.get("prompt_cache_hit_tokens") is not None
    prompt_cache_miss_present = "prompt_cache_miss_tokens" in payload and payload.get("prompt_cache_miss_tokens") is not None

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

    metrics = {key: _coerce_usage_int(payload.get(key)) for key in fields}
    metrics["cache_hit_present"] = prompt_cache_hit_present
    metrics["cache_miss_present"] = prompt_cache_miss_present
    metrics["cache_metrics_present"] = prompt_cache_hit_present or prompt_cache_miss_present
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


def _distribute_overhead_tokens(
    breakdown: dict[str, int],
    overhead_tokens: int,
    recipients: tuple[str, ...],
) -> dict[str, int]:
    remaining = max(0, int(overhead_tokens or 0))
    if remaining <= 0:
        return breakdown

    target_keys = [key for key in recipients if breakdown.get(key, 0) > 0]
    if not target_keys and recipients:
        target_keys = [recipients[0]]
    if not target_keys:
        target_keys = ["core_instructions"]

    weighted_total = sum(max(0, int(breakdown.get(key, 0))) for key in target_keys)
    if weighted_total <= 0:
        breakdown[target_keys[0]] = breakdown.get(target_keys[0], 0) + remaining
        return breakdown

    for index, key in enumerate(target_keys):
        if remaining <= 0:
            break
        if index == len(target_keys) - 1:
            share = remaining
        else:
            weight = max(0, int(breakdown.get(key, 0)))
            share = min(remaining, int((overhead_tokens * weight) / weighted_total))
        breakdown[key] = breakdown.get(key, 0) + share
        remaining -= share

    return breakdown


def _rebalance_breakdown_to_total(breakdown: dict[str, int], total_tokens: int) -> dict[str, int]:
    adjusted = {key: max(0, int(value)) for key, value in breakdown.items() if value and value > 0}
    current_total = sum(adjusted.values())
    if current_total < total_tokens:
        adjusted["core_instructions"] = adjusted.get("core_instructions", 0) + (total_tokens - current_total)
        return adjusted

    overflow = current_total - total_tokens
    if overflow <= 0:
        return adjusted

    for key in SYSTEM_BREAKDOWN_REDUCTION_ORDER:
        if overflow <= 0:
            break
        available = adjusted.get(key, 0)
        if available <= 0:
            continue
        reduction = min(available, overflow)
        adjusted[key] = available - reduction
        overflow -= reduction

    if overflow > 0:
        for key, available in sorted(adjusted.items(), key=lambda item: item[1], reverse=True):
            if overflow <= 0:
                break
            if available <= 0:
                continue
            reduction = min(available, overflow)
            adjusted[key] = available - reduction
            overflow -= reduction

    return {key: value for key, value in adjusted.items() if value > 0}


def _align_breakdown_to_provider_total(breakdown: dict[str, int], total_tokens: int) -> dict[str, int]:
    adjusted = {key: max(0, int(value)) for key, value in breakdown.items() if key in INPUT_BREAKDOWN_KEYS and value and value > 0}
    target_total = max(0, int(total_tokens or 0))
    current_total = sum(adjusted.values())
    if current_total < target_total:
        adjusted["unknown_provider_overhead"] = adjusted.get("unknown_provider_overhead", 0) + (target_total - current_total)
        return adjusted

    overflow = current_total - target_total
    if overflow <= 0:
        return adjusted

    protected_floor_keys = set()
    if target_total > 0:
        protected_candidates = [key for key in MESSAGE_USAGE_BREAKDOWN_PROTECTED_KEYS if adjusted.get(key, 0) > 0]
        protected_floor_keys = set(protected_candidates[: min(len(protected_candidates), target_total)])

    for key in SYSTEM_BREAKDOWN_REDUCTION_ORDER:
        if overflow <= 0:
            break
        floor = 1 if key in protected_floor_keys else 0
        available = adjusted.get(key, 0) - floor
        if available <= 0:
            continue
        reduction = min(available, overflow)
        adjusted[key] = available - reduction + floor
        overflow -= reduction

    if overflow > 0:
        for key, available in sorted(adjusted.items(), key=lambda item: item[1], reverse=True):
            if overflow <= 0:
                break
            floor = 1 if key in protected_floor_keys else 0
            reducible = available - floor
            if reducible <= 0:
                continue
            reduction = min(reducible, overflow)
            adjusted[key] = available - reduction
            overflow -= reduction

    return {key: value for key, value in adjusted.items() if value > 0}


def _estimate_system_message_breakdown(content: str, total_tokens: int) -> dict[str, int]:
    section_matches = list(re.finditer(r"^## [^\n]+", content, flags=re.MULTILINE))
    if not section_matches:
        return {"core_instructions": total_tokens}

    breakdown: dict[str, int] = {}
    cursor = 0
    for index, match in enumerate(section_matches):
        start = match.start()
        end = section_matches[index + 1].start() if index + 1 < len(section_matches) else len(content)
        if start > cursor:
            prefix = content[cursor:start]
            prefix_tokens = _estimate_text_tokens(prefix)
            if prefix_tokens > 0:
                breakdown["core_instructions"] = breakdown.get("core_instructions", 0) + prefix_tokens

        section_text = content[start:end]
        section_tokens = _estimate_text_tokens(section_text)
        if section_tokens > 0:
            section_heading = match.group(0).strip()
            section_key = SYSTEM_BREAKDOWN_SECTION_KEY_BY_HEADING.get(section_heading, "core_instructions")
            breakdown[section_key] = breakdown.get(section_key, 0) + section_tokens
        cursor = end

    return _rebalance_breakdown_to_total(breakdown, total_tokens)


def _estimate_message_breakdown(message: dict) -> dict[str, int]:
    role = str(message.get("role") or "").strip()
    content = str(message.get("content") or "")
    total_tokens = _estimate_text_tokens(content)
    message_id = str(message.get("id") or "").strip()
    if message_id:
        total_tokens += _estimate_text_tokens(message_id)
    if total_tokens <= 0 and role != "assistant":
        return {}

    if role == "user":
        breakdown = {"user_messages": total_tokens}
        return _distribute_overhead_tokens(breakdown, _estimate_message_wrapper_tokens(role), ("user_messages",))
    if role == "assistant":
        breakdown = {}
        if total_tokens > 0:
            breakdown["assistant_history"] = total_tokens
        tool_calls = message.get("tool_calls") if isinstance(message.get("tool_calls"), list) else []
        tool_call_tokens = _estimate_serialized_tokens(tool_calls)
        if tool_call_tokens > 0:
            breakdown["assistant_tool_calls"] = tool_call_tokens
        return _distribute_overhead_tokens(
            breakdown,
            _estimate_message_wrapper_tokens(role, include_tool_calls=bool(tool_calls)),
            ("assistant_history", "assistant_tool_calls"),
        )
    if role == "tool":
        tool_call_id = str(message.get("tool_call_id") or "").strip()
        payload_tokens = total_tokens
        if tool_call_id:
            payload_tokens += _estimate_serialized_tokens({"tool_call_id": tool_call_id})
        if payload_tokens <= 0:
            return {}
        breakdown = {"tool_results": payload_tokens}
        return _distribute_overhead_tokens(breakdown, _estimate_message_wrapper_tokens(role), ("tool_results",))
    if role != "system":
        breakdown = {"core_instructions": total_tokens}
        return _distribute_overhead_tokens(breakdown, _estimate_message_wrapper_tokens(role), ("core_instructions",))

    # Classify system messages by their distinctive markers
    if content.startswith(TOOL_EXECUTION_RESULTS_MARKER):
        return {"tool_results": total_tokens}
    if content.startswith(REASONING_REPLAY_MARKER):
        return {"internal_state": total_tokens}
    if content.startswith("[AGENT WORKING MEMORY]"):
        return {"internal_state": total_tokens}
    if content.startswith("[INSTRUCTION: FINAL ANSWER REQUIRED]"):
        return {"core_instructions": total_tokens}
    if content.startswith("[INSTRUCTION: MISSING FINAL ANSWER"):
        return {"core_instructions": total_tokens}

    breakdown = _estimate_system_message_breakdown(content, total_tokens) or {"core_instructions": total_tokens}
    return _distribute_overhead_tokens(
        breakdown,
        _estimate_message_wrapper_tokens(role),
        tuple(key for key, value in breakdown.items() if value > 0) or ("core_instructions",),
    )


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

    measured_total = sum(breakdown.values())
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


def _is_context_overflow_error(error_str: str) -> bool:
    normalized = str(error_str or "").strip().lower()
    if not normalized:
        return False
    if "rate_limit" in normalized or re.search(r"\b429\b", normalized):
        return False

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
        "max_tokens",
    )
    if any(phrase in normalized for phrase in known_phrases):
        return True
    return "token" in normalized and ("exceed" in normalized or "too long" in normalized)


def _is_retryable_model_error(error: Exception | str) -> bool:
    error_text = str(error or "").strip().lower()
    if not error_text:
        return False
    if _is_context_overflow_error(error_text):
        return False

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
        return True
    return bool(re.search(r"\b429\b", error_text))


def _normalize_tool_args_for_cache(value):
    if isinstance(value, dict):
        return {str(key): _normalize_tool_args_for_cache(value[key]) for key in sorted(value.keys())}
    if isinstance(value, list):
        return [_normalize_tool_args_for_cache(item) for item in value]
    if isinstance(value, str):
        return value.strip()
    return value


def build_tool_cache_key(tool_name: str, tool_args: dict) -> str:
    normalized_args = _normalize_tool_args_for_cache(tool_args if isinstance(tool_args, dict) else {})
    payload = json.dumps(normalized_args, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha1(f"{tool_name}|{payload}".encode("utf-8")).hexdigest()
    return f"tool-cache:{digest}"


def _clean_tool_text(text: str, limit: int | None = None) -> str:
    cleaned = str(text or "").strip()
    if limit and len(cleaned) > limit:
        return cleaned[:limit].rstrip() + "…"
    return cleaned


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
    cleaned = re.sub(r"^\s*\d+[\.)](?=\s)", "", cleaned)
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
            return (
                f"If exact wording is needed, call grep_fetched_content with {url} and a keyword or regex, "
                "or search_tool_memory with the same URL."
            )
        return "If exact wording is needed, call grep_fetched_content with the same URL and a keyword or regex."
    if normalized_tool_name == "fetch_url_summarized":
        url = _clean_tool_text(normalized_tool_args.get("url") or "", limit=160)
        if url:
            return (
                f"If the clean summary is not enough, call fetch_url or grep_fetched_content with {url} "
                "to inspect the raw extracted page text."
            )
        return "If the clean summary is not enough, call fetch_url to inspect the raw extracted page text."
    if normalized_tool_name in {"search_web", "search_news_ddgs", "search_news_google"}:
        return "If exact wording is needed, fetch a specific returned URL or rerun the search with a narrower query."
    if normalized_tool_name == "search_knowledge_base":
        return "Repeat search_knowledge_base with the same query if you need the exact retrieved excerpts again."
    if normalized_tool_name == "search_tool_memory":
        return "Repeat search_tool_memory with the same query if you need the original remembered excerpt again."
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
    return tool_name in {"fetch_url", "fetch_url_summarized"} and isinstance(result, dict) and bool(result.get("error"))


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


def _iter_search_query_batches(raw_queries, *, batch_size: int = SEARCH_TOOL_QUERY_BATCH_SIZE):
    normalized_queries = _normalize_search_queries(raw_queries)
    if batch_size <= 0:
        batch_size = SEARCH_TOOL_QUERY_BATCH_SIZE
    for index in range(0, len(normalized_queries), batch_size):
        yield normalized_queries[index:index + batch_size]


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


def _build_sub_agent_conversation_handoff(messages: list[dict], max_messages: int = 8, max_chars: int = 2_400) -> str:
    visible_entries = []
    for message in messages or []:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "").strip()
        if role not in {"user", "assistant", "summary"}:
            continue
        if role == "assistant":
            tool_calls = message.get("tool_calls") if isinstance(message.get("tool_calls"), list) else []
            if tool_calls:
                continue
        content = _clean_tool_text(message.get("content") or "", limit=700)
        if not content:
            continue
        label = "User" if role == "user" else "Assistant" if role == "assistant" else "Summary"
        visible_entries.append(f"{label}: {content}")

    if len(visible_entries) > max_messages:
        visible_entries = visible_entries[-max_messages:]
    return _clean_tool_text("\n\n".join(visible_entries), limit=max_chars)


def _build_sub_agent_canvas_handoff(runtime_state: dict) -> str:
    documents = get_canvas_runtime_documents(runtime_state.get("canvas"))
    if not documents:
        return ""

    active_document_id = get_canvas_runtime_active_document_id(runtime_state.get("canvas"))
    lines = ["Canvas documents available to inspect:"]
    for document in documents[:12]:
        if not isinstance(document, dict):
            continue
        title = _clean_tool_text(document.get("title") or "Untitled", limit=120)
        path = _clean_tool_text(document.get("path") or document.get("document_path") or "", limit=160)
        role = _clean_tool_text(document.get("role") or "", limit=40)
        format_name = _clean_tool_text(document.get("format") or "", limit=20)
        marker = "*" if str(document.get("id") or "").strip() == str(active_document_id or "").strip() else "-"
        details = []
        if path:
            details.append(path)
        if role:
            details.append(role)
        if format_name:
            details.append(format_name)
        suffix = f" ({', '.join(details)})" if details else ""
        lines.append(f"{marker} {title}{suffix}")
    return _clean_tool_text("\n".join(lines), limit=1_500)


def _resolve_sub_agent_tool_names(requested_tools, parent_visible_tool_names: list[str]) -> list[str]:
    available = [
        name
        for name in _normalize_tool_name_list(parent_visible_tool_names)
        if name in SUB_AGENT_ALLOWED_TOOL_NAMES
    ]
    if not isinstance(requested_tools, list):
        return available

    requested = _normalize_tool_name_list(requested_tools)
    return [name for name in requested if name in available]


def _normalize_sub_agent_tool_calls(tool_calls) -> list[dict]:
    if not isinstance(tool_calls, list):
        return []

    normalized = []
    for tool_call in tool_calls[:8]:
        if not isinstance(tool_call, dict):
            continue
        function = tool_call.get("function") if isinstance(tool_call.get("function"), dict) else {}
        name = str(function.get("name") or tool_call.get("name") or "").strip()
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
            tool_message: dict[str, Any] = {"role": "tool", "content": content}
            tool_call_id = str(message.get("tool_call_id") or "").strip()[:120]
            if tool_call_id:
                tool_message["tool_call_id"] = tool_call_id
            if tool_message.get("content"):
                retry_messages.append(tool_message)
            index += 1
            continue

        if content:
            retry_messages.append({"role": role, "content": content})
        index += 1

    return retry_messages


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
            "state": str(entry.get("state") or "done").strip() if str(entry.get("state") or "").strip() in {"running", "done", "error"} else "done",
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
            tool_name = str(tool_call.get("name") or "").strip()
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
    parent_context: str,
    conversation_handoff: str,
    canvas_handoff: str,
    allowed_tools: list[str],
    max_parallel_tools: int | None = None,
) -> list[dict]:
    parts = [
        "You are an advanced delegated helper agent for a larger AI assistant system.",
        "Complete the delegated task using only the tools that are exposed to you. Read-only still includes web search and URL fetch tools when they are available.",
        "You must not ask the user clarifying questions, mutate files, mutate canvas documents, or delegate to another sub-agent.",
        "Treat the delegated task and handoff as direct instructions from the parent assistant.",
        "If any task or handoff text is not in English, first rewrite it into clear English working notes for yourself, then continue in English.",
        "Use English for tool planning, reasoning, status updates, and the final answer unless told otherwise.",
        "When using read-only search tools like search_web or search_news, batch queries between 1 and 5 items per list and split broader searches into multiple calls.",
        "Synthesize your findings and return a concise, definitive final answer that directly helps the parent assistant continue."
    ]
    if allowed_tools:
        parts.append(f"Available read-only tools: {', '.join(allowed_tools)}.")
    if max_parallel_tools is not None:
        normalized_parallel_tools = max(MAX_PARALLEL_TOOLS_MIN, min(MAX_PARALLEL_TOOLS_MAX, int(max_parallel_tools or 0)))
        parts.append(
            f"At most {normalized_parallel_tools} tool call(s) can execute in parallel in one turn. "
            f"If you need more independent reads than that, prioritize the best {normalized_parallel_tools} first and avoid low-value fan-out."
        )

    user_parts = [f"Delegated task from the parent assistant:\n{_clean_tool_text(task, limit=2_000)}"]
    if parent_context:
        user_parts.append(f"Parent context and goal:\n{_clean_tool_text(parent_context, limit=2_000)}")
    if conversation_handoff:
        user_parts.append(f"Current conversation summary:\n{conversation_handoff}")
    if canvas_handoff:
        user_parts.append(f"Canvas context:\n{canvas_handoff}")
    user_parts.append(
        "Return the best final answer you can. Include the most useful findings and concrete references from the tools you used."
    )

    return [
        {"role": "system", "content": "\n\n".join(parts)},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]


def _estimate_sub_agent_max_steps(
    task: str,
    parent_context: str,
    conversation_handoff: str,
    canvas_handoff: str,
    allowed_tools: list[str],
) -> int:
    combined_text = "\n".join(
        part.strip()
        for part in (task, parent_context, conversation_handoff, canvas_handoff)
        if str(part or "").strip()
    )
    word_count = len(re.findall(r"\w+", combined_text))
    keyword_hits = sum(
        1
        for keyword in (
            "compare",
            "across",
            "multiple",
            "thorough",
            "analyze",
            "analysis",
            "synthesize",
            "investigate",
            "repo",
            "codebase",
            "files",
            "sources",
            "evidence",
            "trace",
            "cross-file",
        )
        if keyword in combined_text.casefold()
    )

    score = 0
    if word_count >= 80:
        score += 1
    if word_count >= 180:
        score += 1
    if len(allowed_tools) >= 4:
        score += 1
    if len(allowed_tools) >= 8:
        score += 1
    if keyword_hits >= 2:
        score += 1
    if keyword_hits >= 5:
        score += 1
    if canvas_handoff:
        score += 1

    return max(3, min(8, 4 + score))


def _resolve_sub_agent_max_steps(
    tool_args: dict,
    *,
    task: str,
    parent_context: str,
    conversation_handoff: str,
    canvas_handoff: str,
    allowed_tools: list[str],
) -> int:
    raw_max_steps = tool_args.get("max_steps")
    if raw_max_steps not in (None, ""):
        return _coerce_int_range(raw_max_steps, SUB_AGENT_DEFAULT_MAX_STEPS, 1, 8)
    return _estimate_sub_agent_max_steps(
        task,
        parent_context,
        conversation_handoff,
        canvas_handoff,
        allowed_tools,
    )


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
        _, document = _find_canvas_document(canvas_state, document_id=document_id, document_path=document_path)
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
        expected_lines = existing_lines[start_line - 1:end_line]
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
        expected_lines = existing_lines[expected_start_line - 1:expected_end_line]
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


def _has_clarification_retry_instruction(messages: list[dict]) -> bool:
    return any(CLARIFICATION_RETRY_MARKER in str(message.get("content") or "") for message in messages)


def _has_clarification_tool_repair_instruction(messages: list[dict]) -> bool:
    return any(CLARIFICATION_TOOL_REPAIR_MARKER in str(message.get("content") or "") for message in messages)


def _get_latest_user_message_text(messages: list[dict]) -> str:
    for message in reversed(messages):
        if str(message.get("role") or "").strip() != "user":
            continue
        content = str(message.get("content") or "").strip()
        if content:
            return content
    return ""


def _user_requested_questions_first(messages: list[dict]) -> bool:
    latest_user_text = _get_latest_user_message_text(messages)
    if not latest_user_text:
        return False
    patterns = (
        r"\bask(?: me)?(?: a few| some)? questions? first\b",
        r"\bbefore (?:you )?answer(?:ing)?[, ]+ask\b",
        r"\bstart by asking\b",
        r"\bönce (?:birkaç |bazi |bazı )?soru(?:lar)? sor\b",
        r"\bcevaplamadan önce soru sor\b",
        r"\bsorular(?:ı|ini|ını)? önce sor\b",
        r"\bsoru sorarak ilerle\b",
    )
    normalized = latest_user_text.casefold()
    return any(re.search(pattern, normalized, re.IGNORECASE) for pattern in patterns)


def _assistant_text_suggests_skipped_clarification(content_text: str, reasoning_text: str) -> bool:
    combined = "\n".join(part for part in (content_text, reasoning_text) if str(part or "").strip()).casefold()
    if not combined:
        return False
    indicators = (
        "prepared questions",
        "i prepared questions",
        "need a few details",
        "need a few more details",
        "before i answer, i need",
        "i have a few questions",
        "clarify before",
        "soruları hazırladım",
        "birkaç soru",
        "netleştirmek için",
        "önce birkaç soru",
    )
    return any(indicator in combined for indicator in indicators)


def _conversation_has_clarification_tool_call(messages: list[dict]) -> bool:
    """Return True if ask_clarifying_question was already called in this conversation."""
    for message in messages:
        if not isinstance(message, dict):
            continue
        tool_calls = message.get("tool_calls")
        if not isinstance(tool_calls, list):
            continue
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            func = tc.get("function")
            name = str(
                (func.get("name") if isinstance(func, dict) else None)
                or tc.get("name")
                or ""
            )
            if name == "ask_clarifying_question":
                return True
    return False


def _should_retry_for_skipped_clarification(
    messages: list[dict],
    content_text: str,
    reasoning_text: str,
    prompt_tool_names: list[str],
) -> bool:
    if "ask_clarifying_question" not in set(prompt_tool_names or []):
        return False
    if _has_clarification_retry_instruction(messages):
        return False
    # Don't retry when the user is responding to questions that were already asked
    if _conversation_has_clarification_tool_call(messages):
        return False
    return _user_requested_questions_first(messages) or _assistant_text_suggests_skipped_clarification(content_text, reasoning_text)


def _build_retry_tool_choice(retry_reason: str | None, prompt_tool_names: list[str] | None):
    if "ask_clarifying_question" not in set(prompt_tool_names or []):
        return None

    normalized_reason = str(retry_reason or "").strip().lower()
    if normalized_reason not in {"clarification_tool_retry", "clarification_tool_repair"}:
        return None

    return {
        "type": "function",
        "function": {
            "name": "ask_clarifying_question",
        },
    }


def _is_openrouter_unsupported_tool_choice_error(error: Exception | str, request_kwargs: dict, target: dict | None) -> bool:
    if not isinstance(request_kwargs.get("tool_choice"), dict):
        return False
    record = target.get("record") if isinstance(target, dict) else None
    if str((record or {}).get("provider") or "").strip() != OPENROUTER_PROVIDER:
        return False

    normalized_error = str(error or "").strip().lower()
    if not normalized_error:
        return False
    return (
        "tool_choice" in normalized_error
        and "no endpoints found" in normalized_error
        and "support the provided" in normalized_error
    )


def _build_openrouter_tool_choice_fallback_request(request_kwargs: dict) -> dict:
    fallback_request_kwargs = dict(request_kwargs)
    fallback_request_kwargs["tool_choice"] = "auto"
    fallback_request_kwargs.pop("parallel_tool_calls", None)
    return fallback_request_kwargs


def _is_tool_execution_result_message(message: dict) -> bool:
    return str(message.get("role") or "").strip() == "system" and str(message.get("content") or "").startswith(
        TOOL_EXECUTION_RESULTS_MARKER
    )


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
        queries = arguments.get("queries")
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
    if tool_name in {"search_knowledge_base", "search_tool_memory"}:
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
    tool_previews: list[str] = []
    result_parts: list[str] = []
    recovery_hints: list[str] = []
    assistant_intent = ""
    for message in block.get("messages") or []:
        role = str(message.get("role") or "").strip()
        if role == "assistant":
            assistant_intent = assistant_intent or _extract_compaction_assistant_intent(message)
            for tool_call in message.get("tool_calls") or []:
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
            content = _extract_compaction_tool_result_preview(message)
            if content:
                result_parts.append(content)

    parts = [f"[Context: compacted tool step {block.get('step_index') or '?'}]"]
    if assistant_intent:
        parts.append(f"Assistant intent: {assistant_intent}")
    if tool_previews:
        parts.append("Actions:\n- " + "\n- ".join(tool_previews[:4]))
    if result_parts:
        parts.append("Outcomes:\n- " + "\n- ".join(result_parts[:3]))
    if recovery_hints:
        parts.append("Recovery:\n- " + "\n- ".join(recovery_hints[:2]))
    return {"role": "user", "content": "\n".join(parts)}


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


def _trace_agent_event(event: str, **fields):
    payload = {"event": event}
    for key, value in fields.items():
        payload[key] = _serialize_for_log(value)
    try:
        _get_agent_trace_logger().info(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    except Exception:
        return


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


def _build_fetch_clipped_text(result: dict, token_threshold: int, clip_aggressiveness: int) -> tuple[str, int]:
    raw_content = _clean_tool_text(result.get("content") or "")
    token_estimate = _estimate_text_tokens(raw_content)
    if not raw_content:
        return "", token_estimate

    if token_estimate <= token_threshold:
        return raw_content, token_estimate

    clip_ratio = min(1.0, token_threshold / max(token_estimate, 1))
    preserve_multiplier = min(1.0, 1.8 - (_normalize_fetch_clip_aggressiveness(clip_aggressiveness) / 100) * 1.0)
    target_chars = max(2000, min(FETCH_SUMMARY_MAX_CHARS, int(len(raw_content) * clip_ratio * preserve_multiplier)))
    clipped_content = _clean_tool_text(raw_content, limit=target_chars)
    result_text = clipped_content or raw_content
    return result_text, _estimate_text_tokens(result_text)


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
            "If you need to find specific text from this page, use grep_fetched_content instead."
        ).strip(),
    }


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


def _build_fetch_summary_source_text(result: dict) -> str:
    parts: list[str] = []
    title = _clean_tool_text(result.get("title") or "", limit=200)
    url = _clean_tool_text(result.get("url") or "", limit=240)
    meta_description = _clean_tool_text(result.get("meta_description") or "", limit=600)
    outline = result.get("outline") if isinstance(result.get("outline"), list) else []
    content = _clean_tool_text(result.get("content") or "", limit=FETCH_SUMMARIZE_MAX_INPUT_CHARS)
    if title:
        parts.append(f"Title: {title}")
    if url:
        parts.append(f"URL: {url}")
    if meta_description:
        parts.append(f"Meta description: {meta_description}")
    if outline:
        headings = [f"- {_clean_tool_text(item, limit=120)}" for item in outline[:40] if _clean_tool_text(item, limit=120)]
        if headings:
            parts.append("Page outline:\n" + "\n".join(headings))
    if content:
        parts.append("Page content:\n" + content)
    return "\n\n".join(parts).strip()


def _summarize_fetched_page_result(result: dict, focus: str, parent_model: str = "") -> tuple[dict, str]:
    settings = get_app_settings()
    summarizer_model = get_operation_model("fetch_summarize", settings, fallback_model_id=parent_model)
    target = resolve_model_target(summarizer_model, settings)
    source_text = _build_fetch_summary_source_text(result)
    if not source_text:
        raise ValueError("Fetched page did not contain enough text to summarize.")

    focus_text = _clean_tool_text(focus, limit=600)
    system_prompt = (
        "You are a precise web-page summarizer working for another AI assistant. "
        "Produce a clean factual summary of the fetched page. Remove navigation chrome, repeated boilerplate, cookie banners, and low-signal filler. "
        "If a focus question is provided, prioritize only the information relevant to that focus and state clearly when the page does not answer it. "
        "Return plain text only."
    )
    user_parts = []
    if focus_text:
        user_parts.append(f"Focus:\n{focus_text}")
    user_parts.append(source_text)
    request_kwargs = apply_model_target_request_options(
        {
            "model": target["api_model"],
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "\n\n".join(user_parts)},
            ],
            "max_tokens": FETCH_SUMMARIZE_MAX_OUTPUT_TOKENS,
            "temperature": 0.2,
        },
        target,
    )
    response = target["client"].chat.completions.create(**request_kwargs)
    summary_text = _clean_tool_text(_extract_chat_completion_text(response), limit=RAG_TOOL_RESULT_MAX_TEXT_CHARS)
    if not summary_text:
        raise ValueError("Fetch summarizer returned empty content.")

    summarized_result = {
        "url": str(result.get("url") or "").strip(),
        "title": str(result.get("title") or "").strip(),
        "summary": summary_text,
        "model": _clean_tool_text(summarizer_model, limit=120),
        "content_char_count": len(_clean_tool_text(result.get("content") or "")),
    }
    if focus_text:
        summarized_result["focus"] = focus_text
    return summarized_result, f"Page summarized: {summarized_result.get('title') or summarized_result.get('url') or 'page'}"


def _prepare_fetch_result_for_model(
    result: dict,
    fetch_url_token_threshold: int | None = None,
    fetch_url_clip_aggressiveness: int | None = None,
) -> dict:
    if not isinstance(result, dict):
        return result

    content = _clean_tool_text(result.get("content") or "")
    prepared = dict(result)
    meta_description = _clean_tool_text(result.get("meta_description") or "", limit=400)
    structured_data = _clean_tool_text(result.get("structured_data") or "", limit=1_200)
    recovery_hint = _build_recovery_hint_for_tool("fetch_url", {"url": result.get("url")})
    prepared["cleanup_applied"] = True
    prepared["content_token_estimate"] = _estimate_text_tokens(content)
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
    clipped_text, token_estimate = _build_fetch_clipped_text(prepared, token_threshold, clip_aggressiveness)
    if not clipped_text or clipped_text == content:
        return prepared

    raw_char_count = len(content)
    clipped_char_count = len(clipped_text)
    clipped_pct = int(100 * clipped_char_count / max(raw_char_count, 1))
    prepared["content"] = clipped_text
    prepared["content_mode"] = "clipped_text"
    prepared["summary_notice"] = (
        f"Content was clipped: showing {clipped_char_count:,} of {raw_char_count:,} characters "
        f"({clipped_pct}% of the page, approximately {token_estimate:,} tokens). "
        "The leading portion is preserved. "
        f"{recovery_hint or 'Use grep_fetched_content for exact text and search_tool_memory for semantic recall.'}"
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
    outline = transcript_result.get("outline")
    meta_description = _clean_tool_text(transcript_result.get("meta_description") or "", limit=260)
    structured_data = _clean_tool_text(transcript_result.get("structured_data") or "", limit=700)
    recovery_hint = _clean_tool_text(transcript_result.get("recovery_hint") or "", limit=280)
    budget_notice = _clean_tool_text(transcript_result.get("budget_notice") or "", limit=220)
    pages_extracted = transcript_result.get("pages_extracted")
    page_count = transcript_result.get("page_count")
    body = _clean_tool_text(transcript_result.get("content") or "", limit=FETCH_SUMMARY_MAX_CHARS)
    if title:
        parts.append(f"Title: {title}")
    if url:
        parts.append(f"URL: {url}")
    if content_format and content_format != "html":
        fmt_info = f"Format: {content_format}"
        if content_format == "pdf" and isinstance(pages_extracted, int) and isinstance(page_count, int):
            fmt_info += f" ({pages_extracted} of {page_count} pages extracted)"
        elif content_format == "pdf" and isinstance(pages_extracted, int):
            fmt_info += f" ({pages_extracted} pages extracted)"
        parts.append(fmt_info)
    if summary:
        parts.append(f"Summary: {_clean_tool_text(summary, limit=300)}")
    if notice:
        parts.append(f"Note: {notice}")
    if diagnostic:
        parts.append(f"Fetch status: {diagnostic}")
    if meta_description:
        parts.append(f"Description: {meta_description}")
    if structured_data:
        parts.append("Structured data:\n" + structured_data)
    if budget_notice:
        parts.append(f"Budget note: {budget_notice}")
    if recovery_hint:
        parts.append(f"Recovery: {recovery_hint}")
    if outline and isinstance(outline, list) and transcript_result.get("content_mode") in {"clipped_text", "budget_compact", "budget_brief"}:
        heading_lines = [f"  - {_clean_tool_text(str(h), limit=120)}" for h in outline[:30] if str(h).strip()]
        if heading_lines:
            parts.append("## Page Outline\n" + "\n".join(heading_lines))
    if body:
        parts.append(body)
    return "\n\n".join(parts).strip()


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
    if tool_name in CANVAS_MUTATION_TOOL_NAMES and isinstance(result, dict):
        compact_result: dict[str, object] = {}
        for key in (
            "status",
            "action",
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
        pass

    if _repair_json is not None and raw_text.lstrip().startswith("{"):
        try:
            repaired = _repair_json(raw_text, return_objects=True, ensure_ascii=False)
            if isinstance(repaired, (dict, list)):
                return repaired
        except Exception:
            pass

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


def _extract_first_balanced_json_like_object(text: str) -> str | None:
    raw_text = str(text or "")
    start_index = raw_text.find("{")
    if start_index < 0:
        return None

    depth = 0
    quote_char = ""
    escape_next = False

    for index in range(start_index, len(raw_text)):
        char = raw_text[index]
        if quote_char:
            if escape_next:
                escape_next = False
                continue
            if char == "\\":
                escape_next = True
                continue
            if char == quote_char:
                quote_char = ""
            continue

        if char in {'"', "'"}:
            quote_char = char
            continue
        if char == "{":
            depth += 1
            continue
        if char == "}":
            depth -= 1
            if depth == 0:
                return raw_text[start_index:index + 1]

    return None


def _close_unbalanced_json_like_object(text: str) -> str | None:
    raw_text = str(text or "").strip()
    if not raw_text:
        return None

    object_text = raw_text
    if not object_text.startswith("{"):
        brace_index = object_text.find("{")
        if brace_index < 0:
            return None
        object_text = object_text[brace_index:].strip()

    stack: list[str] = []
    quote_char = ""
    escape_next = False

    for char in object_text:
        if quote_char:
            if escape_next:
                escape_next = False
                continue
            if char == "\\":
                escape_next = True
                continue
            if char == quote_char:
                quote_char = ""
            continue

        if char in {'"', "'"}:
            quote_char = char
            continue
        if char in "[{":
            stack.append(char)
            continue
        if char == "]":
            if not stack or stack[-1] != "[":
                return None
            stack.pop()
            continue
        if char == "}":
            if not stack or stack[-1] != "{":
                return None
            stack.pop()

    if quote_char or escape_next or not stack:
        return None

    closing_suffix = "".join(
        "}" if opener == "{" else "]"
        for opener in reversed(stack)
    )
    return f"{object_text}{closing_suffix}"


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

        object_text = _extract_first_balanced_json_like_object(candidate)
        if object_text and object_text not in seen:
            pending.append(object_text)

        repaired_object = _close_unbalanced_json_like_object(candidate)
        if repaired_object and repaired_object not in seen:
            pending.append(repaired_object)


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
        arguments_text = raw_content[match.end():next_start]
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

    repaired_arguments = _close_unbalanced_json_like_object(raw_arguments)
    if repaired_arguments is not None:
        parsed_arguments = _parse_json_like_text(repaired_arguments)
        if isinstance(parsed_arguments, dict):
            return parsed_arguments, None

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
                    if candidate_key == raw_field_name and look_ahead < len(raw_arguments) and raw_arguments[look_ahead] == ":":
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
            hex_value = raw_arguments[index + 1:index + 5]
            if len(hex_value) < 4 or any(char not in string.hexdigits for char in hex_value):
                break
            value_chars.append(chr(int(hex_value, 16)))
            index += 5
            continue

        value_chars.append(escape_char)
        index += 1

    return "".join(value_chars)


def _build_streaming_canvas_tool_preview(tool_call_parts: list[dict]) -> dict | None:
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
        if tool_name in CANVAS_STREAM_CONTENT_TOOL_NAMES:
            content = _extract_partial_json_string_value(arguments_text, "content")

        return {
            "tool": tool_name,
            "preview_key": f"canvas-call-{preview_index}",
            "snapshot": snapshot,
            "content": content,
        }
    return None


def _finalize_stream_tool_calls(tool_call_parts: list[dict]) -> tuple[list[dict] | None, str | None]:
    if not tool_call_parts:
        return None, None

    normalized_calls = []
    for index, raw_call in enumerate(tool_call_parts, start=1):
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
                    "name": str(tool_call.get("name") or "").strip(),
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


def _validate_tool_arguments(tool_name: str, tool_args: dict) -> str | None:
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

    schema = spec.get("parameters") or {}
    properties = schema.get("properties") or {}
    required = schema.get("required") or []

    for field_name in required:
        if field_name not in tool_args:
            return f"Missing required argument '{field_name}' for {tool_name}"

    # Strip keys that are clearly not valid property names (e.g. code content that leaked
    # into a key position due to model serialisation errors: contains ';', '*', '=', spaces, etc.).
    bogus_keys = [
        k for k in list(tool_args)
        if k not in properties and not _VALID_IDENTIFIER_RE.match(k)
    ]
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
                return f"Invalid array item type for '{key}' in {tool_name}: expected {item_type}"
            min_items = property_schema.get("minItems")
            max_items = property_schema.get("maxItems")
            if tool_name == "ask_clarifying_question" and key == "questions":
                max_items = get_clarification_max_questions(get_app_settings())
            if isinstance(min_items, int) and len(value) < min_items:
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
                return f"Argument '{key}' in {tool_name} must be >= {minimum}"
            if maximum is not None and value > maximum:
                return f"Argument '{key}' in {tool_name} must be <= {maximum}"
        enum_values = property_schema.get("enum")
        if enum_values and value not in enum_values:
            return f"Argument '{key}' in {tool_name} must be one of: {', '.join(str(item) for item in enum_values)}"
    return None


def _build_final_answer_instruction() -> dict:
    return {
        "role": "system",
        "content": (
            "[INSTRUCTION: FINAL ANSWER REQUIRED]\n\n"
            "Tool execution budget is exhausted. Do not call more tools.\n"
            "Respond with the best possible final answer using the available context.\n"
            "Do not claim that an action was completed unless a tool result in this run confirms it. "
            "If work remains unfinished, say so explicitly.\n"
            "Place the final answer in assistant content, not reasoning_content."
        ),
    }


def _build_minimal_final_answer_instruction() -> dict:
    return {
        "role": "system",
        "content": "[FINAL ANSWER ONLY]\nNo tools. Answer in assistant content only.",
    }


def _build_missing_final_answer_instruction() -> dict:
    return {
        "role": "system",
        "content": (
            "[INSTRUCTION: MISSING FINAL ANSWER — RETRY]\n\n"
            "You have not returned any final answer in assistant content yet.\n"
            "Continue and respond now using assistant content only.\n"
            "If you need tools, place only the tool_calls JSON in assistant content.\n"
            "Do not place the final answer or tool JSON in reasoning_content."
        ),
    }


def _build_clarification_retry_instruction() -> dict:
    return {
        "role": "system",
        "content": (
            "[INSTRUCTION: CLARIFICATION TOOL REQUIRED — RETRY]\n\n"
            "The previous turn returned plain assistant text without the required ask_clarifying_question tool call.\n"
            "Retry now.\n"
            "If you need clarification, or if the user asked you to ask questions first, emit exactly one ask_clarifying_question tool call and no assistant prose.\n"
            "Put every question only inside the tool arguments.\n"
            "Do not say that you prepared questions unless you emit the tool call.\n"
            "Do not place the questions in reasoning_content."
        ),
    }


def _build_clarification_tool_repair_instruction(error: str) -> dict:
    cleaned_error = _clean_tool_text(error or "", limit=220)
    return {
        "role": "system",
        "content": (
            "[INSTRUCTION: CLARIFICATION TOOL REPAIR — RETRY]\n\n"
            "The previous ask_clarifying_question tool call was malformed and could not be executed.\n"
            f"Validation error: {cleaned_error or 'invalid clarification payload'}\n"
            "Retry now with exactly one ask_clarifying_question tool call and no assistant prose.\n"
            "Return a valid JSON object with optional intro, optional submit_label, and a non-empty questions array.\n"
            "Each question must be an object with id, label, and input_type.\n"
            "For single_select or multi_select, provide a non-empty options array of {label, value} objects.\n"
            "Use plain UI text only; no markdown bullets, Q:/A: prefixes, code fences, or <|...|> wrappers."
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
            if summary_notice and result_payload.get("content_mode") in {"clipped_text", "budget_compact", "budget_brief"}:
                parts.append(f"  Recovery: {summary_notice}")
            elif recovery_hint and result_payload.get("content_mode") in {"clipped_text", "budget_compact", "budget_brief"}:
                parts.append(f"  Recovery: {recovery_hint}")

    return {"role": "system", "content": "\n".join(parts)}


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
    del payload
    return ""


def _get_canvas_runtime_state(runtime_state: dict) -> dict:
    return runtime_state.setdefault("canvas", create_canvas_runtime_state())


def _run_append_scratchpad(tool_args: dict, runtime_state: dict):
    del runtime_state
    notes = tool_args.get("notes") or tool_args.get("note", "")
    section = tool_args.get("section") or "notes"
    return append_to_scratchpad(notes, section=section)


def _run_replace_scratchpad(tool_args: dict, runtime_state: dict):
    del runtime_state
    section = tool_args.get("section") or "notes"
    return replace_scratchpad(tool_args.get("new_content", ""), section=section)


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
    sub_agent_depth = _coerce_int_range(agent_context.get("sub_agent_depth"), 0, 0, 4)
    if sub_agent_depth >= 1:
        error = "Recursive sub-agent delegation is disabled."
        return {"status": "error", "error": error}, f"Failed: {error}"

    task = str(tool_args.get("task") or "").strip()
    if not task:
        error = "sub_agent requires a non-empty task."
        return {"status": "error", "error": error}, f"Failed: {error}"
    parent_context = str(tool_args.get("context") or "").strip()

    parent_visible_tools = _normalize_tool_name_list(
        agent_context.get("prompt_tool_names")
        if isinstance(agent_context.get("prompt_tool_names"), list)
        else agent_context.get("enabled_tool_names")
    )
    child_tool_names = _resolve_sub_agent_tool_names(tool_args.get("allowed_tools"), parent_visible_tools)
    if not child_tool_names:
        error = "No eligible read-only tools are available for sub-agent delegation."
        return {"status": "error", "error": error}, f"Failed: {error}"

    settings = get_app_settings()
    parent_model = str(agent_context.get("model") or "").strip()
    child_model_candidates = get_operation_model_candidates("sub_agent", settings, fallback_model_id=parent_model)
    child_max_parallel_tools = get_sub_agent_max_parallel_tools(settings)
    timeout_seconds = _coerce_int_range(
        tool_args.get("timeout_seconds"),
        get_sub_agent_timeout_seconds(settings),
        SUB_AGENT_TIMEOUT_MIN_SECONDS,
        SUB_AGENT_TIMEOUT_MAX_SECONDS,
    )
    retry_attempts = get_sub_agent_retry_attempts(settings)
    retry_delay_seconds = get_sub_agent_retry_delay_seconds(settings)
    overall_deadline = time.monotonic() + timeout_seconds

    conversation_handoff = str(agent_context.get("conversation_handoff") or "").strip()
    canvas_handoff = _build_sub_agent_canvas_handoff(runtime_state)
    child_max_steps = _resolve_sub_agent_max_steps(
        tool_args,
        task=task,
        parent_context=parent_context,
        conversation_handoff=conversation_handoff,
        canvas_handoff=canvas_handoff,
        allowed_tools=child_tool_names,
    )
    child_messages = _build_sub_agent_messages(
        task,
        parent_context,
        conversation_handoff,
        canvas_handoff,
        child_tool_names,
        max_parallel_tools=child_max_parallel_tools,
    )
    resume_messages: list[dict] = []
    fallback_attempts: list[dict[str, str]] = []
    final_result: dict | None = None
    final_summary = ""

    for attempt_index, child_model in enumerate(child_model_candidates, start=1):
        retry_messages = [*child_messages, *resume_messages]
        retry_count = 0

        while True:
            attempt_messages = list(retry_messages)
            attempt_started_at = time.monotonic()
            remaining_overall_seconds = max(0.0, overall_deadline - attempt_started_at)
            if remaining_overall_seconds <= 0:
                timeout_error = f"Sub-agent timed out after {timeout_seconds} seconds."
                final_result = {
                    "status": "error",
                    "summary": timeout_error,
                    "model": _clean_tool_text(child_model_candidates[max(0, attempt_index - 2)] if child_model_candidates else parent_model, limit=120),
                    "error": timeout_error,
                    "timed_out": True,
                }
                if fallback_attempts:
                    final_result["fallback_attempts"] = list(fallback_attempts)
                return final_result, f"Failed: {timeout_error}"

            remaining_attempts = len(child_model_candidates) - attempt_index + 1
            attempt_timeout_seconds = max(1, int(math.ceil(remaining_overall_seconds / max(1, remaining_attempts))))
            attempt_deadline = min(overall_deadline, attempt_started_at + attempt_timeout_seconds)
            attempt_timeout_seconds = max(1, int(math.ceil(max(0.0, attempt_deadline - attempt_started_at))))

            child_tool_trace: list[dict] = []
            child_tool_trace_map: dict[str, int] = {}
            child_history: list[dict] = []
            child_tool_results: list[dict] = []
            child_answer = ""
            child_reasoning = ""
            child_errors: list[str] = []
            timed_out = False
            retryable_model_error = False
            fallback_attempt_logged = False

            yield {
                "type": "sub_agent_trace_update",
                "entry": _build_sub_agent_stream_entry(task, child_model, child_tool_trace, status="running"),
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
                    initial_canvas_active_document_id=get_canvas_runtime_active_document_id(runtime_state.get("canvas")),
                    canvas_expand_max_lines=((runtime_state.get("canvas_limits") or {}).get("expand_max_lines") if isinstance(runtime_state.get("canvas_limits"), dict) else None),
                    canvas_scroll_window_lines=((runtime_state.get("canvas_limits") or {}).get("scroll_window_lines") if isinstance(runtime_state.get("canvas_limits"), dict) else None),
                    workspace_runtime_state=runtime_state.get("workspace"),
                    agent_context={"sub_agent_depth": sub_agent_depth + 1},
                )
                try:
                    for event in child_events:
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
                            _upsert_sub_agent_tool_trace(child_tool_trace, child_tool_trace_map, event)
                            yield {
                                "type": "sub_agent_trace_update",
                                "entry": _build_sub_agent_stream_entry(task, child_model, child_tool_trace, status="running"),
                            }
                            if event_type == "tool_error":
                                error_text = _clean_tool_text(event.get("error") or "", limit=SUB_AGENT_MAX_ERROR_CHARS)
                                if error_text:
                                    if str(event.get("tool") or "").strip() == "api" and _is_retryable_model_error(error_text):
                                        retryable_model_error = True
                                        break
                                    child_errors.append(error_text)
                        elif event_type == "tool_capture":
                            child_tool_results = event.get("tool_results") if isinstance(event.get("tool_results"), list) else []
                        elif event_type == "tool_history":
                            raw_messages = event.get("messages") if isinstance(event.get("messages"), list) else []
                            for message in raw_messages:
                                normalized_message = _normalize_sub_agent_history_message(message)
                                if normalized_message is not None and len(child_history) < SUB_AGENT_MAX_TRANSCRIPT_MESSAGES:
                                    child_history.append(normalized_message)
                finally:
                    close_method = getattr(child_events, "close", None)
                    if callable(close_method):
                        close_method()
            except Exception as exc:
                error_text = _clean_tool_text(str(exc), limit=SUB_AGENT_MAX_ERROR_CHARS)
                if _is_retryable_model_error(exc):
                    retryable_model_error = True
                else:
                    child_errors.append(error_text)

            child_answer = _clean_tool_text(child_answer, limit=SUB_AGENT_MAX_SUMMARY_CHARS)
            child_reasoning = _clean_tool_text(child_reasoning, limit=SUB_AGENT_MAX_REASONING_CHARS)
            if child_answer:
                child_history.append({"role": "assistant", "content": child_answer})
            normalized_tool_trace = _normalize_sub_agent_tool_trace(child_tool_trace)
            trace_error_text = next(
                (
                    _clean_tool_text(entry.get("summary") or f"{entry.get('tool_name', 'tool')} failed.", limit=SUB_AGENT_MAX_ERROR_CHARS)
                    for entry in reversed(normalized_tool_trace)
                    if isinstance(entry, dict) and entry.get("state") == "error"
                ),
                "",
            )
            if trace_error_text and trace_error_text not in child_errors:
                child_errors.append(trace_error_text)

            error_text = _clean_tool_text(child_errors[-1], limit=SUB_AGENT_MAX_ERROR_CHARS) if child_errors else ""

            artifacts = _build_sub_agent_artifacts(child_history, child_tool_results)
            summary_text = child_answer or error_text or "Sub-agent finished without a final summary."

            has_partial_output = bool(child_answer or normalized_tool_trace or artifacts or child_history)
            result_status = "ok"
            if timed_out or error_text or retryable_model_error:
                result_status = "partial" if has_partial_output else "error"

            if (timed_out or retryable_model_error) and retry_count < retry_attempts and time.monotonic() < overall_deadline:
                retry_reason = "a timeout" if timed_out else "a model error"
                resume_messages.extend(_build_sub_agent_retry_messages(child_history))
                resume_messages.append(_build_sub_agent_resume_message(child_model, retry_reason))
                retry_count += 1
                sleep_for = min(float(retry_delay_seconds), max(0.0, overall_deadline - time.monotonic()))
                if sleep_for > 0:
                    time.sleep(sleep_for)
                retry_messages = [*child_messages, *resume_messages]
                continue

            has_more_candidates = attempt_index < len(child_model_candidates)
            fallback_continues = has_more_candidates and result_status != "ok"
            fallback_note = ""
            if fallback_continues:
                next_model = _clean_tool_text(child_model_candidates[attempt_index], limit=120)
                reason_label = "timeout" if timed_out else "model error"
                prompt_reason_label = "a timeout" if timed_out else "a model error"
                fallback_note = f"Continued on {next_model} after {reason_label}."
                if not fallback_attempt_logged:
                    fallback_attempts.append({"model": child_model, "error": error_text or fallback_note or "Retryable model failure."})
                    fallback_attempt_logged = True
                resume_messages.extend(_build_sub_agent_retry_messages(child_history))
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
                "tool_trace": normalized_tool_trace,
                "artifacts": artifacts,
                "messages": child_history[:SUB_AGENT_MAX_TRANSCRIPT_MESSAGES],
            }
            if cleaned_task:
                trace_entry["task"] = cleaned_task
            if full_task and full_task != cleaned_task:
                trace_entry["task_full"] = full_task
            if fallback_attempts:
                trace_entry["fallback_attempts"] = list(fallback_attempts)
            if fallback_note:
                trace_entry["fallback_note"] = fallback_note
            if child_reasoning:
                trace_entry["reasoning"] = child_reasoning
            if timed_out:
                trace_entry["timed_out"] = True
            if fallback_continues:
                error_text = ""
            if error_text:
                trace_entry["error"] = error_text
            _append_sub_agent_trace(runtime_state, trace_entry)
            yield {"type": "sub_agent_trace_update", "entry": trace_entry}

            final_result = {
                "status": result_status,
                "summary": summary_text,
                "tool_trace": normalized_tool_trace,
            }
            if artifacts:
                final_result["artifacts"] = artifacts
            if fallback_attempts:
                final_result["fallback_attempts"] = list(fallback_attempts)
            if error_text:
                final_result["error"] = error_text
            if timed_out:
                final_result["timed_out"] = True
            if fallback_note:
                final_result["fallback_note"] = fallback_note
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
                return final_result, final_summary

            if fallback_continues:
                break
            return final_result, final_summary

    if final_result is None:
        final_error = fallback_attempts[-1]["error"] if fallback_attempts else "Sub-agent could not complete the delegated task."
        final_result = {
            "status": "error",
            "summary": final_error,
            "model": _clean_tool_text(child_model_candidates[-1] if child_model_candidates else parent_model, limit=120),
            "error": final_error,
        }
        if fallback_attempts:
            final_result["fallback_attempts"] = list(fallback_attempts)
        return final_result, f"Failed: {final_error}"

    return final_result, final_summary


def _run_image_explain(tool_args: dict, runtime_state: dict):
    del runtime_state
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
    )
    return {
        "status": "ok",
        "image_id": image_id,
        "conversation_id": normalized_conversation_id,
        "answer": answer,
    }, "Image question answered"


def _run_search_knowledge_base(tool_args: dict, runtime_state: dict):
    del runtime_state
    result = search_knowledge_base_tool(
        tool_args.get("query", ""),
        category=tool_args.get("category"),
        top_k=tool_args.get("top_k", RAG_SEARCH_DEFAULT_TOP_K),
        allowed_source_types=get_rag_source_types(),
        min_similarity=tool_args.get("min_similarity"),
    )
    return result, f"{result.get('count', 0)} knowledge chunks found"


def _run_search_tool_memory(tool_args: dict, runtime_state: dict):
    del runtime_state
    result = search_tool_memory(
        tool_args.get("query", ""),
        top_k=tool_args.get("top_k", RAG_SEARCH_DEFAULT_TOP_K),
        min_similarity=tool_args.get("min_similarity"),
    )
    return result, f"{result.get('count', 0)} tool memory matches found"


def _run_search_web(tool_args: dict, runtime_state: dict):
    del runtime_state
    result = _merge_batched_search_results([search_web_tool(batch) for batch in _iter_search_query_batches(tool_args.get("queries", []))])
    ok_count = sum(1 for row in result if "error" not in row)
    return result, f"{ok_count} web results found"


def _run_search_news_ddgs(tool_args: dict, runtime_state: dict):
    del runtime_state
    result = _merge_batched_search_results(
        [
            search_news_ddgs_tool(
                batch,
                lang=tool_args.get("lang", "tr"),
                when=tool_args.get("when"),
            )
            for batch in _iter_search_query_batches(tool_args.get("queries", []))
        ]
    )
    ok_count = sum(1 for row in result if "error" not in row)
    return result, f"{ok_count} news articles found"


def _run_search_news_google(tool_args: dict, runtime_state: dict):
    del runtime_state
    result = _merge_batched_search_results(
        [
            search_news_google_tool(
                batch,
                lang=tool_args.get("lang", "tr"),
                when=tool_args.get("when"),
            )
            for batch in _iter_search_query_batches(tool_args.get("queries", []))
        ]
    )
    ok_count = sum(1 for row in result if "error" not in row)
    return result, f"{ok_count} news articles found"


def _run_fetch_url(tool_args: dict, runtime_state: dict):
    del runtime_state
    result = fetch_url_tool(tool_args.get("url", ""))
    return result, _summarize_fetch_result(result, tool_args.get("url", ""))


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
    return _summarize_fetched_page_result(result, focus, parent_model=parent_model)


def _run_grep_fetched_content(tool_args: dict, runtime_state: dict):
    del runtime_state
    result = grep_fetched_content_tool(
        url=tool_args.get("url", ""),
        pattern=tool_args.get("pattern", ""),
        context_lines=tool_args.get("context_lines", 2),
        max_matches=tool_args.get("max_matches", 20),
    )
    match_count = result.get("match_count", 0)
    if result.get("error"):
        summary = f"grep_fetched_content error: {_clean_tool_text(result['error'], limit=120)}"
    elif match_count == 0:
        summary = f"grep_fetched_content: no matches for pattern '{_clean_tool_text(tool_args.get('pattern', ''), limit=60)}'"
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
    canvas_limits = runtime_state.get("canvas_limits") if isinstance(runtime_state.get("canvas_limits"), dict) else {}
    expand_max_lines = int(canvas_limits.get("expand_max_lines") or 0) or None
    result = build_canvas_document_context_result(
        canvas_state,
        document_id=tool_args.get("document_id"),
        document_path=tool_args.get("document_path"),
        max_lines=expand_max_lines,
        max_chars=scale_canvas_char_limit(expand_max_lines, default_lines=800, default_chars=20_000) if expand_max_lines else None,
    )
    target_label = str(result.get("document_path") or result.get("title") or "Canvas").strip()
    return result, f"Canvas expanded: {target_label}"


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
        max_results=tool_args.get("max_results") or 10,
    )
    if result.get("all_documents"):
        scope_label = "all canvas documents"
    else:
        first_match = (result.get("matches") or [{}])[0]
        scope_label = str(first_match.get("document_path") or first_match.get("title") or "active canvas").strip()
    return result, f"{len(result.get('matches') or [])} canvas matches found in {scope_label}"


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
    )
    changed_ranges = batch_result.get("changed_ranges") or []
    edit_start_line = None
    edit_end_line = None
    if changed_ranges:
        edit_start_line = min(int(entry.get("edit_start_line") or 0) for entry in changed_ranges if entry.get("edit_start_line"))
        edit_end_line = max(int(entry.get("edit_end_line") or 0) for entry in changed_ranges if entry.get("edit_end_line"))
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
        tool_args.get("operations") or [],
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
        add_dependencies=tool_args.get("add_dependencies"),
        remove_dependencies=tool_args.get("remove_dependencies"),
        add_symbols=tool_args.get("add_symbols"),
    )
    tool_result = build_canvas_tool_result(result["document"], action="metadata_updated")
    tool_result["updated_fields"] = result.get("updated_fields") or []
    return tool_result, f"Canvas metadata updated for {result['document']['title']}"


def _run_set_canvas_viewport(tool_args: dict, runtime_state: dict):
    canvas_state = _get_canvas_runtime_state(runtime_state)
    auto_unpin_on_edit = True if "auto_unpin_on_edit" not in tool_args else tool_args.get("auto_unpin_on_edit") is True
    result = set_canvas_viewport(
        canvas_state,
        start_line=int(tool_args.get("start_line") or 0),
        end_line=int(tool_args.get("end_line") or 0),
        ttl_turns=int(tool_args.get("ttl_turns") or 0) if tool_args.get("ttl_turns") not in (None, "") else 3,
        auto_unpin_on_edit=auto_unpin_on_edit,
        document_id=tool_args.get("document_id"),
        document_path=tool_args.get("document_path"),
    )
    pinned = result.get("pinned") if isinstance(result.get("pinned"), dict) else {}
    target_label = str(pinned.get("document_path") or pinned.get("document_id") or "Canvas").strip()
    return result, f"Canvas viewport pinned for {target_label}"


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


_TOOL_EXECUTORS = {
    "append_scratchpad": _run_append_scratchpad,
    "replace_scratchpad": _run_replace_scratchpad,
    "read_scratchpad": _run_read_scratchpad,
    "ask_clarifying_question": _run_ask_clarifying_question,
    "sub_agent": _run_sub_agent,
    "image_explain": _run_image_explain,
    "search_knowledge_base": _run_search_knowledge_base,
    "search_tool_memory": _run_search_tool_memory,
    "search_web": _run_search_web,
    "search_news_ddgs": _run_search_news_ddgs,
    "search_news_google": _run_search_news_google,
    "fetch_url": _run_fetch_url,
    "fetch_url_summarized": _run_fetch_url_summarized,
    "grep_fetched_content": _run_grep_fetched_content,
    "expand_canvas_document": _run_expand_canvas_document,
    "scroll_canvas_document": _run_scroll_canvas_document,
    "search_canvas_document": _run_search_canvas_document,
    "create_directory": _run_create_directory,
    "create_file": _run_create_file,
    "update_file": _run_update_file,
    "read_file": _run_read_file,
    "list_dir": _run_list_dir,
    "search_files": _run_search_files,
    "write_project_tree": _run_write_project_tree,
    "validate_project_workspace": _run_validate_project_workspace,
    "create_canvas_document": _run_create_canvas_document,
    "rewrite_canvas_document": _run_rewrite_canvas_document,
    "preview_canvas_changes": _run_preview_canvas_changes,
    "transform_canvas_lines": _run_transform_canvas_lines,
    "update_canvas_metadata": _run_update_canvas_metadata,
    "set_canvas_viewport": _run_set_canvas_viewport,
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
    handler = _TOOL_EXECUTORS.get(tool_name)
    if handler is not None:
        return handler(tool_args if isinstance(tool_args, dict) else {}, runtime_state)
    return {"error": f"Unknown tool: {tool_name}"}, f"Unknown tool: {tool_name}"


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
    tool_args = tool_args if isinstance(tool_args, dict) else {}
    if tool_name in {"search_web", "search_news_ddgs", "search_news_google"}:
        values = tool_args.get("queries")
        if isinstance(values, list):
            return ", ".join(str(value).strip() for value in values if str(value).strip())[:300]
    if tool_name in {"search_knowledge_base", "search_tool_memory"}:
        return str(tool_args.get("query") or "").strip()[:300]
    if tool_name == "fetch_url":
        return str(tool_args.get("url") or "").strip()[:300]
    if tool_name == "fetch_url_summarized":
        url = str(tool_args.get("url") or "").strip()
        focus = str(tool_args.get("focus") or "").strip()
        if url and focus:
            return f"{url} | {focus}"[:300]
        return url[:300]
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
        task = str(tool_args.get("task") or "").strip()
        context = str(tool_args.get("context") or "").strip()
        if task and context:
            return f"{task} | {context}"[:300]
        return task[:300]
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

    if tool_name == "fetch_url" and isinstance(transcript_result, dict):
        return _build_fetch_tool_message_content(tool_args, summary, transcript_result)

    if isinstance(transcript_result, str):
        return _clean_tool_text(transcript_result, limit=RAG_TOOL_RESULT_MAX_TEXT_CHARS)

    try:
        return _serialize_tool_message_content(transcript_result)
    except Exception:
        return _serialize_tool_message_content({"tool_name": tool_name, "summary": _clean_tool_text(summary, limit=300)})


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


def _build_tool_result_storage_entry(tool_name: str, tool_args: dict, result, summary: str, transcript_result=None) -> dict | None:
    if tool_name in {"search_knowledge_base", "search_tool_memory"}:
        return None

    text = ""
    if tool_name == "fetch_url":
        if isinstance(result, dict):
            display_result = transcript_result if isinstance(transcript_result, dict) else result
            display_content = _clean_tool_text(display_result.get("content") or "", limit=RAG_TOOL_RESULT_MAX_TEXT_CHARS)
            raw_content = _clean_tool_text(result.get("content") or "", limit=FETCH_RAW_TOOL_RESULT_MAX_TEXT_CHARS)
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
            label = _clean_tool_text(artifact.get("label") or artifact.get("title") or artifact.get("type") or "artifact", limit=80)
            artifact_summary = _clean_tool_text(artifact.get("summary") or artifact.get("content") or "", limit=160)
            if label and artifact_summary:
                artifact_lines.append(f"- {label}: {artifact_summary}")
        if artifact_lines:
            parts.append("Artifacts:\n" + "\n".join(artifact_lines))
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
        raw_content = _clean_tool_text(result.get("content") or "", limit=FETCH_RAW_TOOL_RESULT_MAX_TEXT_CHARS)
        display_content = _clean_tool_text(display_result.get("content") or "", limit=FETCH_RAW_TOOL_RESULT_MAX_TEXT_CHARS)
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
        if recovery_hint:
            compacted["recovery_hint"] = recovery_hint
        return compacted

    serialized = transcript_result if isinstance(transcript_result, str) else _serialize_tool_message_content(
        transcript_result if transcript_result is not None else result
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
    error_text = _clean_tool_text(entry.get("execution_error") or "", limit=max(80, min(char_limit, 140 if ultra_compact else 240)))
    recovery_hint = _clean_tool_text(_build_recovery_hint_for_tool(tool_name, tool_args), limit=180 if ultra_compact else 220)

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
        summary = str(entry.get("summary") or "").strip()
        cached = entry.get("cached") is True
        execution_error = str(entry.get("execution_error") or "").strip()

        if execution_error:
            tool_messages.append(
                {
                    "id": call_id,
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
                "id": call_id,
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
    fetch_url_token_threshold: int | None = None,
    fetch_url_clip_aggressiveness: int | None = None,
) -> tuple[list[dict], list[dict], dict | None, bool]:
    if not tool_output_entries:
        return [], [], None, False

    soft_limit = max(1, int(PROMPT_MAX_INPUT_TOKENS * AGENT_CONTEXT_COMPACTION_THRESHOLD))

    def _estimate_total_tokens(tool_messages: list[dict], tool_execution_result_message: dict | None) -> int:
        candidate_messages = [*base_messages, *tool_messages]
        if tool_execution_result_message is not None:
            candidate_messages.append(tool_execution_result_message)
        return _estimate_messages_tokens(candidate_messages)

    full_tool_messages, full_transcript_results, full_tool_execution_result_message = _render_tool_output_entries(tool_output_entries)
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

    compact_tool_messages, compact_transcript_results, compact_tool_execution_result_message = _render_tool_output_entries(compacted_entries)
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

    ultra_tool_messages, ultra_transcript_results, ultra_tool_execution_result_message = _render_tool_output_entries(ultra_entries)
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
    if tool_name in {"fetch_url", "fetch_url_summarized", "sub_agent"}:
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

    if tool_name not in {"search_web", "search_news_ddgs", "search_news_google"}:
        return None

    query = _tool_input_preview(tool_name, tool_args)
    if not query:
        return None

    try:
        matches = (search_tool_memory(query, top_k=1).get("matches") or [])[:1]
    except Exception:
        return None
    if not matches:
        return None

    best_match = matches[0]
    similarity = best_match.get("similarity")
    if not isinstance(similarity, (int, float)) or similarity < 0.85:
        return None

    excerpt = _clean_tool_text(best_match.get("text") or "", limit=RAG_TOOL_RESULT_MAX_TEXT_CHARS)
    if not excerpt:
        return None

    source_name = _clean_tool_text(best_match.get("source_name") or "Tool memory", limit=120)
    summary = _prefix_cross_turn_tool_memory_summary("", f"Reused tool memory from {source_name}")
    return excerpt, summary


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


def _append_reasoning_replay_entry(reasoning_state: dict, step: int, reasoning_text: str, tool_calls: list[dict] | None) -> None:
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
        str(tool_call.get("name") or "").strip()
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
    parts.append("Prefer a different tool or produce the best available answer if these blockers make repetition low-value.")
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
    temperature: float = 0.7,
    fetch_url_token_threshold: int | None = None,
    fetch_url_clip_aggressiveness: int | None = None,
    initial_canvas_documents: list[dict] | None = None,
    initial_canvas_active_document_id: str | None = None,
    canvas_expand_max_lines: int | None = None,
    canvas_scroll_window_lines: int | None = None,
    workspace_runtime_state: dict | None = None,
    agent_context: dict | None = None,
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
    usage_totals = {
        "prompt_tokens": 0,
        "prompt_cache_hit_tokens": 0,
        "prompt_cache_miss_tokens": 0,
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
    normalized_prompt_tool_names = [
        name
        for name in _normalize_tool_name_list(prompt_tool_names if prompt_tool_names is not None else enabled_tool_names)
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
        "workspace": workspace_runtime_state if isinstance(workspace_runtime_state, dict) else create_workspace_runtime_state(),
    }
    runtime_state["agent_context"] = {
        "model": str(model or "").strip(),
        "enabled_tool_names": normalized_enabled_tool_names,
        "prompt_tool_names": normalized_prompt_tool_names,
        "max_parallel_tools": normalized_parallel_tool_limit,
        "sub_agent_depth": _coerce_int_range((agent_context or {}).get("sub_agent_depth"), 0, 0, 8),
        "conversation_handoff": _build_sub_agent_conversation_handoff(messages),
    }
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
    model_target = resolve_model_target(model, model_settings)
    native_reasoning_continuation = str(model_target["record"].get("provider") or "").strip() == OPENROUTER_PROVIDER
    pricing = get_model_pricing(model, model_settings)
    pricing_known = has_known_model_pricing(model, model_settings)

    def build_tool_capture_event() -> dict:
        current_canvas_snapshot = get_canvas_runtime_snapshot(runtime_state.get("canvas"))
        current_canvas_documents = current_canvas_snapshot.get("documents") or []
        active_canvas_document_id = current_canvas_snapshot.get("active_document_id")
        sub_agent_traces = runtime_state.get("sub_agent_traces") if isinstance(runtime_state.get("sub_agent_traces"), list) else []
        return {
            "type": "tool_capture",
            "tool_results": persisted_tool_results,
            "canvas_documents": current_canvas_documents,
            "active_document_id": active_canvas_document_id,
            "canvas_viewports": current_canvas_snapshot.get("viewports") or {},
            "canvas_modified": canvas_modified,
            "canvas_cleared": canvas_modified and not current_canvas_documents,
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
    )

    def add_usage(usage):
        if not usage:
            return {
                "prompt_tokens": 0,
                "prompt_cache_hit_tokens": 0,
                "prompt_cache_miss_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "received": False,
                "cache_hit_present": False,
                "cache_miss_present": False,
                "cache_metrics_present": False,
            }

        metrics = _extract_usage_metrics(usage)
        prompt_tokens = metrics["prompt_tokens"]
        prompt_cache_hit_tokens = metrics["prompt_cache_hit_tokens"]
        prompt_cache_miss_tokens = metrics["prompt_cache_miss_tokens"]
        completion_tokens = metrics["completion_tokens"]
        total_tokens = metrics["total_tokens"]
        return {
            "prompt_tokens": prompt_tokens,
            "prompt_cache_hit_tokens": prompt_cache_hit_tokens,
            "prompt_cache_miss_tokens": prompt_cache_miss_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "received": any(
                value > 0
                for value in (
                    prompt_tokens,
                    prompt_cache_hit_tokens,
                    prompt_cache_miss_tokens,
                    completion_tokens,
                    total_tokens,
                )
            ),
            "cache_hit_present": bool(metrics.get("cache_hit_present")),
            "cache_miss_present": bool(metrics.get("cache_miss_present")),
            "cache_metrics_present": bool(metrics.get("cache_metrics_present")),
        }

    def calculate_cost(
        prompt_tokens,
        completion_tokens,
        prompt_cache_hit_tokens=0,
        prompt_cache_miss_tokens=None,
    ):
        prompt_tokens = _coerce_usage_int(prompt_tokens)
        completion_tokens = _coerce_usage_int(completion_tokens)
        prompt_cache_hit_tokens = _coerce_usage_int(prompt_cache_hit_tokens)
        if prompt_cache_miss_tokens is None:
            prompt_cache_miss_tokens = prompt_tokens if prompt_cache_hit_tokens <= 0 else max(0, prompt_tokens - prompt_cache_hit_tokens)
        else:
            prompt_cache_miss_tokens = _coerce_usage_int(prompt_cache_miss_tokens)
            accounted_prompt_tokens = prompt_cache_hit_tokens + prompt_cache_miss_tokens
            if prompt_tokens > accounted_prompt_tokens:
                prompt_cache_miss_tokens += prompt_tokens - accounted_prompt_tokens

        cache_hit_input_rate = pricing.get("input_cache_hit", pricing["input"]) or pricing["input"]
        input_cost = (prompt_cache_hit_tokens / 1_000_000) * cache_hit_input_rate
        input_cost += (prompt_cache_miss_tokens / 1_000_000) * pricing["input"]
        output_cost = (completion_tokens / 1_000_000) * pricing["output"]
        return round(input_cost + output_cost, 6)

    def apply_context_compaction(extra_messages: list[dict] | None = None, reason: str = "", force: bool = False):
        nonlocal messages
        extra_messages = list(extra_messages or [])
        turn_messages = [*messages, *extra_messages]
        threshold = max(1, int(PROMPT_MAX_INPUT_TOKENS * AGENT_CONTEXT_COMPACTION_THRESHOLD))
        before_tokens = _estimate_messages_tokens(turn_messages)
        before_message_count = len(turn_messages)
        before_exchange_count = _count_exchange_blocks(messages)
        if not force and before_tokens <= threshold:
            return turn_messages, False

        compacted_messages = _try_compact_messages(
            messages,
            max(1, int(PROMPT_MAX_INPUT_TOKENS * 0.75)),
            keep_recent=0 if force else AGENT_CONTEXT_COMPACTION_KEEP_RECENT_ROUNDS,
        )
        if compacted_messages is None:
            return turn_messages, False

        messages = compacted_messages
        compacted_turn_messages = [*messages, *extra_messages]
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
            keep_recent=0 if force else AGENT_CONTEXT_COMPACTION_KEEP_RECENT_ROUNDS,
        )
        return compacted_turn_messages, True

    def usage_event():
        prompt_tokens_total = max(0, int(usage_totals["prompt_tokens"] or 0))
        input_breakdown = dict(usage_totals["input_breakdown"])
        estimated_input_tokens = max(0, int(usage_totals["estimated_input_tokens"] or 0))
        if prompt_tokens_total > 0:
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
            )
        return {
            "type": "usage",
            "prompt_tokens": prompt_tokens_total,
            "prompt_cache_hit_tokens": usage_totals["prompt_cache_hit_tokens"],
            "prompt_cache_miss_tokens": usage_totals["prompt_cache_miss_tokens"],
            "completion_tokens": usage_totals["completion_tokens"],
            "total_tokens": usage_totals["total_tokens"],
            "estimated_input_tokens": estimated_input_tokens,
            "input_breakdown": input_breakdown,
            "model_call_count": usage_totals["model_call_count"],
            "model_calls": list(usage_totals["model_calls"]),
            "max_input_tokens_per_call": call_usage_summary["max_input_tokens_per_call"],
            "configured_prompt_max_input_tokens": PROMPT_MAX_INPUT_TOKENS,
            "cost": total_cost,
            "cost_available": pricing_known,
            "currency": "USD",
            "model": model,
            "provider": model_target["record"]["provider"],
            "cache_metrics_estimated": usage_totals["cache_metrics_estimated"],
        }

    def remember_tool_result(tool_name: str, tool_args: dict, result, summary: str, cache_key: str, transcript_result=None):
        if cache_key in persisted_tool_cache_keys:
            return
        entry = _build_tool_result_storage_entry(tool_name, tool_args, result, summary, transcript_result=transcript_result)
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
            "completion_tokens": 0,
            "total_tokens": 0,
            "received": False,
            "cache_hit_present": False,
            "cache_miss_present": False,
            "cache_metrics_present": False,
        }
        _trace_agent_event(
            "model_turn_started",
            trace_id=trace_id,
            step=step,
            message_count=len(messages_to_send),
            messages=_summarize_messages_for_log(messages_to_send),
        )

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
            turn_tools = get_openai_tool_specs(
                prompt_enabled_tool_names,
                canvas_documents=current_canvas_documents,
                clarification_max_questions=get_clarification_max_questions(model_settings),
            )
            if turn_tools:
                request_kwargs["tools"] = turn_tools
                forced_tool_choice = _build_retry_tool_choice(retry_reason, prompt_enabled_tool_names)
                request_kwargs["tool_choice"] = forced_tool_choice or "auto"
                if forced_tool_choice is not None:
                    request_kwargs["parallel_tool_calls"] = False
        request_kwargs = apply_model_target_request_options(request_kwargs, model_target)
        cache_estimate_context = build_openrouter_cache_estimate_context(
            request_kwargs.get("messages"),
            model_target.get("record") if isinstance(model_target, dict) else None,
        )
        try:
            response = model_target["client"].chat.completions.create(**request_kwargs)
        except Exception as exc:
            if not _is_openrouter_unsupported_tool_choice_error(exc, request_kwargs, model_target):
                raise
            fallback_request_kwargs = _build_openrouter_tool_choice_fallback_request(request_kwargs)
            _trace_agent_event(
                "openrouter_tool_choice_fallback",
                trace_id=trace_id,
                step=step,
                retry_reason=retry_reason,
                error=str(exc),
                original_tool_choice=request_kwargs.get("tool_choice"),
            )
            request_kwargs = fallback_request_kwargs
            cache_estimate_context = build_openrouter_cache_estimate_context(
                request_kwargs.get("messages"),
                model_target.get("record") if isinstance(model_target, dict) else None,
            )
            response = model_target["client"].chat.completions.create(**request_kwargs)

        def finalize_call_usage() -> tuple[dict[str, int], int, int]:
            nonlocal provider_usage
            estimated_breakdown, estimated_input_tokens, tool_schema_tokens = _estimate_input_breakdown(
                messages_to_send,
                provider_prompt_tokens=provider_usage["prompt_tokens"] if provider_usage["received"] else None,
                request_tools=turn_tools,
            )
            prompt_token_basis = provider_usage["prompt_tokens"] if provider_usage["prompt_tokens"] > 0 else estimated_input_tokens
            cache_hit_tokens = provider_usage["prompt_cache_hit_tokens"] if provider_usage["cache_hit_present"] else None
            cache_miss_tokens = provider_usage["prompt_cache_miss_tokens"] if provider_usage["cache_miss_present"] else None
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
                    cache_miss_tokens = _coerce_usage_int(cache_miss_tokens) + (prompt_token_basis - accounted_prompt_tokens)
                    cache_metrics_estimated = True
                if isinstance(cache_estimate_context, dict):
                    openrouter_cache_estimate_state["previous_cacheable_text"] = str(cache_estimate_context.get("cacheable_text") or "")

            final_cache_hit_tokens = _coerce_usage_int(cache_hit_tokens)
            final_cache_miss_tokens = _coerce_usage_int(cache_miss_tokens)

            usage_totals["prompt_tokens"] += provider_usage["prompt_tokens"]
            usage_totals["prompt_cache_hit_tokens"] += final_cache_hit_tokens
            usage_totals["prompt_cache_miss_tokens"] += final_cache_miss_tokens
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
                    "completion_tokens": provider_usage["completion_tokens"] if provider_usage["received"] else None,
                    "total_tokens": provider_usage["total_tokens"] if provider_usage["received"] else None,
                    "estimated_input_tokens": estimated_input_tokens,
                    "input_breakdown": dict(estimated_breakdown),
                    "missing_provider_usage": not provider_usage["received"],
                    "cache_metrics_estimated": cache_metrics_estimated,
                }
            )
            if provider_usage["received"]:
                usage_totals["estimated_input_tokens"] += estimated_input_tokens
                for key, value in estimated_breakdown.items():
                    usage_totals["input_breakdown"][key] += value
            return estimated_breakdown, estimated_input_tokens, tool_schema_tokens

        try:
            if getattr(response, "choices", None):
                provider_usage = add_usage(getattr(response, "usage", None))
                finalize_call_usage()
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

            try:
                for chunk in response:
                    reasoning_delta, content_delta, reasoning_details_delta = _extract_stream_delta_texts(chunk)
                    if reasoning_details_delta:
                        turn_reasoning_details = _merge_reasoning_details(turn_reasoning_details, reasoning_details_delta)
                    if reasoning_delta:
                        reasoning_parts.append(reasoning_delta)
                        for event in emit_turn_reasoning(reasoning_delta):
                            yield event
                    if getattr(chunk, "choices", None):
                        delta = getattr(chunk.choices[0], "delta", None)
                        if delta is not None:
                            _merge_stream_tool_call_delta(tool_call_parts, delta)
                            canvas_preview = _build_streaming_canvas_tool_preview(tool_call_parts)
                            if canvas_preview is not None:
                                preview_tool_name = canvas_preview["tool"]
                                preview_key = str(canvas_preview.get("preview_key") or "").strip()
                                if announced_canvas_preview_key != preview_key:
                                    announced_canvas_preview_key = preview_key
                                    streamed_canvas_content_length = 0
                                    yield {
                                        "type": "canvas_tool_starting",
                                        "tool": preview_tool_name,
                                        "preview_key": preview_key,
                                        "snapshot": canvas_preview["snapshot"],
                                    }
                                preview_content = canvas_preview.get("content")
                                if preview_content is not None and len(preview_content) > streamed_canvas_content_length:
                                    next_content_delta = preview_content[streamed_canvas_content_length:]
                                    streamed_canvas_content_length = len(preview_content)
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
                        elif tool_call_parts:
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
                        provider_usage["completion_tokens"] += usage_snapshot["completion_tokens"]
                        provider_usage["total_tokens"] += usage_snapshot["total_tokens"]
                        provider_usage["received"] = provider_usage["received"] or usage_snapshot["received"]
                        provider_usage["cache_hit_present"] = provider_usage["cache_hit_present"] or usage_snapshot["cache_hit_present"]
                        provider_usage["cache_miss_present"] = provider_usage["cache_miss_present"] or usage_snapshot["cache_miss_present"]
                        provider_usage["cache_metrics_present"] = provider_usage["cache_metrics_present"] or usage_snapshot["cache_metrics_present"]
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
            finalize_call_usage()
            if buffered_content_deltas and not buffer_answer and not tool_calls and not tool_call_error:
                for pending_delta in buffered_content_deltas:
                    for event in emit_turn_answer(pending_delta):
                        yield event

            _trace_agent_event(
                "model_turn_completed",
                trace_id=trace_id,
                step=step,
                reasoning_excerpt=final_reasoning,
                content_excerpt=final_content,
                tool_calls=tool_calls or [],
                stream_error=stream_error,
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
        step += 1
        runtime_state["agent_context"]["conversation_handoff"] = _build_sub_agent_conversation_handoff(messages)
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

        try:
            turn_result = yield from stream_model_turn(
                turn_messages,
                buffer_answer=False,
                call_type="agent_step",
                retry_reason=step_retry_reason,
            )
        except Exception as exc:
            fatal_api_error = str(exc)
            if _is_context_overflow_error(fatal_api_error) and not context_compacted_this_step:
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
                fatal_api_error = CONTEXT_OVERFLOW_RECOVERY_ERROR_TEXT
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
            if content_text and _should_retry_for_skipped_clarification(
                messages,
                content_text,
                reasoning_text,
                normalized_prompt_tool_names,
            ):
                _trace_agent_event(
                    "clarification_tool_retry_requested",
                    trace_id=trace_id,
                    step=step,
                    content_excerpt=content_text,
                    reasoning_excerpt=reasoning_text,
                )
                messages.append(_build_clarification_retry_instruction())
                pending_step_retry_reason = "clarification_tool_retry"
                step -= 1
                continue
            if content_text:
                _trace_agent_event("final_answer_received", trace_id=trace_id, step=step, content_excerpt=content_text)
                if (
                    not answer_started
                    and "ask_clarifying_question" in set(normalized_prompt_tool_names)
                    and _has_clarification_retry_instruction(messages)
                    and _assistant_text_suggests_skipped_clarification(content_text, reasoning_text)
                    and not _has_missing_final_answer_instruction(messages)
                ):
                    _trace_agent_event(
                        "clarification_retry_failed_missing_answer",
                        trace_id=trace_id,
                        step=step,
                        content_excerpt=content_text,
                    )
                    messages.append(_build_missing_final_answer_instruction())
                    pending_step_retry_reason = "missing_final_answer"
                    step -= 1
                    continue
                if not answer_started:
                    for event in emit_answer(content_text):
                        yield event
                if stream_error:
                    yield {"type": "tool_error", "step": step, "tool": "api", "error": stream_error}
                if usage_totals["total_tokens"]:
                    yield usage_event()
                yield build_tool_capture_event()
                yield {"type": "done"}
                return

            if stream_error:
                if _is_context_overflow_error(stream_error) and not context_compacted_this_step:
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
                    fatal_api_error = CONTEXT_OVERFLOW_RECOVERY_ERROR_TEXT
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
                    str(tool_call.get("name") or "").strip()
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
        clarification_repair_error: str | None = None

        # ---- Phase 1: validate, pre-check, build execution slots (sequential) ----
        slots = []
        for call_index, tool_call in enumerate(tool_calls, start=1):
            tool_name = tool_call["name"]
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
                slot["error"] = f"Tool disabled: {tool_name}"
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
            )
            _append_working_state_attempt(working_state, tool_name, preview)
            slot["has_step_update"] = True

            tool_limit = _get_tool_step_limit(tool_name, max_steps)
            if tool_call_counts[tool_name] >= tool_limit:
                error = f"Per-tool step limit reached for {tool_name}. Try a different tool or produce the best available answer."
                _append_working_state_blocker(working_state, tool_name, error)
                slot["kind"] = "error"
                slot["error"] = error
                slots.append(slot)
                continue
            tool_call_counts[tool_name] += 1

            if tool_name not in CANVAS_TOOL_NAMES and cache_key in tool_result_cache:
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

        # ---- Phase 1b: yield step_update events for all non-error, non-disabled calls ----
        for slot in slots:
            if slot.get("has_step_update"):
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
            parallel_slots = [s for s in pending_slots if s["tool_name"] in PARALLEL_SAFE_TOOL_NAMES]
            sequential_slots = [s for s in pending_slots if s["tool_name"] not in PARALLEL_SAFE_TOOL_NAMES]
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
                        return {"ok": False, "error": str(exc)}

                with ThreadPoolExecutor(max_workers=min(normalized_parallel_tool_limit, len(parallel_slots))) as executor:
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
                        s["exec_result"] = {"ok": False, "error": str(exc)}

            for s in parallel_slots:
                buffered_events = s.get("exec_result", {}).get("events") if isinstance(s.get("exec_result"), dict) else []
                if isinstance(buffered_events, list):
                    for event in buffered_events:
                        if isinstance(event, dict):
                            yield event

            for s in sequential_slots:
                try:
                    if s["tool_name"] == "sub_agent":
                        res, summ = yield from _run_sub_agent_stream(s["tool_args"], runtime_state)
                    else:
                        res, summ = _execute_tool(s["tool_name"], s["tool_args"], runtime_state=runtime_state)
                    s["exec_result"] = {"ok": True, "result": res, "summary": summ}
                except Exception as exc:
                    s["exec_result"] = {"ok": False, "error": str(exc)}

        # ---- Phase 3: post-process all slots in original order ----
        for slot in slots:
            kind = slot["kind"]
            tool_name = slot["tool_name"]
            tool_args = slot["tool_args"]
            call_id = slot["call_id"]
            preview = slot["preview"]
            cache_key = slot["cache_key"]

            if kind == "error":
                error = slot["error"]
                if tool_name == "ask_clarifying_question" and clarification_repair_error is None:
                    clarification_repair_error = error
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
                    if tool_name not in CANVAS_TOOL_NAMES:
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
                                # search_tool_memory or grep_fetched_content.
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
                    )
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
                            "id": call_id,
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
                    clarification_event = _extract_clarification_event(result)
                    if clarification_event is not None:
                        _trace_agent_event(
                            "clarification_requested",
                            trace_id=trace_id,
                            step=step,
                            clarification=clarification_event.get("clarification"),
                        )
                        yield {
                            "type": "tool_history",
                            "step": step,
                            "messages": [assistant_tool_call_message, *tool_messages],
                        }
                        yield clarification_event
                        if usage_totals["total_tokens"]:
                            yield usage_event()
                        yield build_tool_capture_event()
                        yield {"type": "done"}
                        return
                else:
                    error = exec_result["error"]
                    if tool_name == "ask_clarifying_question" and clarification_repair_error is None:
                        clarification_repair_error = error
                    _append_working_state_blocker(working_state, tool_name, error)
                    _trace_agent_event(
                        "tool_call_failed",
                        trace_id=trace_id,
                        step=step,
                        tool_name=tool_name,
                        tool_args=tool_args,
                        error=error,
                    )
                    yield {"type": "tool_error", "step": step, "tool": tool_name, "error": error, "call_id": call_id}
                    tool_messages.append(
                        {
                            "id": call_id,
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

        tool_execution_result_message = _build_tool_execution_result_message(transcript_results)
        if tool_output_entries:
            tool_messages, transcript_results, tool_execution_result_message, tool_results_budget_compacted = _apply_tool_output_budget(
                messages,
                tool_output_entries,
                fetch_url_token_threshold=fetch_url_token_threshold,
                fetch_url_clip_aggressiveness=fetch_url_clip_aggressiveness,
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
        )
        yield {
            "type": "tool_history",
            "step": step,
            "messages": [assistant_tool_call_message, *tool_messages],
        }
        messages.extend(tool_messages)
        if tool_execution_result_message is not None:
            messages.append(tool_execution_result_message)
        if clarification_repair_error and not _has_clarification_tool_repair_instruction(messages):
            messages.append(_build_clarification_tool_repair_instruction(clarification_repair_error))
            _trace_agent_event(
                "clarification_tool_repair_requested",
                trace_id=trace_id,
                step=step,
                error=clarification_repair_error,
            )
            pending_step_retry_reason = "clarification_tool_repair"
            step -= 1
            continue

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
            turn_result = yield from stream_model_turn(
                final_messages,
                allow_tools=False,
                buffer_answer=False,
                call_type="final_answer",
                retry_reason=final_retry_reason,
            )
            content_text = turn_result.get("content_text") or ""
            tool_calls = turn_result.get("tool_calls")
            stream_error = turn_result.get("stream_error")
            answer_emitted = bool(turn_result.get("answer_emitted"))
            if stream_error and _is_context_overflow_error(stream_error) and not final_phase_compaction_used:
                _, compacted = apply_context_compaction(final_extra_messages, reason="reactive_final_stream", force=True)
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
                stream_error = CONTEXT_OVERFLOW_RECOVERY_ERROR_TEXT
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
            if stream_error:
                yield {"type": "tool_error", "step": step, "tool": "final_answer", "error": stream_error}
            if not answer_emitted:
                for event in emit_answer(final_text):
                    yield event
            break
        except Exception as exc:
            error = str(exc)
            if _is_context_overflow_error(error) and not final_phase_compaction_used:
                _, compacted = apply_context_compaction(final_extra_messages, reason="reactive_final_answer", force=True)
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
                error = CONTEXT_OVERFLOW_RECOVERY_ERROR_TEXT
            yield {"type": "tool_error", "step": step, "tool": "final_answer", "error": error}
            for event in emit_answer(FINAL_ANSWER_ERROR_TEXT):
                yield event
            break

    if usage_totals["total_tokens"]:
        yield usage_event()
    yield build_tool_capture_event()
    yield {"type": "done"}
