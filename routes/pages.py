from __future__ import annotations

import json
from pathlib import Path

from flask import jsonify, render_template, request

from config import (
    CHAT_SUMMARY_ALLOWED_MODES,
    CLARIFICATION_QUESTION_LIMIT_MAX,
    CLARIFICATION_QUESTION_LIMIT_MIN,
    CONTENT_MAX_CHARS,
    CONTEXT_SELECTION_ALLOWED_STRATEGIES,
    DEFAULT_WEB_CACHE_TTL_HOURS,
    DEFAULT_SETTINGS,
    ENTROPY_PROFILE_PRESETS,
    FETCH_HTML_CONVERTER_MODES,
    MAX_PARALLEL_TOOLS_MAX,
    MAX_PARALLEL_TOOLS_MIN,
    OCR_SUPPORTED_PROVIDERS,
    OPENROUTER_PROMPT_CACHE_DEFAULT_ENABLED,
    OPENROUTER_ANTHROPIC_CACHE_TTL_DEFAULT,
    RAG_CONTEXT_SIZE_PRESETS,
    RAG_ENABLED,
    RAG_SENSITIVITY_PRESETS,
    SEARCH_TOOL_QUERY_LIMIT_MAX,
    SEARCH_TOOL_QUERY_LIMIT_MIN,
    SCRATCHPAD_DEFAULT_SECTION,
    SCRATCHPAD_SECTION_METADATA,
    SCRATCHPAD_SECTION_ORDER,
    SCRATCHPAD_SECTION_SETTING_KEYS,
    SUB_AGENT_MAX_STEPS_MAX,
    SUB_AGENT_MAX_STEPS_MIN,
    WEB_CACHE_TTL_HOURS_MAX,
    WEB_CACHE_TTL_HOURS_MIN,
    get_feature_flags,
)
from routes.auth import is_login_pin_enabled
from db import (
    build_persona_preferences,
    build_effective_user_preferences,
    count_scratchpad_notes,
    get_active_tool_names,
    get_ai_personality,
    get_all_scratchpad_sections,
    get_app_settings,
    get_canvas_expand_max_lines,
    get_canvas_prompt_code_line_max_chars,
    get_canvas_prompt_max_chars,
    get_canvas_prompt_max_lines,
    get_canvas_prompt_max_tokens,
    get_canvas_prompt_text_line_max_chars,
    get_canvas_scroll_window_lines,
    get_chat_summary_model,
    get_chat_summary_mode,
    get_chat_summary_detail_level,
    get_chat_summary_trigger_token_count,
    get_clarification_max_questions,
    get_conversation_memory_enabled,
    get_context_compaction_keep_recent_rounds,
    get_context_compaction_threshold,
    get_context_selection_strategy,
    get_default_persona,
    get_default_persona_id,
    get_entropy_profile,
    get_entropy_protect_code_blocks_enabled,
    get_entropy_protect_tool_results_enabled,
    get_entropy_rag_budget_ratio,
    get_entropy_reference_boost_enabled,
    get_fetch_raw_max_text_chars,
    get_fetch_html_converter_mode,
    get_fetch_summary_max_chars,
    get_fetch_url_clip_aggressiveness,
    get_fetch_url_summarized_max_input_chars,
    get_fetch_url_summarized_max_output_tokens,
    get_fetch_url_token_threshold,
    get_login_lockout_seconds,
    get_login_max_failed_attempts,
    get_login_remember_session_days,
    get_login_session_timeout_minutes,
    get_max_parallel_tools,
    get_model_temperature,
    get_ocr_enabled,
    get_ocr_provider,
    get_openrouter_app_title,
    get_openrouter_http_referer,
    get_openrouter_prompt_cache_enabled,
    get_openrouter_anthropic_cache_ttl,
    get_prompt_max_input_tokens,
    get_prompt_preflight_summary_token_count,
    get_prompt_rag_max_tokens,
    get_prompt_recent_history_max_tokens,
    get_prompt_response_token_reserve,
    get_search_tool_query_limit,
    get_prompt_summary_max_tokens,
    get_prompt_tool_memory_max_tokens,
    get_prompt_tool_trace_max_tokens,
    get_proxy_enabled_operations,
    get_pruning_batch_size,
    get_pruning_enabled,
    get_pruning_min_target_tokens,
    get_pruning_target_reduction_ratio,
    get_pruning_token_threshold,
    get_reasoning_auto_collapse,
    get_rag_auto_inject_enabled,
    get_rag_auto_inject_source_types,
    get_rag_chunk_overlap,
    get_rag_chunk_size,
    get_rag_context_size,
    get_rag_enabled,
    get_rag_max_chunks_per_source,
    get_rag_query_expansion_enabled,
    get_rag_query_expansion_max_variants,
    get_rag_search_min_similarity,
    get_rag_search_top_k,
    get_rag_source_types,
    get_rag_sensitivity,
    get_sub_agent_allowed_tool_names,
    get_sub_agent_max_steps,
    get_sub_agent_max_parallel_tools,
    get_sub_agent_retry_attempts,
    get_sub_agent_retry_delay_seconds,
    get_sub_agent_timeout_seconds,
    get_summary_retry_min_source_tokens,
    get_summary_source_target_tokens,
    get_summary_skip_first,
    get_summary_skip_last,
    get_tool_memory_ttl_default_seconds,
    get_tool_memory_ttl_news_seconds,
    get_tool_memory_ttl_web_seconds,
    get_general_instructions,
    get_persona,
    get_tool_memory_auto_inject_enabled,
    get_web_cache_ttl_hours,
    get_youtube_transcript_language,
    get_youtube_transcript_model_size,
    get_youtube_transcripts_enabled,
    list_personas,
    normalize_active_tool_names,
    normalize_rag_source_types,
    normalize_sub_agent_allowed_tool_names,
    normalize_scratchpad_text,
    save_app_settings,
    upsert_default_persona,
)
from model_registry import (
    MODEL_OPERATION_KEYS,
    canonicalize_model_id,
    get_all_models,
    get_chat_capable_models,
    get_custom_model_contract,
    get_default_chat_model_id,
    get_image_helper_model_id,
    get_model_record,
    get_operation_model_fallback_preferences,
    get_operation_model_preferences,
    get_visible_chat_models,
    normalize_custom_model_definition,
    normalize_custom_models,
    normalize_image_processing_method,
    normalize_openrouter_provider_slug,
    normalize_operation_model_fallback_preferences,
    normalize_operation_model_preferences,
    normalize_visible_model_order,
)
from proxy_settings import (
    PROXY_OPERATION_FETCH_URL,
    PROXY_OPERATION_KEYS,
    PROXY_OPERATION_OPENROUTER,
    PROXY_OPERATION_SEARCH_NEWS_DDGS,
    PROXY_OPERATION_SEARCH_NEWS_GOOGLE,
    PROXY_OPERATION_SEARCH_WEB,
    normalize_proxy_enabled_operations,
)
from tool_registry import TOOL_SPEC_BY_NAME, get_tool_runtime_metadata

TOOL_PERMISSION_LABELS = {
    "save_to_conversation_memory": "Save chat memory",
    "delete_conversation_memory_entry": "Delete chat memory",
    "save_to_persona_memory": "Save persona memory",
    "delete_persona_memory_entry": "Delete persona memory",
    "append_scratchpad": "Append persistent scratchpad",
    "replace_scratchpad": "Rewrite persistent scratchpad section",
    "read_scratchpad": "Read persistent scratchpad",
    "ask_clarifying_question": "Ask interactive clarification questions",
    "sub_agent": "Web research helper",
    "image_explain": "Follow up on stored images",
    "transcribe_youtube_video": "Transcribe YouTube video",
    "search_knowledge_base": "Knowledge base search",
    "search_tool_memory": "Search remembered research",
    "search_web": "Web search",
    "fetch_url": "Read URL content",
    "fetch_url_summarized": "Summarize URL",
    "scroll_fetched_content": "Scroll fetched page content",
    "grep_fetched_content": "Search fetched page content",
    "search_news_ddgs": "News search — DDGS",
    "search_news_google": "News search — Google",
    "create_canvas_document": "Create canvas document",
    "expand_canvas_document": "Expand canvas document",
    "scroll_canvas_document": "Scroll canvas document",
    "search_canvas_document": "Search canvas document",
    "rewrite_canvas_document": "Rewrite canvas document",
    "preview_canvas_changes": "Preview canvas changes",
    "batch_canvas_edits": "Batch canvas edits",
    "batch_read_canvas_documents": "Read multiple canvas documents",
    "transform_canvas_lines": "Transform canvas lines",
    "update_canvas_metadata": "Update canvas metadata",
    "set_canvas_viewport": "Set canvas viewport",
    "focus_canvas_page": "Focus Canvas Page",
    "clear_canvas_viewport": "Clear canvas viewport",
    "replace_canvas_lines": "Replace canvas lines",
    "insert_canvas_lines": "Insert canvas lines",
    "delete_canvas_lines": "Delete canvas lines",
    "delete_canvas_document": "Delete canvas document",
    "clear_canvas": "Clear canvas",
    "create_directory": "Create directory",
    "create_file": "Create file",
    "update_file": "Update file",
    "read_file": "Read file",
    "list_dir": "List directory",
    "search_files": "Search files",
    "write_project_tree": "Write project tree",
    "validate_project_workspace": "Lightweight workspace validation",
    "validate_canvas_document": "Validate canvas document",
}

TOOL_PERMISSION_DESCRIPTIONS = {
    "save_to_conversation_memory": "Save a short chat-scoped memory entry for later turns in this conversation.",
    "delete_conversation_memory_entry": "Remove one outdated chat-scoped memory entry.",
    "save_to_persona_memory": "Save a short persona-scoped memory entry shared across conversations using that persona.",
    "delete_persona_memory_entry": "Remove one outdated persona-scoped memory entry.",
    "append_scratchpad": "Append durable facts to a named persistent memory section.",
    "replace_scratchpad": "Fully rewrite one persistent memory section.",
    "read_scratchpad": "Read the current persistent memory before editing.",
    "ask_clarifying_question": "Pause and ask the user structured questions before answering.",
    "sub_agent": "Delegate a bounded web research task to a read-only helper agent.",
    "image_explain": "Ask follow-up questions about a previously uploaded image.",
    "transcribe_youtube_video": "Validate a YouTube URL and generate a local speech transcript with a prompt-ready context block.",
    "search_knowledge_base": "Semantic search over synced chats and uploaded documents.",
    "search_tool_memory": "Search remembered web research results from earlier conversations.",
    "search_web": "Live web search via DuckDuckGo for current facts.",
    "fetch_url": "Read and extract cleaned text from a specific web page.",
    "fetch_url_summarized": "Fetch a page and return only a focused AI summary.",
    "scroll_fetched_content": "Read another window from a previously fetched page without importing it into Canvas.",
    "grep_fetched_content": "Search for a keyword or pattern inside a previously fetched page.",
    "search_news_ddgs": "Search recent news articles via DuckDuckGo News.",
    "search_news_google": "Search recent news articles via Google News RSS.",
    "create_canvas_document": "Create a new editable canvas document or code artifact.",
    "expand_canvas_document": "Load a full canvas document into view beyond the active excerpt.",
    "scroll_canvas_document": "Read a targeted line range from a canvas document.",
    "search_canvas_document": "Search for text or patterns inside canvas documents.",
    "rewrite_canvas_document": "Fully replace a canvas document's content in one operation.",
    "preview_canvas_changes": "Dry-run a set of canvas edits and preview the result without applying.",
    "batch_canvas_edits": "Apply several non-overlapping line edits to a canvas document in one call.",
    "batch_read_canvas_documents": "Read multiple canvas documents or ranges in one call.",
    "transform_canvas_lines": "Apply a text transformation to a range of lines in a canvas document.",
    "update_canvas_metadata": "Update the title, language, or other metadata of a canvas document.",
    "set_canvas_viewport": "Pin a line range as the active viewport for a canvas document.",
    "focus_canvas_page": "Pin a specific page from a page-aware canvas document so later prompts keep that page in view.",
    "clear_canvas_viewport": "Remove the pinned viewport so the full canvas is shown.",
    "replace_canvas_lines": "Replace a specific line range inside a canvas document.",
    "insert_canvas_lines": "Insert new lines at a position inside a canvas document.",
    "delete_canvas_lines": "Delete a specific line range from a canvas document.",
    "delete_canvas_document": "Permanently remove a canvas document from the conversation.",
    "clear_canvas": "Remove all canvas documents from the current conversation.",
    "create_directory": "Create a directory inside the conversation workspace sandbox.",
    "create_file": "Write a new file inside the conversation workspace sandbox.",
    "update_file": "Replace the full content of an existing workspace sandbox file.",
    "read_file": "Read the content of a workspace file with optional line limits.",
    "list_dir": "List files and folders in the workspace sandbox.",
    "search_files": "Search file paths or file contents within the workspace sandbox.",
    "write_project_tree": "Create or overwrite many files and directories in one batch.",
    "validate_project_workspace": "Run lightweight validation checks against the workspace sandbox.",
    "validate_canvas_document": "Run a syntax or structure check on a canvas document without editing it.",
}

