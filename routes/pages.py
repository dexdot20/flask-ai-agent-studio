from __future__ import annotations

import json
from pathlib import Path

from flask import jsonify, render_template, request

from config import (
    CHAT_SUMMARY_ALLOWED_MODES,
    CLARIFICATION_QUESTION_LIMIT_MAX,
    CLARIFICATION_QUESTION_LIMIT_MIN,
    DEFAULT_SETTINGS,
    MAX_PARALLEL_TOOLS_MAX,
    MAX_PARALLEL_TOOLS_MIN,
    MAX_USER_PREFERENCES_LENGTH,
    RAG_CONTEXT_SIZE_PRESETS,
    RAG_ENABLED,
    RAG_SENSITIVITY_PRESETS,
    SCRATCHPAD_DEFAULT_SECTION,
    SCRATCHPAD_SECTION_METADATA,
    SCRATCHPAD_SECTION_ORDER,
    SCRATCHPAD_SECTION_SETTING_KEYS,
    SUB_AGENT_ALLOWED_TOOL_NAMES,
    SUB_AGENT_RETRY_ATTEMPTS_MAX,
    SUB_AGENT_RETRY_ATTEMPTS_MIN,
    SUB_AGENT_RETRY_DELAY_MAX_SECONDS,
    SUB_AGENT_RETRY_DELAY_MIN_SECONDS,
    SUB_AGENT_TIMEOUT_MAX_SECONDS,
    SUB_AGENT_TIMEOUT_MIN_SECONDS,
    get_feature_flags,
)
from routes.auth import is_login_pin_enabled
from db import (
    count_scratchpad_notes,
    get_active_tool_names,
    get_all_scratchpad_sections,
    get_app_settings,
    get_canvas_expand_max_lines,
    get_canvas_prompt_max_lines,
    get_canvas_prompt_max_tokens,
    get_canvas_scroll_window_lines,
    get_chat_summary_mode,
    get_chat_summary_detail_level,
    get_chat_summary_trigger_token_count,
    get_clarification_max_questions,
    get_fetch_url_clip_aggressiveness,
    get_fetch_url_token_threshold,
    get_max_parallel_tools,
    get_model_temperature,
    get_proxy_enabled_operations,
    get_pruning_batch_size,
    get_pruning_enabled,
    get_pruning_token_threshold,
    get_reasoning_auto_collapse,
    get_rag_auto_inject_enabled,
    get_rag_context_size,
    get_rag_source_types,
    get_rag_sensitivity,
    get_summary_skip_first,
    get_summary_skip_last,
    get_sub_agent_max_parallel_tools,
    get_sub_agent_allowed_tool_names,
    get_sub_agent_include_canvas_context,
    get_sub_agent_include_conversation_context,
    get_sub_agent_retry_attempts,
    get_sub_agent_retry_delay_seconds,
    get_sub_agent_timeout_seconds,
    get_tool_memory_auto_inject_enabled,
    normalize_active_tool_names,
    normalize_rag_source_types,
    normalize_scratchpad_text,
    save_app_settings,
)
from model_registry import (
    MODEL_OPERATION_KEYS,
    canonicalize_model_id,
    get_all_models,
    get_chat_capable_models,
    get_default_chat_model_id,
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
from tool_registry import TOOL_SPEC_BY_NAME


TOOL_PERMISSION_LABELS = {
    "append_scratchpad": "Append persistent scratchpad",
    "replace_scratchpad": "Rewrite persistent scratchpad section",
    "read_scratchpad": "Read persistent scratchpad",
    "ask_clarifying_question": "Ask interactive clarification questions",
    "sub_agent": "Delegate to sub-agent",
    "image_explain": "Follow up on stored images",
    "search_knowledge_base": "Knowledge base search",
    "search_tool_memory": "Search tool memory",
    "search_web": "Web search",
    "fetch_url": "Read URL content",
    "fetch_url_summarized": "Fetch URL (summarized)",
    "grep_fetched_content": "Search fetched page content",
    "search_news_ddgs": "Search news (DDGS)",
    "search_news_google": "Search news (Google)",
    "create_canvas_document": "Create canvas document",
    "expand_canvas_document": "Expand canvas document",
    "scroll_canvas_document": "Scroll canvas document",
    "search_canvas_document": "Search canvas document",
    "rewrite_canvas_document": "Rewrite canvas document",
    "preview_canvas_changes": "Preview canvas changes",
    "batch_canvas_edits": "Batch canvas edits",
    "transform_canvas_lines": "Transform canvas lines",
    "update_canvas_metadata": "Update canvas metadata",
    "set_canvas_viewport": "Set canvas viewport",
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
    "validate_project_workspace": "Validate project workspace",
}

TOOL_PERMISSION_DESCRIPTIONS = {
    "append_scratchpad": "Append durable facts to a named persistent memory section.",
    "replace_scratchpad": "Fully rewrite one persistent memory section.",
    "read_scratchpad": "Read the current persistent memory before editing.",
    "ask_clarifying_question": "Pause and ask the user structured questions before answering.",
    "sub_agent": "Delegate a bounded research task to a read-only helper agent.",
    "image_explain": "Ask follow-up questions about a previously uploaded image.",
    "search_knowledge_base": "Semantic search over synced chats and uploaded documents.",
    "search_tool_memory": "Search remembered web research results from past conversations.",
    "search_web": "Live web search via DuckDuckGo for current facts.",
    "fetch_url": "Read and extract cleaned text from a specific web page.",
    "fetch_url_summarized": "Fetch a page and return an AI-generated summary only.",
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
    "transform_canvas_lines": "Apply a text transformation to a range of lines in a canvas document.",
    "update_canvas_metadata": "Update the title, language, or other metadata of a canvas document.",
    "set_canvas_viewport": "Pin a line range as the active viewport for a canvas document.",
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
        "note": "These tools are still context-gated during runtime if the prompt is not web-related.",
    },
    "canvas": {
        "title": "Canvas Editing",
        "description": "Editable draft documents, canvas search, and line-level changes inside the conversation canvas.",
        "note": "Canvas edit tools can automatically pull in inspection helpers such as expand and scroll.",
    },
    "workspace": {
        "title": "Workspace Sandbox",
        "description": "Create, read, update, and validate files inside the conversation workspace only.",
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
    if name in {"append_scratchpad", "replace_scratchpad", "read_scratchpad", "ask_clarifying_question", "sub_agent", "image_explain", "search_knowledge_base", "search_tool_memory"}:
        return "assistant"
    if name in {"search_web", "fetch_url", "fetch_url_summarized", "grep_fetched_content", "search_news_ddgs", "search_news_google"}:
        return "research"
    if name in {
        "create_canvas_document",
        "expand_canvas_document",
        "scroll_canvas_document",
        "search_canvas_document",
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


def build_sub_agent_tool_permission_sections() -> list[dict[str, object]]:
    allowed_tools = set(SUB_AGENT_ALLOWED_TOOL_NAMES)
    sections: list[dict[str, object]] = []
    for section in build_tool_permission_sections():
        filtered_tools = [tool for tool in section["tools"] if tool["name"] in allowed_tools]
        if not filtered_tools:
            continue
        sections.append({**section, "tools": filtered_tools})
    return sections


def build_settings_payload() -> dict:
    raw = get_app_settings()
    available_models = get_all_models(raw)
    visible_chat_models = get_visible_chat_models(raw)
    return {
        "user_preferences": raw["user_preferences"],
        "scratchpad": raw.get("scratchpad", ""),
        "scratchpad_sections": build_scratchpad_sections_payload(raw),
        "max_steps": int(raw.get("max_steps", DEFAULT_SETTINGS["max_steps"])),
        "max_parallel_tools": get_max_parallel_tools(raw),
        "temperature": get_model_temperature(raw),
        "clarification_max_questions": get_clarification_max_questions(raw),
        "available_models": available_models,
        "custom_models": normalize_custom_models(raw.get("custom_models")),
        "visible_model_order": [model["id"] for model in visible_chat_models],
        "default_chat_model": get_default_chat_model_id(raw),
        "operation_model_preferences": get_operation_model_preferences(raw),
        "operation_model_fallback_preferences": get_operation_model_fallback_preferences(raw),
        "image_processing_method": normalize_image_processing_method(raw.get("image_processing_method")),
        "active_tools": get_active_tool_names(raw),
        "proxy_enabled_operations": get_proxy_enabled_operations(raw),
        "rag_auto_inject": get_rag_auto_inject_enabled(raw),
        "rag_sensitivity": get_rag_sensitivity(raw),
        "rag_context_size": get_rag_context_size(raw),
        "rag_source_types": get_rag_source_types(raw),
        "tool_memory_auto_inject": get_tool_memory_auto_inject_enabled(raw),
        "canvas_prompt_max_lines": get_canvas_prompt_max_lines(raw),
        "canvas_prompt_max_tokens": get_canvas_prompt_max_tokens(raw),
        "canvas_expand_max_lines": get_canvas_expand_max_lines(raw),
        "canvas_scroll_window_lines": get_canvas_scroll_window_lines(raw),
        "sub_agent_timeout_seconds": get_sub_agent_timeout_seconds(raw),
        "sub_agent_max_parallel_tools": get_sub_agent_max_parallel_tools(raw),
        "sub_agent_allowed_tool_names": get_sub_agent_allowed_tool_names(raw),
        "sub_agent_include_conversation_context": get_sub_agent_include_conversation_context(raw),
        "sub_agent_include_canvas_context": get_sub_agent_include_canvas_context(raw),
        "sub_agent_retry_attempts": get_sub_agent_retry_attempts(raw),
        "sub_agent_retry_delay_seconds": get_sub_agent_retry_delay_seconds(raw),
        "chat_summary_detail_level": get_chat_summary_detail_level(raw),
        "chat_summary_mode": get_chat_summary_mode(raw),
        "chat_summary_trigger_token_count": get_chat_summary_trigger_token_count(raw),
        "summary_skip_first": get_summary_skip_first(raw),
        "summary_skip_last": get_summary_skip_last(raw),
        "reasoning_auto_collapse": get_reasoning_auto_collapse(raw),
        "pruning_enabled": get_pruning_enabled(raw),
        "pruning_token_threshold": get_pruning_token_threshold(raw),
        "pruning_batch_size": get_pruning_batch_size(raw),
        "fetch_url_token_threshold": get_fetch_url_token_threshold(raw),
        "fetch_url_clip_aggressiveness": get_fetch_url_clip_aggressiveness(raw),
        "features": get_feature_flags(),
        "sub_agent_tool_sections": build_sub_agent_tool_permission_sections(),
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
            sub_agent_tool_sections=build_sub_agent_tool_permission_sections(),
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
        max_steps_raw = data.get("max_steps")
        max_parallel_tools_raw = data.get("max_parallel_tools")
        temperature_raw = data.get("temperature")
        clarification_max_questions_raw = data.get("clarification_max_questions")
        custom_models_raw = data.get("custom_models")
        visible_model_order_raw = data.get("visible_model_order")
        operation_model_preferences_raw = data.get("operation_model_preferences")
        operation_model_fallback_preferences_raw = data.get("operation_model_fallback_preferences")
        image_processing_method_raw = data.get("image_processing_method")
        active_tools_raw = data.get("active_tools")
        proxy_enabled_operations_raw = data.get("proxy_enabled_operations")
        rag_auto_inject = data.get("rag_auto_inject")
        rag_sensitivity = data.get("rag_sensitivity")
        rag_context_size = data.get("rag_context_size")
        rag_source_types = data.get("rag_source_types")
        tool_memory_auto_inject = data.get("tool_memory_auto_inject")
        chat_summary_mode_raw = data.get("chat_summary_mode")
        chat_summary_detail_level_raw = data.get("chat_summary_detail_level")
        chat_summary_trigger_raw = data.get("chat_summary_trigger_token_count")
        summary_skip_first_raw = data.get("summary_skip_first")
        summary_skip_last_raw = data.get("summary_skip_last")
        reasoning_auto_collapse_raw = data.get("reasoning_auto_collapse")
        pruning_enabled_raw = data.get("pruning_enabled")
        pruning_token_threshold_raw = data.get("pruning_token_threshold")
        pruning_batch_size_raw = data.get("pruning_batch_size")
        fetch_url_token_threshold_raw = data.get("fetch_url_token_threshold")
        fetch_url_clip_aggressiveness_raw = data.get("fetch_url_clip_aggressiveness")
        canvas_prompt_max_lines_raw = data.get("canvas_prompt_max_lines")
        canvas_prompt_max_tokens_raw = data.get("canvas_prompt_max_tokens")
        canvas_expand_max_lines_raw = data.get("canvas_expand_max_lines")
        canvas_scroll_window_lines_raw = data.get("canvas_scroll_window_lines")
        sub_agent_timeout_seconds_raw = data.get("sub_agent_timeout_seconds")
        sub_agent_max_parallel_tools_raw = data.get("sub_agent_max_parallel_tools")
        sub_agent_allowed_tool_names_raw = data.get("sub_agent_allowed_tool_names")
        sub_agent_include_conversation_context_raw = data.get("sub_agent_include_conversation_context")
        sub_agent_include_canvas_context_raw = data.get("sub_agent_include_canvas_context")
        sub_agent_retry_attempts_raw = data.get("sub_agent_retry_attempts")
        sub_agent_retry_delay_seconds_raw = data.get("sub_agent_retry_delay_seconds")
        scratchpad = data.get("scratchpad")
        scratchpad_sections_raw = data.get("scratchpad_sections")

        if (
            user_preferences is None
            and scratchpad is None
            and scratchpad_sections_raw is None
            and max_steps_raw is None
            and max_parallel_tools_raw is None
            and temperature_raw is None
            and clarification_max_questions_raw is None
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
            and tool_memory_auto_inject is None
            and chat_summary_mode_raw is None
            and chat_summary_detail_level_raw is None
            and chat_summary_trigger_raw is None
            and summary_skip_first_raw is None
            and summary_skip_last_raw is None
            and reasoning_auto_collapse_raw is None
            and pruning_enabled_raw is None
            and pruning_token_threshold_raw is None
            and pruning_batch_size_raw is None
            and fetch_url_token_threshold_raw is None
            and fetch_url_clip_aggressiveness_raw is None
            and canvas_prompt_max_lines_raw is None
            and canvas_prompt_max_tokens_raw is None
            and canvas_expand_max_lines_raw is None
            and canvas_scroll_window_lines_raw is None
            and sub_agent_timeout_seconds_raw is None
            and sub_agent_max_parallel_tools_raw is None
            and sub_agent_allowed_tool_names_raw is None
            and sub_agent_include_conversation_context_raw is None
            and sub_agent_include_canvas_context_raw is None
            and sub_agent_retry_attempts_raw is None
            and sub_agent_retry_delay_seconds_raw is None
        ):
            return jsonify({"error": "No settings provided."}), 400

        settings = get_app_settings()

        if user_preferences is not None:
            if not isinstance(user_preferences, str):
                return jsonify({"error": "Invalid user preferences."}), 400
            settings["user_preferences"] = user_preferences.strip()[:MAX_USER_PREFERENCES_LENGTH]

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

        if custom_models_raw is not None:
            if not isinstance(custom_models_raw, list):
                return jsonify({"error": "custom_models must be an array."}), 400

            normalized_custom_models = []
            seen_custom_model_ids: set[str] = set()
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
                seen_custom_model_ids.add(definition["id"])
                normalized_custom_models.append(definition)

            settings["custom_models"] = json.dumps(normalized_custom_models, ensure_ascii=False)

        if visible_model_order_raw is not None:
            if not isinstance(visible_model_order_raw, list):
                return jsonify({"error": "visible_model_order must be an array."}), 400

            normalized_visible_model_order: list[str] = []
            for value in visible_model_order_raw:
                model_id = canonicalize_model_id(value)
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

            for operation_key, model_value in filtered_operation_preferences.items():
                candidate = canonicalize_model_id(model_value)
                if candidate and get_model_record(candidate, settings) is None:
                    return jsonify({"error": f"operation_model_preferences.{operation_key} must reference a known model."}), 400

            normalized_operation_preferences = normalize_operation_model_preferences(filtered_operation_preferences, settings)
            settings["operation_model_preferences"] = json.dumps(normalized_operation_preferences, ensure_ascii=False)

        if operation_model_fallback_preferences_raw is not None:
            if not isinstance(operation_model_fallback_preferences_raw, dict):
                return jsonify({"error": "operation_model_fallback_preferences must be an object."}), 400

            filtered_operation_fallback_preferences = {
                key: value
                for key, value in operation_model_fallback_preferences_raw.items()
                if key in MODEL_OPERATION_KEYS
            }

            for operation_key, model_value in filtered_operation_fallback_preferences.items():
                if model_value in (None, ""):
                    continue

                if isinstance(model_value, str):
                    candidate_values = [model_value]
                elif isinstance(model_value, list):
                    candidate_values = model_value
                else:
                    return jsonify({"error": f"operation_model_fallback_preferences.{operation_key} must be an array of model ids."}), 400

                for candidate_value in candidate_values:
                    candidate = canonicalize_model_id(candidate_value)
                    if candidate and get_model_record(candidate, settings) is None:
                        return jsonify({"error": f"operation_model_fallback_preferences.{operation_key} must reference known models."}), 400

            normalized_operation_fallback_preferences = normalize_operation_model_fallback_preferences(
                filtered_operation_fallback_preferences,
                settings,
            )
            settings["operation_model_fallback_preferences"] = json.dumps(
                normalized_operation_fallback_preferences,
                ensure_ascii=False,
            )

        if image_processing_method_raw is not None:
            normalized_image_processing_method = normalize_image_processing_method(image_processing_method_raw)
            if normalized_image_processing_method != str(image_processing_method_raw or "").strip().lower():
                return jsonify({"error": "image_processing_method must be one of auto, llm, local_ocr, local_vl, or local_both."}), 400
            settings["image_processing_method"] = normalized_image_processing_method

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

        if rag_auto_inject is not None and RAG_ENABLED:
            if isinstance(rag_auto_inject, bool):
                settings["rag_auto_inject"] = "true" if rag_auto_inject else "false"
            else:
                settings["rag_auto_inject"] = (
                    "true" if str(rag_auto_inject).strip().lower() in {"1", "true", "yes", "on"} else "false"
                )
        elif not RAG_ENABLED:
            settings["rag_auto_inject"] = "false"

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

        if tool_memory_auto_inject is not None and RAG_ENABLED:
            if isinstance(tool_memory_auto_inject, bool):
                settings["tool_memory_auto_inject"] = "true" if tool_memory_auto_inject else "false"
            else:
                settings["tool_memory_auto_inject"] = (
                    "true" if str(tool_memory_auto_inject).strip().lower() in {"1", "true", "yes", "on"} else "false"
                )
        elif not RAG_ENABLED:
            settings["tool_memory_auto_inject"] = "false"

        if chat_summary_mode_raw is not None:
            normalized_summary_mode = str(chat_summary_mode_raw or "").strip().lower()
            if normalized_summary_mode not in CHAT_SUMMARY_ALLOWED_MODES:
                return jsonify({"error": "chat_summary_mode must be one of auto, never, or aggressive."}), 400
            settings["chat_summary_mode"] = normalized_summary_mode

        if chat_summary_detail_level_raw is not None:
            normalized_summary_detail_level = str(chat_summary_detail_level_raw or "").strip().lower()
            if normalized_summary_detail_level not in {"concise", "balanced", "detailed"}:
                return jsonify({"error": "chat_summary_detail_level must be one of concise, balanced, or detailed."}), 400
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
            if not (500 <= canvas_prompt_max_tokens <= 20_000):
                return jsonify({"error": "canvas_prompt_max_tokens must be between 500 and 20000."}), 400
            settings["canvas_prompt_max_tokens"] = str(canvas_prompt_max_tokens)

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

        if sub_agent_timeout_seconds_raw is not None:
            try:
                sub_agent_timeout_seconds = int(sub_agent_timeout_seconds_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "sub_agent_timeout_seconds must be an integer."}), 400
            if not (SUB_AGENT_TIMEOUT_MIN_SECONDS <= sub_agent_timeout_seconds <= SUB_AGENT_TIMEOUT_MAX_SECONDS):
                return jsonify({"error": f"sub_agent_timeout_seconds must be between {SUB_AGENT_TIMEOUT_MIN_SECONDS} and {SUB_AGENT_TIMEOUT_MAX_SECONDS}."}), 400
            settings["sub_agent_timeout_seconds"] = str(sub_agent_timeout_seconds)

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
            normalized_sub_agent_tools = [
                tool_name
                for tool_name in normalize_active_tool_names(sub_agent_allowed_tool_names_raw)
                if tool_name in SUB_AGENT_ALLOWED_TOOL_NAMES
            ]
            settings["sub_agent_allowed_tool_names"] = json.dumps(normalized_sub_agent_tools, ensure_ascii=False)

        if sub_agent_include_conversation_context_raw is not None:
            if isinstance(sub_agent_include_conversation_context_raw, bool):
                settings["sub_agent_include_conversation_context"] = (
                    "true" if sub_agent_include_conversation_context_raw else "false"
                )
            else:
                settings["sub_agent_include_conversation_context"] = (
                    "true"
                    if str(sub_agent_include_conversation_context_raw).strip().lower() in {"1", "true", "yes", "on"}
                    else "false"
                )

        if sub_agent_include_canvas_context_raw is not None:
            if isinstance(sub_agent_include_canvas_context_raw, bool):
                settings["sub_agent_include_canvas_context"] = (
                    "true" if sub_agent_include_canvas_context_raw else "false"
                )
            else:
                settings["sub_agent_include_canvas_context"] = (
                    "true"
                    if str(sub_agent_include_canvas_context_raw).strip().lower() in {"1", "true", "yes", "on"}
                    else "false"
                )

        if sub_agent_retry_attempts_raw is not None:
            try:
                sub_agent_retry_attempts = int(sub_agent_retry_attempts_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "sub_agent_retry_attempts must be an integer."}), 400
            if not (SUB_AGENT_RETRY_ATTEMPTS_MIN <= sub_agent_retry_attempts <= SUB_AGENT_RETRY_ATTEMPTS_MAX):
                return jsonify({"error": f"sub_agent_retry_attempts must be between {SUB_AGENT_RETRY_ATTEMPTS_MIN} and {SUB_AGENT_RETRY_ATTEMPTS_MAX}."}), 400
            settings["sub_agent_retry_attempts"] = str(sub_agent_retry_attempts)

        if sub_agent_retry_delay_seconds_raw is not None:
            try:
                sub_agent_retry_delay_seconds = int(sub_agent_retry_delay_seconds_raw)
            except (TypeError, ValueError):
                return jsonify({"error": "sub_agent_retry_delay_seconds must be an integer."}), 400
            if not (SUB_AGENT_RETRY_DELAY_MIN_SECONDS <= sub_agent_retry_delay_seconds <= SUB_AGENT_RETRY_DELAY_MAX_SECONDS):
                return jsonify({"error": f"sub_agent_retry_delay_seconds must be between {SUB_AGENT_RETRY_DELAY_MIN_SECONDS} and {SUB_AGENT_RETRY_DELAY_MAX_SECONDS}."}), 400
            settings["sub_agent_retry_delay_seconds"] = str(sub_agent_retry_delay_seconds)

        save_app_settings(settings)
        return jsonify(build_settings_payload())