TOOL_PERMISSION_SECTION_ORDER = ["assistant", "research", "canvas", "workspace"]
TOOL_PERMISSION_SECTION_METADATA = {
    "assistant": {
        "title": "Assistant & Memory",
        "description": "Memory, clarifications, and sub-agent behavior that stays closest to the chat loop.",
        "note": "These tools affect how the assistant reasons and remembers, not the filesystem sandbox.",
    },
    "research": {
        "title": "Web Research",
        "description": "Search and fetch public web content when the request calls for outside information.",
        "note": "When enabled, these tools stay available at runtime, but the prompt still tells the assistant to avoid unnecessary external lookups.",
    },
    "canvas": {
        "title": "Draft Files (Canvas)",
        "description": "Conversation-attached draft documents, canvas search, and line-level changes inside Canvas.",
        "note": "Enable inspection helpers such as expand and scroll separately when you want read-only canvas navigation.",
    },
    "workspace": {
        "title": "Real Files (Workspace)",
        "description": "Create, read, update, and validate real files inside the conversation workspace sandbox only.",
        "note": "This panel cannot expand the sandbox boundary. It only controls which sandbox operations the assistant may request.",
    },
}

PROXY_OPERATION_OPTIONS = [
    {
        "name": PROXY_OPERATION_OPENROUTER,
        "label": "OpenRouter model requests",
        "description": "Apply proxies.txt to chat, title generation, sub-agent, and other OpenRouter-backed model calls.",
    },
    {
        "name": PROXY_OPERATION_FETCH_URL,
        "label": "URL fetch tool",
        "description": "Use proxies.txt when fetch_url reads a page directly.",
    },
    {
        "name": PROXY_OPERATION_SEARCH_WEB,
        "label": "Web search",
        "description": "Use proxies.txt for DDGS web search requests.",
    },
    {
        "name": PROXY_OPERATION_SEARCH_NEWS_DDGS,
        "label": "News search (DDGS)",
        "description": "Use proxies.txt for DDGS news search requests.",
    },
    {
        "name": PROXY_OPERATION_SEARCH_NEWS_GOOGLE,
        "label": "News search (Google)",
        "description": "Use proxies.txt for Google News RSS fetches.",
    },
]


def _get_tool_permission_section_key(name: str) -> str:
    if name in {"save_to_conversation_memory", "delete_conversation_memory_entry", "save_to_persona_memory", "delete_persona_memory_entry", "append_scratchpad", "replace_scratchpad", "read_scratchpad", "ask_clarifying_question", "sub_agent", "image_explain", "transcribe_youtube_video", "search_knowledge_base", "search_tool_memory"}:
        return "assistant"
    if name in {"search_web", "fetch_url", "fetch_url_summarized", "scroll_fetched_content", "grep_fetched_content", "search_news_ddgs", "search_news_google"}:
        return "research"
    if name in {
        "create_canvas_document",
        "expand_canvas_document",
        "scroll_canvas_document",
        "search_canvas_document",
        "rewrite_canvas_document",
        "preview_canvas_changes",
        "batch_canvas_edits",
        "batch_read_canvas_documents",
        "transform_canvas_lines",
        "update_canvas_metadata",
        "set_canvas_viewport",
        "focus_canvas_page",
        "clear_canvas_viewport",
        "replace_canvas_lines",
        "insert_canvas_lines",
        "delete_canvas_lines",
        "delete_canvas_document",
        "clear_canvas",
        "validate_canvas_document",
    }:
        return "canvas"
    return "workspace"


def build_tool_permission_options() -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    for name in TOOL_SPEC_BY_NAME:
        options.append(
            {
                "name": name,
                "label": TOOL_PERMISSION_LABELS.get(name, name.replace("_", " ").title()),
                "description": TOOL_PERMISSION_DESCRIPTIONS.get(name, ""),
            }
        )
    return options


def build_tool_permission_sections() -> list[dict[str, object]]:
    grouped_tools: dict[str, list[dict[str, str]]] = {key: [] for key in TOOL_PERMISSION_SECTION_ORDER}
    for tool in build_tool_permission_options():
        section_key = _get_tool_permission_section_key(tool["name"])
        grouped_tools.setdefault(section_key, []).append(tool)

    sections: list[dict[str, object]] = []
    for section_key in TOOL_PERMISSION_SECTION_ORDER:
        tools = grouped_tools.get(section_key) or []
        if not tools:
            continue
        metadata = TOOL_PERMISSION_SECTION_METADATA[section_key]
        sections.append(
            {
                "key": section_key,
                "title": metadata["title"],
                "description": metadata["description"],
                "note": metadata["note"],
                "tools": tools,
            }
        )
    return sections


def build_sub_agent_web_tool_sections() -> list[dict[str, object]]:
    allowed_tools = {
        tool_name
        for tool_name in TOOL_SPEC_BY_NAME
        if tool_name != "sub_agent" and get_tool_runtime_metadata(tool_name).get("read_only") is True
    }
    sections: list[dict[str, object]] = []
    for section in build_tool_permission_sections():
        filtered_tools = [tool for tool in section["tools"] if tool["name"] in allowed_tools]
        if not filtered_tools:
            continue
        sections.append({**section, "tools": filtered_tools})
    return sections


def _normalize_bool_setting_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return "true" if str(value or "").strip().lower() in {"1", "true", "yes", "on"} else "false"


def _normalize_custom_model_client_uid(
    value,
    *,
    existing_custom_model_ids: set[str] | None = None,
) -> str:
    raw_value = str(value or "").strip()
    if not raw_value or len(raw_value) > 200:
        return ""

    client_uid_prefix = str(get_custom_model_contract().get("client_uid_prefix") or "").strip()
    if client_uid_prefix and raw_value.startswith(client_uid_prefix):
        return raw_value
    if raw_value in (existing_custom_model_ids or set()):
        return raw_value
    return ""


def _resolve_model_reference_id(value, custom_model_reference_ids: dict[str, str] | None = None) -> str:
    raw_value = str(value or "").strip()
    if not raw_value:
        return ""
    if isinstance(custom_model_reference_ids, dict):
        mapped_value = custom_model_reference_ids.get(raw_value)
        if mapped_value:
            return mapped_value
    return canonicalize_model_id(raw_value)


def build_settings_payload() -> dict:
    raw = get_app_settings()
    available_models = get_all_models(raw)
    visible_chat_models = get_visible_chat_models(raw)
    default_persona = get_default_persona(raw)
    general_instructions = (
        default_persona.get("general_instructions", "")
        if isinstance(default_persona, dict)
        else get_general_instructions(raw)
    )
    ai_personality = (
        default_persona.get("ai_personality", "")
        if isinstance(default_persona, dict)
        else get_ai_personality(raw)
    )
    configured_active_tools = normalize_active_tool_names(raw.get("active_tools"))
    if raw.get("active_tools") is None:
        configured_active_tools = get_active_tool_names(raw)
    return {
        "user_preferences": general_instructions,
        "general_instructions": general_instructions,
        "ai_personality": ai_personality,
        "effective_user_preferences": (
            build_persona_preferences(default_persona)
            if isinstance(default_persona, dict)
            else build_effective_user_preferences(raw)
        ),
        "default_persona_id": get_default_persona_id(raw),
        "personas": list_personas(),
        "scratchpad": raw.get("scratchpad", ""),
        "scratchpad_sections": build_scratchpad_sections_payload(raw),
        "max_steps": int(raw.get("max_steps", DEFAULT_SETTINGS["max_steps"])),
        "max_parallel_tools": get_max_parallel_tools(raw),
        "temperature": get_model_temperature(raw),
        "clarification_max_questions": get_clarification_max_questions(raw),
        "search_tool_query_limit": get_search_tool_query_limit(raw),
        "available_models": available_models,
        "custom_model_contract": get_custom_model_contract(),
        "custom_models": normalize_custom_models(raw.get("custom_models")),
        "visible_model_order": [model["id"] for model in visible_chat_models],
        "default_chat_model": get_default_chat_model_id(raw),
        "operation_model_preferences": get_operation_model_preferences(raw),
        "operation_model_fallback_preferences": get_operation_model_fallback_preferences(raw),
        "image_processing_method": normalize_image_processing_method(raw.get("image_processing_method")),
        "image_helper_model": get_image_helper_model_id(raw),
        "active_tools": configured_active_tools,
        "proxy_enabled_operations": get_proxy_enabled_operations(raw),
        "rag_auto_inject": get_rag_auto_inject_enabled(raw),
        "rag_sensitivity": get_rag_sensitivity(raw),
        "rag_context_size": get_rag_context_size(raw),
        "rag_source_types": get_rag_source_types(raw),
        "rag_auto_inject_source_types": get_rag_auto_inject_source_types(raw),
        "tool_memory_auto_inject": get_tool_memory_auto_inject_enabled(raw),
        "canvas_prompt_max_lines": get_canvas_prompt_max_lines(raw),
        "canvas_prompt_max_tokens": get_canvas_prompt_max_tokens(raw),
        "canvas_prompt_max_chars": get_canvas_prompt_max_chars(raw),
        "canvas_prompt_code_line_max_chars": get_canvas_prompt_code_line_max_chars(raw),
        "canvas_prompt_text_line_max_chars": get_canvas_prompt_text_line_max_chars(raw),
        "canvas_expand_max_lines": get_canvas_expand_max_lines(raw),
        "canvas_scroll_window_lines": get_canvas_scroll_window_lines(raw),
        "sub_agent_max_steps": get_sub_agent_max_steps(raw),
        "sub_agent_timeout_seconds": get_sub_agent_timeout_seconds(raw),
        "sub_agent_retry_attempts": get_sub_agent_retry_attempts(raw),
        "sub_agent_retry_delay_seconds": get_sub_agent_retry_delay_seconds(raw),
        "sub_agent_max_parallel_tools": get_sub_agent_max_parallel_tools(raw),
        "sub_agent_allowed_tool_names": get_sub_agent_allowed_tool_names(raw),
        "web_cache_ttl_hours": get_web_cache_ttl_hours(raw),
        "openrouter_prompt_cache_enabled": get_openrouter_prompt_cache_enabled(raw),
        "openrouter_anthropic_cache_ttl": get_openrouter_anthropic_cache_ttl(raw),
        "openrouter_http_referer": get_openrouter_http_referer(raw),
        "openrouter_app_title": get_openrouter_app_title(raw),
        "login_session_timeout_minutes": get_login_session_timeout_minutes(raw),
        "login_max_failed_attempts": get_login_max_failed_attempts(raw),
        "login_lockout_seconds": get_login_lockout_seconds(raw),
        "login_remember_session_days": get_login_remember_session_days(raw),
        "conversation_memory_enabled": get_conversation_memory_enabled(raw),
        "ocr_enabled": get_ocr_enabled(raw),
        "ocr_provider": get_ocr_provider(raw),
        "rag_enabled": get_rag_enabled(raw),
        "youtube_transcripts_enabled": get_youtube_transcripts_enabled(raw),
        "youtube_transcript_language": get_youtube_transcript_language(raw),
        "youtube_transcript_model_size": get_youtube_transcript_model_size(raw),
        "chat_summary_model": get_chat_summary_model(raw),
        "rag_chunk_size": get_rag_chunk_size(raw),
        "rag_chunk_overlap": get_rag_chunk_overlap(raw),
        "rag_max_chunks_per_source": get_rag_max_chunks_per_source(raw),
        "rag_search_top_k": get_rag_search_top_k(raw),
        "rag_search_min_similarity": get_rag_search_min_similarity(raw),
        "rag_query_expansion_enabled": get_rag_query_expansion_enabled(raw),
        "rag_query_expansion_max_variants": get_rag_query_expansion_max_variants(raw),
        "tool_memory_ttl_default_seconds": get_tool_memory_ttl_default_seconds(raw),
        "tool_memory_ttl_web_seconds": get_tool_memory_ttl_web_seconds(raw),
        "tool_memory_ttl_news_seconds": get_tool_memory_ttl_news_seconds(raw),
        "fetch_raw_max_text_chars": get_fetch_raw_max_text_chars(raw),
        "fetch_summary_max_chars": get_fetch_summary_max_chars(raw),
        "chat_summary_detail_level": get_chat_summary_detail_level(raw),
        "chat_summary_mode": get_chat_summary_mode(raw),
        "chat_summary_trigger_token_count": get_chat_summary_trigger_token_count(raw),
        "summary_skip_first": get_summary_skip_first(raw),
        "summary_skip_last": get_summary_skip_last(raw),
        "prompt_max_input_tokens": get_prompt_max_input_tokens(raw),
        "prompt_response_token_reserve": get_prompt_response_token_reserve(raw),
        "prompt_recent_history_max_tokens": get_prompt_recent_history_max_tokens(raw),
        "prompt_summary_max_tokens": get_prompt_summary_max_tokens(raw),
        "prompt_preflight_summary_token_count": get_prompt_preflight_summary_token_count(raw),
        "prompt_rag_max_tokens": get_prompt_rag_max_tokens(raw),
        "prompt_tool_memory_max_tokens": get_prompt_tool_memory_max_tokens(raw),
        "prompt_tool_trace_max_tokens": get_prompt_tool_trace_max_tokens(raw),
        "summary_source_target_tokens": get_summary_source_target_tokens(raw),
        "summary_retry_min_source_tokens": get_summary_retry_min_source_tokens(raw),
        "context_compaction_threshold": get_context_compaction_threshold(raw),
        "context_compaction_keep_recent_rounds": get_context_compaction_keep_recent_rounds(raw),
        "context_selection_strategy": get_context_selection_strategy(raw),
        "entropy_profile": get_entropy_profile(raw),
        "entropy_rag_budget_ratio": get_entropy_rag_budget_ratio(raw),
        "entropy_protect_code_blocks": get_entropy_protect_code_blocks_enabled(raw),
        "entropy_protect_tool_results": get_entropy_protect_tool_results_enabled(raw),
        "entropy_reference_boost": get_entropy_reference_boost_enabled(raw),
        "reasoning_auto_collapse": get_reasoning_auto_collapse(raw),
        "pruning_enabled": get_pruning_enabled(raw),
        "pruning_token_threshold": get_pruning_token_threshold(raw),
        "pruning_batch_size": get_pruning_batch_size(raw),
        "pruning_target_reduction_ratio": get_pruning_target_reduction_ratio(raw),
        "pruning_min_target_tokens": get_pruning_min_target_tokens(raw),
        "fetch_url_token_threshold": get_fetch_url_token_threshold(raw),
        "fetch_url_clip_aggressiveness": get_fetch_url_clip_aggressiveness(raw),
        "fetch_html_converter_mode": get_fetch_html_converter_mode(raw),
        "fetch_url_summarized_max_input_chars": get_fetch_url_summarized_max_input_chars(raw),
        "fetch_url_summarized_max_output_tokens": get_fetch_url_summarized_max_output_tokens(raw),
        "features": get_feature_flags(raw),
    }


def build_scratchpad_sections_payload(settings: dict) -> dict:
    scratchpad_sections = get_all_scratchpad_sections(settings)
    return {
        section_id: {
            "id": section_id,
            "title": SCRATCHPAD_SECTION_METADATA[section_id]["title"],
            "description": SCRATCHPAD_SECTION_METADATA[section_id]["description"],
            "content": scratchpad_sections.get(section_id, ""),
            "note_count": count_scratchpad_notes(scratchpad_sections.get(section_id, "")),
        }
        for section_id in SCRATCHPAD_SECTION_ORDER
    }


def _static_asset_version(app, filename: str) -> str:
    static_folder = getattr(app, "static_folder", None)
    if not static_folder:
        return "1"
    asset_path = Path(static_folder) / filename
    try:
        return str(int(asset_path.stat().st_mtime))
    except OSError:
        return "1"


def _resolve_page_lang() -> str:
    return request.accept_languages.best_match(["tr", "en"]) or "en"


def register_page_routes(app) -> None:
    @app.route("/")
    def index():
        settings = build_settings_payload()
        return render_template(
            "index.html",
            models=get_visible_chat_models(get_app_settings()),
            settings=settings,
            auth_enabled=is_login_pin_enabled(),
            page_lang=_resolve_page_lang(),
            app_js_version=_static_asset_version(app, "app.js"),
        )

    @app.route("/settings")
    def settings_page():
        settings = build_settings_payload()
        return render_template(
            "settings.html",
            settings=settings,
            tool_sections=build_tool_permission_sections(),
            sub_agent_tool_sections=build_sub_agent_web_tool_sections(),
            proxy_operation_options=PROXY_OPERATION_OPTIONS,
            auth_enabled=is_login_pin_enabled(),
            page_lang=_resolve_page_lang(),
            settings_js_version=_static_asset_version(app, "settings.js"),
        )

    @app.route("/api/settings", methods=["GET"])
    def get_settings():
        return jsonify(build_settings_payload())

    @app.route("/api/settings", methods=["PATCH"])
    def update_settings():
        data = request.get_json(silent=True) or {}
        user_preferences = data.get("user_preferences")
        general_instructions = data.get("general_instructions")
        ai_personality = data.get("ai_personality")
        default_persona_id_raw = data.get("default_persona_id")
        max_steps_raw = data.get("max_steps")
        max_parallel_tools_raw = data.get("max_parallel_tools")
        temperature_raw = data.get("temperature")
        clarification_max_questions_raw = data.get("clarification_max_questions")
        search_tool_query_limit_raw = data.get("search_tool_query_limit")
        custom_models_raw = data.get("custom_models")
        visible_model_order_raw = data.get("visible_model_order")
        operation_model_preferences_raw = data.get("operation_model_preferences")
        operation_model_fallback_preferences_raw = data.get("operation_model_fallback_preferences")
        image_processing_method_raw = data.get("image_processing_method")
        image_helper_model_raw = data.get("image_helper_model")
        active_tools_raw = data.get("active_tools")
        proxy_enabled_operations_raw = data.get("proxy_enabled_operations")
        rag_auto_inject = data.get("rag_auto_inject")
        rag_sensitivity = data.get("rag_sensitivity")
        rag_context_size = data.get("rag_context_size")
        rag_source_types = data.get("rag_source_types")
        rag_auto_inject_source_types = data.get("rag_auto_inject_source_types")
        tool_memory_auto_inject = data.get("tool_memory_auto_inject")
        chat_summary_mode_raw = data.get("chat_summary_mode")
        chat_summary_detail_level_raw = data.get("chat_summary_detail_level")
        chat_summary_trigger_raw = data.get("chat_summary_trigger_token_count")
        summary_skip_first_raw = data.get("summary_skip_first")
        summary_skip_last_raw = data.get("summary_skip_last")
        context_selection_strategy_raw = data.get("context_selection_strategy")
        entropy_profile_raw = data.get("entropy_profile")
        entropy_rag_budget_ratio_raw = data.get("entropy_rag_budget_ratio")
        entropy_protect_code_blocks_raw = data.get("entropy_protect_code_blocks")
        entropy_protect_tool_results_raw = data.get("entropy_protect_tool_results")
        entropy_reference_boost_raw = data.get("entropy_reference_boost")
        prompt_max_input_tokens_raw = data.get("prompt_max_input_tokens")
        prompt_response_token_reserve_raw = data.get("prompt_response_token_reserve")
        prompt_recent_history_max_tokens_raw = data.get("prompt_recent_history_max_tokens")
        prompt_summary_max_tokens_raw = data.get("prompt_summary_max_tokens")
        prompt_preflight_summary_token_count_raw = data.get("prompt_preflight_summary_token_count")
        prompt_rag_max_tokens_raw = data.get("prompt_rag_max_tokens")
        prompt_tool_memory_max_tokens_raw = data.get("prompt_tool_memory_max_tokens")
        prompt_tool_trace_max_tokens_raw = data.get("prompt_tool_trace_max_tokens")
        summary_source_target_tokens_raw = data.get("summary_source_target_tokens")
        summary_retry_min_source_tokens_raw = data.get("summary_retry_min_source_tokens")
        context_compaction_threshold_raw = data.get("context_compaction_threshold")
        context_compaction_keep_recent_rounds_raw = data.get("context_compaction_keep_recent_rounds")
        reasoning_auto_collapse_raw = data.get("reasoning_auto_collapse")
        pruning_enabled_raw = data.get("pruning_enabled")
        pruning_token_threshold_raw = data.get("pruning_token_threshold")
        pruning_batch_size_raw = data.get("pruning_batch_size")
        pruning_target_reduction_ratio_raw = data.get("pruning_target_reduction_ratio")
        pruning_min_target_tokens_raw = data.get("pruning_min_target_tokens")
        fetch_url_token_threshold_raw = data.get("fetch_url_token_threshold")
        fetch_url_clip_aggressiveness_raw = data.get("fetch_url_clip_aggressiveness")
        fetch_html_converter_mode_raw = data.get("fetch_html_converter_mode")
        fetch_url_summarized_max_input_chars_raw = data.get("fetch_url_summarized_max_input_chars")
        fetch_url_summarized_max_output_tokens_raw = data.get("fetch_url_summarized_max_output_tokens")
        canvas_prompt_max_lines_raw = data.get("canvas_prompt_max_lines")
        canvas_prompt_max_tokens_raw = data.get("canvas_prompt_max_tokens")
        canvas_prompt_max_chars_raw = data.get("canvas_prompt_max_chars")
        canvas_prompt_code_line_max_chars_raw = data.get("canvas_prompt_code_line_max_chars")
        canvas_prompt_text_line_max_chars_raw = data.get("canvas_prompt_text_line_max_chars")
        canvas_expand_max_lines_raw = data.get("canvas_expand_max_lines")
        canvas_scroll_window_lines_raw = data.get("canvas_scroll_window_lines")
        sub_agent_max_steps_raw = data.get("sub_agent_max_steps")
        sub_agent_timeout_seconds_raw = data.get("sub_agent_timeout_seconds")
        sub_agent_retry_attempts_raw = data.get("sub_agent_retry_attempts")
        sub_agent_retry_delay_seconds_raw = data.get("sub_agent_retry_delay_seconds")
        sub_agent_max_parallel_tools_raw = data.get("sub_agent_max_parallel_tools")
        sub_agent_allowed_tool_names_raw = data.get("sub_agent_allowed_tool_names")
        web_cache_ttl_hours_raw = data.get("web_cache_ttl_hours")
        openrouter_prompt_cache_enabled_raw = data.get("openrouter_prompt_cache_enabled")
        openrouter_anthropic_cache_ttl_raw = data.get("openrouter_anthropic_cache_ttl")
        openrouter_http_referer_raw = data.get("openrouter_http_referer")
        openrouter_app_title_raw = data.get("openrouter_app_title")
        login_session_timeout_minutes_raw = data.get("login_session_timeout_minutes")
        login_max_failed_attempts_raw = data.get("login_max_failed_attempts")
        login_lockout_seconds_raw = data.get("login_lockout_seconds")
        login_remember_session_days_raw = data.get("login_remember_session_days")
        conversation_memory_enabled_raw = data.get("conversation_memory_enabled")
        ocr_enabled_raw = data.get("ocr_enabled")
        ocr_provider_raw = data.get("ocr_provider")
        rag_enabled_raw = data.get("rag_enabled")
        youtube_transcripts_enabled_raw = data.get("youtube_transcripts_enabled")
        youtube_transcript_language_raw = data.get("youtube_transcript_language")
        youtube_transcript_model_size_raw = data.get("youtube_transcript_model_size")
        chat_summary_model_raw = data.get("chat_summary_model")
        rag_chunk_size_raw = data.get("rag_chunk_size")
        rag_chunk_overlap_raw = data.get("rag_chunk_overlap")
        rag_max_chunks_per_source_raw = data.get("rag_max_chunks_per_source")
        rag_search_top_k_raw = data.get("rag_search_top_k")
        rag_search_min_similarity_raw = data.get("rag_search_min_similarity")
        rag_query_expansion_enabled_raw = data.get("rag_query_expansion_enabled")
        rag_query_expansion_max_variants_raw = data.get("rag_query_expansion_max_variants")
        tool_memory_ttl_default_seconds_raw = data.get("tool_memory_ttl_default_seconds")
        tool_memory_ttl_web_seconds_raw = data.get("tool_memory_ttl_web_seconds")
        tool_memory_ttl_news_seconds_raw = data.get("tool_memory_ttl_news_seconds")
        fetch_raw_max_text_chars_raw = data.get("fetch_raw_max_text_chars")
        fetch_summary_max_chars_raw = data.get("fetch_summary_max_chars")
        scratchpad = data.get("scratchpad")
        scratchpad_sections_raw = data.get("scratchpad_sections")

        if (
            user_preferences is None
            and general_instructions is None
            and ai_personality is None
            and default_persona_id_raw is None
            and scratchpad is None
            and scratchpad_sections_raw is None
            and max_steps_raw is None
            and max_parallel_tools_raw is None
            and temperature_raw is None
            and clarification_max_questions_raw is None
            and search_tool_query_limit_raw is None
            and custom_models_raw is None
            and visible_model_order_raw is None
            and operation_model_preferences_raw is None
            and operation_model_fallback_preferences_raw is None
            and image_processing_method_raw is None
            and active_tools_raw is None
            and proxy_enabled_operations_raw is None
            and rag_auto_inject is None
            and rag_sensitivity is None
            and rag_context_size is None
            and rag_source_types is None
            and rag_auto_inject_source_types is None
            and tool_memory_auto_inject is None
            and chat_summary_mode_raw is None
            and chat_summary_detail_level_raw is None
            and chat_summary_trigger_raw is None
            and summary_skip_first_raw is None
            and summary_skip_last_raw is None
            and prompt_max_input_tokens_raw is None
            and prompt_response_token_reserve_raw is None
            and prompt_recent_history_max_tokens_raw is None
            and prompt_summary_max_tokens_raw is None
            and prompt_preflight_summary_token_count_raw is None
            and prompt_rag_max_tokens_raw is None
            and prompt_tool_memory_max_tokens_raw is None
            and prompt_tool_trace_max_tokens_raw is None
            and summary_source_target_tokens_raw is None
            and summary_retry_min_source_tokens_raw is None
            and context_compaction_threshold_raw is None
            and context_compaction_keep_recent_rounds_raw is None
            and context_selection_strategy_raw is None
            and entropy_profile_raw is None
            and entropy_rag_budget_ratio_raw is None
            and entropy_protect_code_blocks_raw is None
            and entropy_protect_tool_results_raw is None
            and entropy_reference_boost_raw is None
            and reasoning_auto_collapse_raw is None
            and pruning_enabled_raw is None
            and pruning_token_threshold_raw is None
            and pruning_batch_size_raw is None
            and pruning_target_reduction_ratio_raw is None
            and pruning_min_target_tokens_raw is None
            and fetch_url_token_threshold_raw is None
            and fetch_url_clip_aggressiveness_raw is None
            and fetch_html_converter_mode_raw is None
            and fetch_url_summarized_max_input_chars_raw is None
            and fetch_url_summarized_max_output_tokens_raw is None
            and canvas_prompt_max_lines_raw is None
            and canvas_prompt_max_tokens_raw is None
            and canvas_prompt_max_chars_raw is None
            and canvas_prompt_code_line_max_chars_raw is None
            and canvas_prompt_text_line_max_chars_raw is None
            and canvas_expand_max_lines_raw is None
            and canvas_scroll_window_lines_raw is None
            and sub_agent_max_steps_raw is None
            and sub_agent_timeout_seconds_raw is None
            and sub_agent_retry_attempts_raw is None
            and sub_agent_retry_delay_seconds_raw is None
            and sub_agent_max_parallel_tools_raw is None
            and sub_agent_allowed_tool_names_raw is None
            and web_cache_ttl_hours_raw is None
            and openrouter_prompt_cache_enabled_raw is None
            and openrouter_anthropic_cache_ttl_raw is None
            and openrouter_http_referer_raw is None
            and openrouter_app_title_raw is None
            and login_session_timeout_minutes_raw is None
            and login_max_failed_attempts_raw is None
            and login_lockout_seconds_raw is None
            and login_remember_session_days_raw is None
            and conversation_memory_enabled_raw is None
            and ocr_enabled_raw is None
            and ocr_provider_raw is None
            and rag_enabled_raw is None
            and youtube_transcripts_enabled_raw is None
            and youtube_transcript_language_raw is None
            and youtube_transcript_model_size_raw is None
            and chat_summary_model_raw is None
            and rag_chunk_size_raw is None
            and rag_chunk_overlap_raw is None
            and rag_max_chunks_per_source_raw is None
            and rag_search_top_k_raw is None
            and rag_search_min_similarity_raw is None
            and rag_query_expansion_enabled_raw is None
            and rag_query_expansion_max_variants_raw is None
            and tool_memory_ttl_default_seconds_raw is None
            and tool_memory_ttl_web_seconds_raw is None
            and tool_memory_ttl_news_seconds_raw is None
            and fetch_raw_max_text_chars_raw is None
            and fetch_summary_max_chars_raw is None
        ):
            return jsonify({"error": "No settings provided."}), 400

        settings = get_app_settings()
        default_persona = get_default_persona(settings)
        existing_custom_model_ids = {
            str(model.get("id") or "").strip()
            for model in normalize_custom_models(settings.get("custom_models"))
            if str(model.get("id") or "").strip()
        }
        custom_model_reference_ids: dict[str, str] = {}

        if general_instructions is None and user_preferences is not None:
            general_instructions = user_preferences

        if general_instructions is not None and not isinstance(general_instructions, str):
            return jsonify({"error": "Invalid general instructions."}), 400

        if ai_personality is not None and not isinstance(ai_personality, str):
            return jsonify({"error": "Invalid AI personality."}), 400

        if general_instructions is not None or ai_personality is not None:
            normalized_general_instructions = (
                (general_instructions or "").strip()
                if general_instructions is not None
                else (
                    str(default_persona.get("general_instructions") or "")
                    if isinstance(default_persona, dict)
                    else get_general_instructions(settings)
                )
            )
            normalized_ai_personality = (
                (ai_personality or "").strip()
                if ai_personality is not None
                else (
                    str(default_persona.get("ai_personality") or "")
                    if isinstance(default_persona, dict)
                    else get_ai_personality(settings)
                )
            )

            if normalized_general_instructions or normalized_ai_personality or isinstance(default_persona, dict):
                persona = upsert_default_persona(
                    normalized_general_instructions,
                    normalized_ai_personality,
                )
                settings["default_persona_id"] = str(persona["id"])

            settings["general_instructions"] = ""
            settings["user_preferences"] = ""
            settings["ai_personality"] = ""

        if default_persona_id_raw is not None:
            if default_persona_id_raw in (None, ""):
                settings["default_persona_id"] = ""
            else:
                try:
                    default_persona_id = int(default_persona_id_raw)
                except (TypeError, ValueError):
                    return jsonify({"error": "default_persona_id must be an integer or empty."}), 400
                if default_persona_id <= 0:
                    return jsonify({"error": "default_persona_id must be a positive integer."}), 400
                if get_persona(default_persona_id) is None:
                    return jsonify({"error": "default_persona_id must reference an existing persona."}), 400
                settings["default_persona_id"] = str(default_persona_id)

        if scratchpad is not None:
            if not isinstance(scratchpad, str):
                return jsonify({"error": "Invalid scratchpad."}), 400
            settings[SCRATCHPAD_SECTION_SETTING_KEYS[SCRATCHPAD_DEFAULT_SECTION]] = normalize_scratchpad_text(scratchpad)

        if scratchpad_sections_raw is not None:
            if not isinstance(scratchpad_sections_raw, dict):
                return jsonify({"error": "Invalid scratchpad sections."}), 400
            unexpected_sections = [
                section_id
                for section_id in scratchpad_sections_raw
                if section_id not in SCRATCHPAD_SECTION_SETTING_KEYS
            ]
            if unexpected_sections:
                return jsonify({"error": f"Unknown scratchpad sections: {', '.join(sorted(unexpected_sections))}."}), 400
            for section_id, content in scratchpad_sections_raw.items():
                if not isinstance(content, str):
                    return jsonify({"error": f"Invalid scratchpad section content for {section_id}."}), 400
                settings[SCRATCHPAD_SECTION_SETTING_KEYS[section_id]] = normalize_scratchpad_text(content)

        if max_steps_raw is not None:
            try:
                max_steps = int(max_steps_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "max_steps must be an integer."}), 400
            if not (1 <= max_steps <= 50):
                return jsonify({"error": "max_steps must be between 1 and 50."}), 400
            settings["max_steps"] = str(max_steps)

        if max_parallel_tools_raw is not None:
            try:
                max_parallel_tools = int(max_parallel_tools_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "max_parallel_tools must be an integer."}), 400
            if not (MAX_PARALLEL_TOOLS_MIN <= max_parallel_tools <= MAX_PARALLEL_TOOLS_MAX):
                return jsonify({"error": f"max_parallel_tools must be between {MAX_PARALLEL_TOOLS_MIN} and {MAX_PARALLEL_TOOLS_MAX}."}), 400
            settings["max_parallel_tools"] = str(max_parallel_tools)

        if temperature_raw is not None:
            try:
                temperature = float(temperature_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "temperature must be a number."}), 400
            if not (0.0 <= temperature <= 2.0):
                return jsonify({"error": "temperature must be between 0 and 2."}), 400
            settings["temperature"] = str(temperature)

        if clarification_max_questions_raw is not None:
            try:
                clarification_max_questions = int(clarification_max_questions_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "clarification_max_questions must be an integer."}), 400
            if not (CLARIFICATION_QUESTION_LIMIT_MIN <= clarification_max_questions <= CLARIFICATION_QUESTION_LIMIT_MAX):
                return jsonify({"error": f"clarification_max_questions must be between {CLARIFICATION_QUESTION_LIMIT_MIN} and {CLARIFICATION_QUESTION_LIMIT_MAX}."}), 400
            settings["clarification_max_questions"] = str(clarification_max_questions)

        if search_tool_query_limit_raw is not None:
            try:
                search_tool_query_limit = int(search_tool_query_limit_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "search_tool_query_limit must be an integer."}), 400
            if not (SEARCH_TOOL_QUERY_LIMIT_MIN <= search_tool_query_limit <= SEARCH_TOOL_QUERY_LIMIT_MAX):
                return jsonify({"error": f"search_tool_query_limit must be between {SEARCH_TOOL_QUERY_LIMIT_MIN} and {SEARCH_TOOL_QUERY_LIMIT_MAX}."}), 400
            settings["search_tool_query_limit"] = str(search_tool_query_limit)

        if custom_models_raw is not None:
            if not isinstance(custom_models_raw, list):
                return jsonify({"error": "custom_models must be an array."}), 400

            normalized_custom_models = []
            seen_custom_model_ids: set[str] = set()
            seen_custom_model_client_uids: set[str] = set()
            for entry in custom_models_raw:
                if not isinstance(entry, dict):
                    return jsonify({"error": "Each custom model must be an object."}), 400

                raw_provider_slug = entry.get("provider_slug")
                if raw_provider_slug is None:
                    raw_provider_slug = entry.get("openrouter_provider")
                if str(raw_provider_slug or "").strip() and not normalize_openrouter_provider_slug(raw_provider_slug):
                    return jsonify(
                        {
                            "error": (
                                "custom_models contains an invalid provider_slug. "
                                "Use an OpenRouter provider slug such as anthropic or deepinfra/turbo."
                            )
                        }
                    ), 400

                definition = normalize_custom_model_definition(entry)
                if not definition:
                    return jsonify({"error": "Each custom model must include a valid OpenRouter model id."}), 400
                if definition["id"] in seen_custom_model_ids:
                    return jsonify({"error": "custom_models contains duplicate model ids."}), 400

                client_uid = _normalize_custom_model_client_uid(
                    entry.get("client_uid"),
                    existing_custom_model_ids=existing_custom_model_ids,
                )
                if str(entry.get("client_uid") or "").strip() and not client_uid:
                    return jsonify({"error": "custom_models contains an invalid client_uid."}), 400
                if client_uid:
                    if client_uid in seen_custom_model_client_uids:
                        return jsonify({"error": "custom_models contains duplicate client_uids."}), 400
                    existing_mapping = custom_model_reference_ids.get(client_uid)
                    if existing_mapping and existing_mapping != definition["id"]:
                        return jsonify({"error": "custom_models contains conflicting client_uids."}), 400
                    seen_custom_model_client_uids.add(client_uid)

                seen_custom_model_ids.add(definition["id"])
                custom_model_reference_ids[definition["id"]] = definition["id"]
                if client_uid:
                    custom_model_reference_ids[client_uid] = definition["id"]
                normalized_custom_models.append(definition)

            settings["custom_models"] = json.dumps(normalized_custom_models, ensure_ascii=False)

        if visible_model_order_raw is not None:
            if not isinstance(visible_model_order_raw, list):
                return jsonify({"error": "visible_model_order must be an array."}), 400

            normalized_visible_model_order: list[str] = []
            for value in visible_model_order_raw:
                model_id = _resolve_model_reference_id(value, custom_model_reference_ids)
                record = get_model_record(model_id, settings)
                if not record or not record.get("supports_tools"):
                    return jsonify({"error": "visible_model_order contains unsupported chat models."}), 400
                if record["id"] not in normalized_visible_model_order:
                    normalized_visible_model_order.append(record["id"])

            normalized_visible_model_order = normalize_visible_model_order(normalized_visible_model_order, settings)
            if not normalized_visible_model_order:
                return jsonify({"error": "At least one visible chat model is required."}), 400
            settings["visible_model_order"] = json.dumps(normalized_visible_model_order, ensure_ascii=False)

        if operation_model_preferences_raw is not None:
            if not isinstance(operation_model_preferences_raw, dict):
                return jsonify({"error": "operation_model_preferences must be an object."}), 400

            filtered_operation_preferences = {
                key: value
                for key, value in operation_model_preferences_raw.items()
                if key in MODEL_OPERATION_KEYS
            }
            resolved_operation_preferences: dict[str, str] = {}

            for operation_key, model_value in filtered_operation_preferences.items():
                candidate = _resolve_model_reference_id(model_value, custom_model_reference_ids)
                if candidate and get_model_record(candidate, settings) is None:
                    return jsonify({"error": f"operation_model_preferences.{operation_key} must reference a known model."}), 400
                resolved_operation_preferences[operation_key] = candidate

            normalized_operation_preferences = normalize_operation_model_preferences(resolved_operation_preferences, settings)
            settings["operation_model_preferences"] = json.dumps(normalized_operation_preferences, ensure_ascii=False)

        if operation_model_fallback_preferences_raw is not None:
            if not isinstance(operation_model_fallback_preferences_raw, dict):
                return jsonify({"error": "operation_model_fallback_preferences must be an object."}), 400

            filtered_operation_fallback_preferences = {
                key: value
                for key, value in operation_model_fallback_preferences_raw.items()
                if key in MODEL_OPERATION_KEYS
            }
            resolved_operation_fallback_preferences: dict[str, list[str] | str] = {}

            for operation_key, model_value in filtered_operation_fallback_preferences.items():
                if model_value in (None, ""):
                    resolved_operation_fallback_preferences[operation_key] = []
                    continue

                if isinstance(model_value, str):
                    candidate_values = [model_value]
                elif isinstance(model_value, list):
                    candidate_values = model_value
                else:
                    return jsonify({"error": f"operation_model_fallback_preferences.{operation_key} must be an array of model ids."}), 400

                for candidate_value in candidate_values:
                    candidate = _resolve_model_reference_id(candidate_value, custom_model_reference_ids)
                    if candidate and get_model_record(candidate, settings) is None:
                        return jsonify({"error": f"operation_model_fallback_preferences.{operation_key} must reference known models."}), 400
                resolved_operation_fallback_preferences[operation_key] = [
                    _resolve_model_reference_id(candidate_value, custom_model_reference_ids)
                    for candidate_value in candidate_values
                ]

            normalized_operation_fallback_preferences = normalize_operation_model_fallback_preferences(
                resolved_operation_fallback_preferences,
                settings,
            )
            settings["operation_model_fallback_preferences"] = json.dumps(
                normalized_operation_fallback_preferences,
                ensure_ascii=False,
            )

        if image_processing_method_raw is not None:
            normalized_image_processing_method = normalize_image_processing_method(image_processing_method_raw)
            if normalized_image_processing_method != str(image_processing_method_raw or "").strip().lower():
                return jsonify({"error": "image_processing_method must be one of auto, llm_helper, llm_direct, or local_ocr."}), 400
            settings["image_processing_method"] = normalized_image_processing_method

        if image_helper_model_raw is not None:
            candidate = _resolve_model_reference_id(image_helper_model_raw, custom_model_reference_ids)
            if candidate:
                record = get_model_record(candidate, settings)
                if record is None:
                    return jsonify({"error": "image_helper_model must reference a known model."}), 400
                if not record.get("supports_vision"):
                    return jsonify({"error": "image_helper_model must support image input."}), 400
            settings["image_helper_model"] = candidate

        if active_tools_raw is not None:
            if not isinstance(active_tools_raw, list):
                return jsonify({"error": "Invalid active tools."}), 400
            settings["active_tools"] = json.dumps(normalize_active_tool_names(active_tools_raw), ensure_ascii=False)

        if proxy_enabled_operations_raw is not None:
            if not isinstance(proxy_enabled_operations_raw, list):
                return jsonify({"error": "proxy_enabled_operations must be an array."}), 400

            incoming_proxy_operations = [str(value or "").strip().lower() for value in proxy_enabled_operations_raw]
            if any(operation not in PROXY_OPERATION_KEYS for operation in incoming_proxy_operations):
                return jsonify({"error": "proxy_enabled_operations contains unsupported operations."}), 400

            settings["proxy_enabled_operations"] = json.dumps(
                normalize_proxy_enabled_operations(incoming_proxy_operations),
                ensure_ascii=False,
            )

        if openrouter_http_referer_raw is not None:
            if not isinstance(openrouter_http_referer_raw, str):
                return jsonify({"error": "openrouter_http_referer must be a string."}), 400
            settings["openrouter_http_referer"] = openrouter_http_referer_raw.strip()[:500]

        if openrouter_app_title_raw is not None:
            if not isinstance(openrouter_app_title_raw, str):
                return jsonify({"error": "openrouter_app_title must be a string."}), 400
            settings["openrouter_app_title"] = openrouter_app_title_raw.strip()[:120]

        if login_session_timeout_minutes_raw is not None:
            try:
                login_session_timeout_minutes = int(login_session_timeout_minutes_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "login_session_timeout_minutes must be an integer."}), 400
            if not (1 <= login_session_timeout_minutes <= 10_080):
                return jsonify({"error": "login_session_timeout_minutes must be between 1 and 10080."}), 400
            settings["login_session_timeout_minutes"] = str(login_session_timeout_minutes)

        if login_max_failed_attempts_raw is not None:
            try:
                login_max_failed_attempts = int(login_max_failed_attempts_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "login_max_failed_attempts must be an integer."}), 400
            if not (1 <= login_max_failed_attempts <= 50):
                return jsonify({"error": "login_max_failed_attempts must be between 1 and 50."}), 400
            settings["login_max_failed_attempts"] = str(login_max_failed_attempts)

        if login_lockout_seconds_raw is not None:
            try:
                login_lockout_seconds = int(login_lockout_seconds_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "login_lockout_seconds must be an integer."}), 400
            if not (1 <= login_lockout_seconds <= 86_400):
                return jsonify({"error": "login_lockout_seconds must be between 1 and 86400."}), 400
            settings["login_lockout_seconds"] = str(login_lockout_seconds)

        if login_remember_session_days_raw is not None:
            try:
                login_remember_session_days = int(login_remember_session_days_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "login_remember_session_days must be an integer."}), 400
            if not (1 <= login_remember_session_days <= 3_650):
                return jsonify({"error": "login_remember_session_days must be between 1 and 3650."}), 400
            settings["login_remember_session_days"] = str(login_remember_session_days)

        if conversation_memory_enabled_raw is not None:
            settings["conversation_memory_enabled"] = _normalize_bool_setting_value(conversation_memory_enabled_raw)

        if ocr_enabled_raw is not None:
            settings["ocr_enabled"] = _normalize_bool_setting_value(ocr_enabled_raw)

        if ocr_provider_raw is not None:
            normalized_ocr_provider = str(ocr_provider_raw or "").strip().lower()
            if normalized_ocr_provider not in OCR_SUPPORTED_PROVIDERS:
                return jsonify({"error": f"ocr_provider must be one of {', '.join(sorted(OCR_SUPPORTED_PROVIDERS))}."}), 400
            settings["ocr_provider"] = normalized_ocr_provider

        if rag_enabled_raw is not None:
            settings["rag_enabled"] = _normalize_bool_setting_value(rag_enabled_raw)

        if youtube_transcripts_enabled_raw is not None:
            settings["youtube_transcripts_enabled"] = _normalize_bool_setting_value(youtube_transcripts_enabled_raw)

        if youtube_transcript_language_raw is not None:
            if not isinstance(youtube_transcript_language_raw, str):
                return jsonify({"error": "youtube_transcript_language must be a string."}), 400
            settings["youtube_transcript_language"] = youtube_transcript_language_raw.strip()[:32]

        if youtube_transcript_model_size_raw is not None:
            if not isinstance(youtube_transcript_model_size_raw, str):
                return jsonify({"error": "youtube_transcript_model_size must be a string."}), 400
            normalized_model_size = youtube_transcript_model_size_raw.strip()
            if not normalized_model_size:
                return jsonify({"error": "youtube_transcript_model_size cannot be empty."}), 400
            settings["youtube_transcript_model_size"] = normalized_model_size[:64]

        if chat_summary_model_raw is not None:
            candidate = _resolve_model_reference_id(chat_summary_model_raw, custom_model_reference_ids)
            if candidate and get_model_record(candidate, settings) is None:
                return jsonify({"error": "chat_summary_model must reference a known model."}), 400
            settings["chat_summary_model"] = candidate

        if rag_chunk_size_raw is not None:
            try:
                rag_chunk_size = int(rag_chunk_size_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "rag_chunk_size must be an integer."}), 400
            if not (300 <= rag_chunk_size <= CONTENT_MAX_CHARS):
                return jsonify({"error": f"rag_chunk_size must be between 300 and {CONTENT_MAX_CHARS}."}), 400
            settings["rag_chunk_size"] = str(rag_chunk_size)

        if rag_chunk_overlap_raw is not None:
            try:
                rag_chunk_overlap = int(rag_chunk_overlap_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "rag_chunk_overlap must be an integer."}), 400
            effective_rag_chunk_size = int(settings.get("rag_chunk_size") or get_rag_chunk_size(settings))
            if not (0 <= rag_chunk_overlap <= max(0, effective_rag_chunk_size // 2)):
                return jsonify({"error": "rag_chunk_overlap must be between 0 and half of rag_chunk_size."}), 400
            settings["rag_chunk_overlap"] = str(rag_chunk_overlap)

        if rag_max_chunks_per_source_raw is not None:
            try:
                rag_max_chunks_per_source = int(rag_max_chunks_per_source_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "rag_max_chunks_per_source must be an integer."}), 400
            if not (1 <= rag_max_chunks_per_source <= 20):
                return jsonify({"error": "rag_max_chunks_per_source must be between 1 and 20."}), 400
            settings["rag_max_chunks_per_source"] = str(rag_max_chunks_per_source)

        if rag_search_top_k_raw is not None:
            try:
                rag_search_top_k = int(rag_search_top_k_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "rag_search_top_k must be an integer."}), 400
            if not (1 <= rag_search_top_k <= 50):
                return jsonify({"error": "rag_search_top_k must be between 1 and 50."}), 400
            settings["rag_search_top_k"] = str(rag_search_top_k)

        if rag_search_min_similarity_raw is not None:
            try:
                rag_search_min_similarity = float(rag_search_min_similarity_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "rag_search_min_similarity must be a number."}), 400
            if not (0.0 <= rag_search_min_similarity <= 1.0):
                return jsonify({"error": "rag_search_min_similarity must be between 0.0 and 1.0."}), 400
            settings["rag_search_min_similarity"] = str(rag_search_min_similarity)

        if rag_query_expansion_enabled_raw is not None:
            settings["rag_query_expansion_enabled"] = _normalize_bool_setting_value(rag_query_expansion_enabled_raw)

        if rag_query_expansion_max_variants_raw is not None:
            try:
                rag_query_expansion_max_variants = int(rag_query_expansion_max_variants_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "rag_query_expansion_max_variants must be an integer."}), 400
            if not (1 <= rag_query_expansion_max_variants <= 10):
                return jsonify({"error": "rag_query_expansion_max_variants must be between 1 and 10."}), 400
            settings["rag_query_expansion_max_variants"] = str(rag_query_expansion_max_variants)

        if tool_memory_ttl_default_seconds_raw is not None:
            try:
                tool_memory_ttl_default_seconds = int(tool_memory_ttl_default_seconds_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "tool_memory_ttl_default_seconds must be an integer."}), 400
            if not (60 <= tool_memory_ttl_default_seconds <= 31_536_000):
                return jsonify({"error": "tool_memory_ttl_default_seconds must be between 60 and 31536000."}), 400
            settings["tool_memory_ttl_default_seconds"] = str(tool_memory_ttl_default_seconds)

        if tool_memory_ttl_web_seconds_raw is not None:
            try:
                tool_memory_ttl_web_seconds = int(tool_memory_ttl_web_seconds_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "tool_memory_ttl_web_seconds must be an integer."}), 400
            if not (60 <= tool_memory_ttl_web_seconds <= 31_536_000):
                return jsonify({"error": "tool_memory_ttl_web_seconds must be between 60 and 31536000."}), 400
            settings["tool_memory_ttl_web_seconds"] = str(tool_memory_ttl_web_seconds)

        if tool_memory_ttl_news_seconds_raw is not None:
            try:
                tool_memory_ttl_news_seconds = int(tool_memory_ttl_news_seconds_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "tool_memory_ttl_news_seconds must be an integer."}), 400
            if not (60 <= tool_memory_ttl_news_seconds <= 31_536_000):
                return jsonify({"error": "tool_memory_ttl_news_seconds must be between 60 and 31536000."}), 400
            settings["tool_memory_ttl_news_seconds"] = str(tool_memory_ttl_news_seconds)

        if fetch_raw_max_text_chars_raw is not None:
            try:
                fetch_raw_max_text_chars = int(fetch_raw_max_text_chars_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "fetch_raw_max_text_chars must be an integer."}), 400
            if not (1_000 <= fetch_raw_max_text_chars <= CONTENT_MAX_CHARS):
                return jsonify({"error": f"fetch_raw_max_text_chars must be between 1000 and {CONTENT_MAX_CHARS}."}), 400
            settings["fetch_raw_max_text_chars"] = str(fetch_raw_max_text_chars)

        if fetch_summary_max_chars_raw is not None:
            try:
                fetch_summary_max_chars = int(fetch_summary_max_chars_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "fetch_summary_max_chars must be an integer."}), 400
            if not (500 <= fetch_summary_max_chars <= CONTENT_MAX_CHARS):
                return jsonify({"error": f"fetch_summary_max_chars must be between 500 and {CONTENT_MAX_CHARS}."}), 400
            settings["fetch_summary_max_chars"] = str(fetch_summary_max_chars)

        effective_rag_enabled = get_rag_enabled(settings)

        normalized_rag_auto_inject_toggle = None
        if rag_auto_inject is not None and effective_rag_enabled:
            if isinstance(rag_auto_inject, bool):
                normalized_rag_auto_inject_toggle = rag_auto_inject
            else:
                normalized_rag_auto_inject_toggle = str(rag_auto_inject).strip().lower() in {"1", "true", "yes", "on"}

        if rag_sensitivity is not None:
            normalized_rag_sensitivity = str(rag_sensitivity or "").strip().lower()
            if normalized_rag_sensitivity not in RAG_SENSITIVITY_PRESETS:
                return jsonify({"error": "rag_sensitivity must be one of flexible, normal, or strict."}), 400
            settings["rag_sensitivity"] = normalized_rag_sensitivity

        if rag_context_size is not None:
            normalized_rag_context_size = str(rag_context_size or "").strip().lower()
            if normalized_rag_context_size not in RAG_CONTEXT_SIZE_PRESETS:
                return jsonify({"error": "rag_context_size must be one of small, medium, or large."}), 400
            settings["rag_context_size"] = normalized_rag_context_size

        if rag_source_types is not None:
            if not isinstance(rag_source_types, list):
                return jsonify({"error": "rag_source_types must be an array."}), 400
            normalized_rag_source_types = normalize_rag_source_types(rag_source_types)
            incoming_source_types = [str(value or "").strip().lower() for value in rag_source_types]
            if any(source_type not in normalized_rag_source_types for source_type in incoming_source_types):
                return jsonify({"error": "rag_source_types contains unsupported source types."}), 400
            settings["rag_source_types"] = json.dumps(normalized_rag_source_types, ensure_ascii=False)

        normalized_rag_auto_inject_source_types = None
        if rag_auto_inject_source_types is not None:
            if not isinstance(rag_auto_inject_source_types, list):
                return jsonify({"error": "rag_auto_inject_source_types must be an array."}), 400
            normalized_rag_auto_inject_source_types = normalize_rag_source_types(rag_auto_inject_source_types)
            incoming_auto_inject_source_types = [str(value or "").strip().lower() for value in rag_auto_inject_source_types]
            if any(source_type not in normalized_rag_auto_inject_source_types for source_type in incoming_auto_inject_source_types):
                return jsonify({"error": "rag_auto_inject_source_types contains unsupported source types."}), 400

        current_raw_rag_auto_inject_source_types = normalize_rag_source_types(
            settings.get("rag_auto_inject_source_types", DEFAULT_SETTINGS["rag_auto_inject_source_types"])
        )
        if not effective_rag_enabled:
            effective_rag_auto_inject_source_types = []
        elif normalized_rag_auto_inject_source_types is not None:
            effective_rag_auto_inject_source_types = normalized_rag_auto_inject_source_types
        elif normalized_rag_auto_inject_toggle is False:
            effective_rag_auto_inject_source_types = []
        elif normalized_rag_auto_inject_toggle is True:
            effective_rag_auto_inject_source_types = current_raw_rag_auto_inject_source_types or get_rag_source_types(settings)
        else:
            effective_rag_auto_inject_source_types = get_rag_auto_inject_source_types(settings)

        settings["rag_auto_inject_source_types"] = json.dumps(
            effective_rag_auto_inject_source_types,
            ensure_ascii=False,
        )
        settings["rag_auto_inject"] = "true" if effective_rag_auto_inject_source_types else "false"

        if tool_memory_auto_inject is not None and effective_rag_enabled:
            if isinstance(tool_memory_auto_inject, bool):
                settings["tool_memory_auto_inject"] = "true" if tool_memory_auto_inject else "false"
            else:
                settings["tool_memory_auto_inject"] = (
                    "true" if str(tool_memory_auto_inject).strip().lower() in {"1", "true", "yes", "on"} else "false"
                )
        elif not effective_rag_enabled:
            settings["tool_memory_auto_inject"] = "false"
            settings["rag_auto_inject_source_types"] = json.dumps([], ensure_ascii=False)
            settings["rag_auto_inject"] = "false"

        if chat_summary_mode_raw is not None:
            normalized_summary_mode = str(chat_summary_mode_raw or "").strip().lower()
            if normalized_summary_mode not in CHAT_SUMMARY_ALLOWED_MODES:
                return jsonify({"error": "chat_summary_mode must be one of auto, conservative, never, or aggressive."}), 400
            settings["chat_summary_mode"] = normalized_summary_mode

        if chat_summary_detail_level_raw is not None:
            normalized_summary_detail_level = str(chat_summary_detail_level_raw or "").strip().lower()
            if normalized_summary_detail_level not in {"very_concise", "concise", "balanced", "detailed", "comprehensive"}:
                return jsonify({"error": "chat_summary_detail_level must be one of very_concise, concise, balanced, detailed, or comprehensive."}), 400
            settings["chat_summary_detail_level"] = normalized_summary_detail_level

        if chat_summary_trigger_raw is not None:
            try:
                chat_summary_trigger = int(chat_summary_trigger_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "chat_summary_trigger_token_count must be an integer."}), 400
            if not (1_000 <= chat_summary_trigger <= 200_000):
                return jsonify({"error": "chat_summary_trigger_token_count must be between 1000 and 200000."}), 400
            settings["chat_summary_trigger_token_count"] = str(chat_summary_trigger)

        if summary_skip_first_raw is not None:
            try:
                summary_skip_first = int(summary_skip_first_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "summary_skip_first must be an integer."}), 400
            if not (0 <= summary_skip_first <= 20):
                return jsonify({"error": "summary_skip_first must be between 0 and 20."}), 400
            settings["summary_skip_first"] = str(summary_skip_first)

        if summary_skip_last_raw is not None:
            try:
                summary_skip_last = int(summary_skip_last_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "summary_skip_last must be an integer."}), 400
            if not (0 <= summary_skip_last <= 20):
                return jsonify({"error": "summary_skip_last must be between 0 and 20."}), 400
            settings["summary_skip_last"] = str(summary_skip_last)

        if prompt_max_input_tokens_raw is not None:
            try:
                prompt_max_input_tokens = int(prompt_max_input_tokens_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "prompt_max_input_tokens must be an integer."}), 400
            if not (8_000 <= prompt_max_input_tokens <= 120_000):
                return jsonify({"error": "prompt_max_input_tokens must be between 8000 and 120000."}), 400
            settings["prompt_max_input_tokens"] = str(prompt_max_input_tokens)

        if prompt_response_token_reserve_raw is not None:
            try:
                prompt_response_token_reserve = int(prompt_response_token_reserve_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "prompt_response_token_reserve must be an integer."}), 400
            if not (1_000 <= prompt_response_token_reserve <= 32_000):
                return jsonify({"error": "prompt_response_token_reserve must be between 1000 and 32000."}), 400
            settings["prompt_response_token_reserve"] = str(prompt_response_token_reserve)

        if prompt_recent_history_max_tokens_raw is not None:
            try:
                prompt_recent_history_max_tokens = int(prompt_recent_history_max_tokens_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "prompt_recent_history_max_tokens must be an integer."}), 400
            if not (1_000 <= prompt_recent_history_max_tokens <= 120_000):
                return jsonify({"error": "prompt_recent_history_max_tokens must be between 1000 and 120000."}), 400
            settings["prompt_recent_history_max_tokens"] = str(prompt_recent_history_max_tokens)

        if prompt_summary_max_tokens_raw is not None:
            try:
                prompt_summary_max_tokens = int(prompt_summary_max_tokens_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "prompt_summary_max_tokens must be an integer."}), 400
            if not (500 <= prompt_summary_max_tokens <= 120_000):
                return jsonify({"error": "prompt_summary_max_tokens must be between 500 and 120000."}), 400
            settings["prompt_summary_max_tokens"] = str(prompt_summary_max_tokens)

        if prompt_preflight_summary_token_count_raw is not None:
            try:
                prompt_preflight_summary_token_count = int(prompt_preflight_summary_token_count_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "prompt_preflight_summary_token_count must be an integer."}), 400
            if not (2_000 <= prompt_preflight_summary_token_count <= 200_000):
                return jsonify({"error": "prompt_preflight_summary_token_count must be between 2000 and 200000."}), 400
            settings["prompt_preflight_summary_token_count"] = str(prompt_preflight_summary_token_count)

        if prompt_rag_max_tokens_raw is not None:
            try:
                prompt_rag_max_tokens = int(prompt_rag_max_tokens_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "prompt_rag_max_tokens must be an integer."}), 400
            if not (0 <= prompt_rag_max_tokens <= 120_000):
                return jsonify({"error": "prompt_rag_max_tokens must be between 0 and 120000."}), 400
            settings["prompt_rag_max_tokens"] = str(prompt_rag_max_tokens)

        if prompt_tool_memory_max_tokens_raw is not None:
            try:
                prompt_tool_memory_max_tokens = int(prompt_tool_memory_max_tokens_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "prompt_tool_memory_max_tokens must be an integer."}), 400
            if not (0 <= prompt_tool_memory_max_tokens <= 120_000):
                return jsonify({"error": "prompt_tool_memory_max_tokens must be between 0 and 120000."}), 400
            settings["prompt_tool_memory_max_tokens"] = str(prompt_tool_memory_max_tokens)

        if prompt_tool_trace_max_tokens_raw is not None:
            try:
                prompt_tool_trace_max_tokens = int(prompt_tool_trace_max_tokens_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "prompt_tool_trace_max_tokens must be an integer."}), 400
            if not (0 <= prompt_tool_trace_max_tokens <= 120_000):
                return jsonify({"error": "prompt_tool_trace_max_tokens must be between 0 and 120000."}), 400
            settings["prompt_tool_trace_max_tokens"] = str(prompt_tool_trace_max_tokens)

        if summary_source_target_tokens_raw is not None:
            try:
                summary_source_target_tokens = int(summary_source_target_tokens_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "summary_source_target_tokens must be an integer."}), 400
            if not (1_000 <= summary_source_target_tokens <= 40_000):
                return jsonify({"error": "summary_source_target_tokens must be between 1000 and 40000."}), 400
            settings["summary_source_target_tokens"] = str(summary_source_target_tokens)

        if summary_retry_min_source_tokens_raw is not None:
            try:
                summary_retry_min_source_tokens = int(summary_retry_min_source_tokens_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "summary_retry_min_source_tokens must be an integer."}), 400
            if not (500 <= summary_retry_min_source_tokens <= 40_000):
                return jsonify({"error": "summary_retry_min_source_tokens must be between 500 and 40000."}), 400
            settings["summary_retry_min_source_tokens"] = str(summary_retry_min_source_tokens)

        if context_compaction_threshold_raw is not None:
            try:
                context_compaction_threshold = float(context_compaction_threshold_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "context_compaction_threshold must be a number."}), 400
            if not (0.5 <= context_compaction_threshold <= 0.98):
                return jsonify({"error": "context_compaction_threshold must be between 0.5 and 0.98."}), 400
            settings["context_compaction_threshold"] = str(context_compaction_threshold)

        if context_compaction_keep_recent_rounds_raw is not None:
            try:
                context_compaction_keep_recent_rounds = int(context_compaction_keep_recent_rounds_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "context_compaction_keep_recent_rounds must be an integer."}), 400
            if not (0 <= context_compaction_keep_recent_rounds <= 6):
                return jsonify({"error": "context_compaction_keep_recent_rounds must be between 0 and 6."}), 400
            settings["context_compaction_keep_recent_rounds"] = str(context_compaction_keep_recent_rounds)

        if context_selection_strategy_raw is not None:
            normalized_context_selection_strategy = str(context_selection_strategy_raw or "").strip().lower()
            if normalized_context_selection_strategy not in CONTEXT_SELECTION_ALLOWED_STRATEGIES:
                return jsonify({"error": "context_selection_strategy must be one of classic, entropy, or entropy_rag_hybrid."}), 400
            settings["context_selection_strategy"] = normalized_context_selection_strategy

        if entropy_profile_raw is not None:
            normalized_entropy_profile = str(entropy_profile_raw or "").strip().lower()
            if normalized_entropy_profile not in ENTROPY_PROFILE_PRESETS:
                return jsonify({"error": "entropy_profile must be one of conservative, balanced, or aggressive."}), 400
            settings["entropy_profile"] = normalized_entropy_profile

        if entropy_rag_budget_ratio_raw is not None:
            try:
                entropy_rag_budget_ratio = int(entropy_rag_budget_ratio_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "entropy_rag_budget_ratio must be an integer."}), 400
            if not (0 <= entropy_rag_budget_ratio <= 80):
                return jsonify({"error": "entropy_rag_budget_ratio must be between 0 and 80."}), 400
            settings["entropy_rag_budget_ratio"] = str(entropy_rag_budget_ratio)

        if entropy_protect_code_blocks_raw is not None:
            if isinstance(entropy_protect_code_blocks_raw, bool):
                settings["entropy_protect_code_blocks"] = "true" if entropy_protect_code_blocks_raw else "false"
            else:
                settings["entropy_protect_code_blocks"] = (
                    "true" if str(entropy_protect_code_blocks_raw).strip().lower() in {"1", "true", "yes", "on"} else "false"
                )

        if entropy_protect_tool_results_raw is not None:
            if isinstance(entropy_protect_tool_results_raw, bool):
                settings["entropy_protect_tool_results"] = "true" if entropy_protect_tool_results_raw else "false"
            else:
                settings["entropy_protect_tool_results"] = (
                    "true" if str(entropy_protect_tool_results_raw).strip().lower() in {"1", "true", "yes", "on"} else "false"
                )

        if entropy_reference_boost_raw is not None:
            if isinstance(entropy_reference_boost_raw, bool):
                settings["entropy_reference_boost"] = "true" if entropy_reference_boost_raw else "false"
            else:
                settings["entropy_reference_boost"] = (
                    "true" if str(entropy_reference_boost_raw).strip().lower() in {"1", "true", "yes", "on"} else "false"
                )

        if reasoning_auto_collapse_raw is not None:
            if isinstance(reasoning_auto_collapse_raw, bool):
                settings["reasoning_auto_collapse"] = "true" if reasoning_auto_collapse_raw else "false"
            else:
                settings["reasoning_auto_collapse"] = (
                    "true" if str(reasoning_auto_collapse_raw).strip().lower() in {"1", "true", "yes", "on"} else "false"
                )

        if pruning_enabled_raw is not None:
            if isinstance(pruning_enabled_raw, bool):
                settings["pruning_enabled"] = "true" if pruning_enabled_raw else "false"
            else:
                settings["pruning_enabled"] = (
                    "true" if str(pruning_enabled_raw).strip().lower() in {"1", "true", "yes", "on"} else "false"
                )

        if pruning_token_threshold_raw is not None:
            try:
                pruning_token_threshold = int(pruning_token_threshold_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "pruning_token_threshold must be an integer."}), 400
            if not (1_000 <= pruning_token_threshold <= 200_000):
                return jsonify({"error": "pruning_token_threshold must be between 1000 and 200000."}), 400
            settings["pruning_token_threshold"] = str(pruning_token_threshold)

        if pruning_batch_size_raw is not None:
            try:
                pruning_batch_size = int(pruning_batch_size_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "pruning_batch_size must be an integer."}), 400
            if not (1 <= pruning_batch_size <= 50):
                return jsonify({"error": "pruning_batch_size must be between 1 and 50."}), 400
            settings["pruning_batch_size"] = str(pruning_batch_size)

        if pruning_target_reduction_ratio_raw is not None:
            try:
                pruning_target_reduction_ratio = float(pruning_target_reduction_ratio_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "pruning_target_reduction_ratio must be a number."}), 400
            if not (0.1 <= pruning_target_reduction_ratio <= 0.9):
                return jsonify({"error": "pruning_target_reduction_ratio must be between 0.1 and 0.9."}), 400
            settings["pruning_target_reduction_ratio"] = str(pruning_target_reduction_ratio)

        if pruning_min_target_tokens_raw is not None:
            try:
                pruning_min_target_tokens = int(pruning_min_target_tokens_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "pruning_min_target_tokens must be an integer."}), 400
            if not (50 <= pruning_min_target_tokens <= 5_000):
                return jsonify({"error": "pruning_min_target_tokens must be between 50 and 5000."}), 400
            settings["pruning_min_target_tokens"] = str(pruning_min_target_tokens)

        effective_prompt_max_input_tokens = get_prompt_max_input_tokens(settings)
        configured_prompt_response_token_reserve = int(
            settings.get("prompt_response_token_reserve", get_prompt_response_token_reserve(settings))
        )
        if configured_prompt_response_token_reserve > effective_prompt_max_input_tokens - 2_000:
            return jsonify(
                {
                    "error": (
                        "prompt_response_token_reserve must leave at least 2000 tokens for prompt input. "
                        "Lower the reserve or increase prompt_max_input_tokens."
                    )
                }
            ), 400

        for setting_key, label in (
            ("prompt_recent_history_max_tokens", "prompt_recent_history_max_tokens"),
            ("prompt_summary_max_tokens", "prompt_summary_max_tokens"),
            ("prompt_rag_max_tokens", "prompt_rag_max_tokens"),
            ("prompt_tool_memory_max_tokens", "prompt_tool_memory_max_tokens"),
            ("prompt_tool_trace_max_tokens", "prompt_tool_trace_max_tokens"),
        ):
            configured_value = int(settings.get(setting_key, effective_prompt_max_input_tokens))
            if configured_value > effective_prompt_max_input_tokens:
                return jsonify({"error": f"{label} cannot exceed prompt_max_input_tokens."}), 400

        configured_summary_source_target_tokens = int(
            settings.get("summary_source_target_tokens", get_summary_source_target_tokens(settings))
        )
        configured_summary_retry_min_source_tokens = int(
            settings.get("summary_retry_min_source_tokens", get_summary_retry_min_source_tokens(settings))
        )
        if configured_summary_retry_min_source_tokens > configured_summary_source_target_tokens:
            return jsonify({"error": "summary_retry_min_source_tokens cannot exceed summary_source_target_tokens."}), 400

        if fetch_url_token_threshold_raw is not None:
            try:
                fetch_url_token_threshold = int(fetch_url_token_threshold_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "fetch_url_token_threshold must be an integer."}), 400
            if not (400 <= fetch_url_token_threshold <= 20_000):
                return jsonify({"error": "fetch_url_token_threshold must be between 400 and 20000."}), 400
            settings["fetch_url_token_threshold"] = str(fetch_url_token_threshold)

        if fetch_url_clip_aggressiveness_raw is not None:
            try:
                fetch_url_clip_aggressiveness = int(fetch_url_clip_aggressiveness_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "fetch_url_clip_aggressiveness must be an integer."}), 400
            if not (0 <= fetch_url_clip_aggressiveness <= 100):
                return jsonify({"error": "fetch_url_clip_aggressiveness must be between 0 and 100."}), 400
            settings["fetch_url_clip_aggressiveness"] = str(fetch_url_clip_aggressiveness)

        if fetch_html_converter_mode_raw is not None:
            normalized_fetch_html_converter_mode = str(fetch_html_converter_mode_raw or "").strip().lower()
            if normalized_fetch_html_converter_mode not in FETCH_HTML_CONVERTER_MODES:
                return jsonify({"error": "fetch_html_converter_mode must be one of internal, external, or hybrid."}), 400
            settings["fetch_html_converter_mode"] = normalized_fetch_html_converter_mode

        if fetch_url_summarized_max_input_chars_raw is not None:
            try:
                fetch_url_summarized_max_input_chars = int(fetch_url_summarized_max_input_chars_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "fetch_url_summarized_max_input_chars must be an integer."}), 400
            if not (4_000 <= fetch_url_summarized_max_input_chars <= CONTENT_MAX_CHARS):
                return jsonify({"error": f"fetch_url_summarized_max_input_chars must be between 4000 and {CONTENT_MAX_CHARS}."}), 400
            settings["fetch_url_summarized_max_input_chars"] = str(fetch_url_summarized_max_input_chars)

        if fetch_url_summarized_max_output_tokens_raw is not None:
            try:
                fetch_url_summarized_max_output_tokens = int(fetch_url_summarized_max_output_tokens_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "fetch_url_summarized_max_output_tokens must be an integer."}), 400
            if not (200 <= fetch_url_summarized_max_output_tokens <= 4_000):
                return jsonify({"error": "fetch_url_summarized_max_output_tokens must be between 200 and 4000."}), 400
            settings["fetch_url_summarized_max_output_tokens"] = str(fetch_url_summarized_max_output_tokens)

        if canvas_prompt_max_lines_raw is not None:
            try:
                canvas_prompt_max_lines = int(canvas_prompt_max_lines_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "canvas_prompt_max_lines must be an integer."}), 400
            if not (100 <= canvas_prompt_max_lines <= 3_000):
                return jsonify({"error": "canvas_prompt_max_lines must be between 100 and 3000."}), 400
            settings["canvas_prompt_max_lines"] = str(canvas_prompt_max_lines)

        if canvas_prompt_max_tokens_raw is not None:
            try:
                canvas_prompt_max_tokens = int(canvas_prompt_max_tokens_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "canvas_prompt_max_tokens must be an integer."}), 400
            if not (500 <= canvas_prompt_max_tokens <= 50_000):
                return jsonify({"error": "canvas_prompt_max_tokens must be between 500 and 50000."}), 400
            settings["canvas_prompt_max_tokens"] = str(canvas_prompt_max_tokens)

        if canvas_prompt_max_chars_raw is not None:
            try:
                canvas_prompt_max_chars = int(canvas_prompt_max_chars_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "canvas_prompt_max_chars must be an integer."}), 400
            if not (1_000 <= canvas_prompt_max_chars <= 200_000):
                return jsonify({"error": "canvas_prompt_max_chars must be between 1000 and 200000."}), 400
            settings["canvas_prompt_max_chars"] = str(canvas_prompt_max_chars)

        if canvas_prompt_code_line_max_chars_raw is not None:
            try:
                canvas_prompt_code_line_max_chars = int(canvas_prompt_code_line_max_chars_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "canvas_prompt_code_line_max_chars must be an integer."}), 400
            if not (40 <= canvas_prompt_code_line_max_chars <= 1_000):
                return jsonify({"error": "canvas_prompt_code_line_max_chars must be between 40 and 1000."}), 400
            settings["canvas_prompt_code_line_max_chars"] = str(canvas_prompt_code_line_max_chars)

        if canvas_prompt_text_line_max_chars_raw is not None:
            try:
                canvas_prompt_text_line_max_chars = int(canvas_prompt_text_line_max_chars_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "canvas_prompt_text_line_max_chars must be an integer."}), 400
            if not (40 <= canvas_prompt_text_line_max_chars <= 1_000):
                return jsonify({"error": "canvas_prompt_text_line_max_chars must be between 40 and 1000."}), 400
            settings["canvas_prompt_text_line_max_chars"] = str(canvas_prompt_text_line_max_chars)

        if canvas_expand_max_lines_raw is not None:
            try:
                canvas_expand_max_lines = int(canvas_expand_max_lines_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "canvas_expand_max_lines must be an integer."}), 400
            if not (100 <= canvas_expand_max_lines <= 4_000):
                return jsonify({"error": "canvas_expand_max_lines must be between 100 and 4000."}), 400
            settings["canvas_expand_max_lines"] = str(canvas_expand_max_lines)

        if canvas_scroll_window_lines_raw is not None:
            try:
                canvas_scroll_window_lines = int(canvas_scroll_window_lines_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "canvas_scroll_window_lines must be an integer."}), 400
            if not (50 <= canvas_scroll_window_lines <= 800):
                return jsonify({"error": "canvas_scroll_window_lines must be between 50 and 800."}), 400
            settings["canvas_scroll_window_lines"] = str(canvas_scroll_window_lines)

        if sub_agent_max_steps_raw is not None:
            try:
                sub_agent_max_steps = int(sub_agent_max_steps_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "sub_agent_max_steps must be an integer."}), 400
            if not (SUB_AGENT_MAX_STEPS_MIN <= sub_agent_max_steps <= SUB_AGENT_MAX_STEPS_MAX):
                return jsonify({"error": f"sub_agent_max_steps must be between {SUB_AGENT_MAX_STEPS_MIN} and {SUB_AGENT_MAX_STEPS_MAX}."}), 400
            settings["sub_agent_max_steps"] = str(sub_agent_max_steps)

        if sub_agent_timeout_seconds_raw is not None:
            try:
                sub_agent_timeout_seconds = int(sub_agent_timeout_seconds_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "sub_agent_timeout_seconds must be an integer."}), 400
            if not (5 <= sub_agent_timeout_seconds <= 900):
                return jsonify({"error": "sub_agent_timeout_seconds must be between 5 and 900."}), 400
            settings["sub_agent_timeout_seconds"] = str(sub_agent_timeout_seconds)

        if sub_agent_retry_attempts_raw is not None:
            try:
                sub_agent_retry_attempts = int(sub_agent_retry_attempts_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "sub_agent_retry_attempts must be an integer."}), 400
            if not (0 <= sub_agent_retry_attempts <= 5):
                return jsonify({"error": "sub_agent_retry_attempts must be between 0 and 5."}), 400
            settings["sub_agent_retry_attempts"] = str(sub_agent_retry_attempts)

        if sub_agent_retry_delay_seconds_raw is not None:
            try:
                sub_agent_retry_delay_seconds = int(sub_agent_retry_delay_seconds_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "sub_agent_retry_delay_seconds must be an integer."}), 400
            if not (0 <= sub_agent_retry_delay_seconds <= 60):
                return jsonify({"error": "sub_agent_retry_delay_seconds must be between 0 and 60."}), 400
            settings["sub_agent_retry_delay_seconds"] = str(sub_agent_retry_delay_seconds)

        if sub_agent_max_parallel_tools_raw is not None:
            try:
                sub_agent_max_parallel_tools = int(sub_agent_max_parallel_tools_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "sub_agent_max_parallel_tools must be an integer."}), 400
            if not (MAX_PARALLEL_TOOLS_MIN <= sub_agent_max_parallel_tools <= MAX_PARALLEL_TOOLS_MAX):
                return jsonify({"error": f"sub_agent_max_parallel_tools must be between {MAX_PARALLEL_TOOLS_MIN} and {MAX_PARALLEL_TOOLS_MAX}."}), 400
            settings["sub_agent_max_parallel_tools"] = str(sub_agent_max_parallel_tools)

        if sub_agent_allowed_tool_names_raw is not None:
            if not isinstance(sub_agent_allowed_tool_names_raw, list):
                return jsonify({"error": "sub_agent_allowed_tool_names must be an array."}), 400
            normalized_sub_agent_tools = normalize_sub_agent_allowed_tool_names(sub_agent_allowed_tool_names_raw)
            settings["sub_agent_allowed_tool_names"] = json.dumps(normalized_sub_agent_tools, ensure_ascii=False)

        if web_cache_ttl_hours_raw is not None:
            try:
                web_cache_ttl_hours = int(web_cache_ttl_hours_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "web_cache_ttl_hours must be an integer."}), 400
            if not (WEB_CACHE_TTL_HOURS_MIN <= web_cache_ttl_hours <= WEB_CACHE_TTL_HOURS_MAX):
                return jsonify({"error": f"web_cache_ttl_hours must be between {WEB_CACHE_TTL_HOURS_MIN} and {WEB_CACHE_TTL_HOURS_MAX}."}), 400
            settings["web_cache_ttl_hours"] = str(web_cache_ttl_hours)

        if openrouter_prompt_cache_enabled_raw is not None:
            if isinstance(openrouter_prompt_cache_enabled_raw, bool):
                settings["openrouter_prompt_cache_enabled"] = "true" if openrouter_prompt_cache_enabled_raw else "false"
            else:
                normalized_prompt_cache = str(openrouter_prompt_cache_enabled_raw).strip().lower()
                settings["openrouter_prompt_cache_enabled"] = (
                    "true"
                    if normalized_prompt_cache in {"1", "true", "yes", "on"}
                    else "false"
                )

        if openrouter_anthropic_cache_ttl_raw is not None:
            normalized_ttl = str(openrouter_anthropic_cache_ttl_raw).strip().lower()
            if normalized_ttl not in {"5m", "1h"}:
                return jsonify({"error": "openrouter_anthropic_cache_ttl must be '5m' or '1h'."}), 400
            settings["openrouter_anthropic_cache_ttl"] = normalized_ttl

        save_app_settings(settings)
        return jsonify(build_settings_payload())
