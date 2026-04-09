from __future__ import annotations

import ipaddress
import json
import os

from dotenv import load_dotenv

from model_registry import (
    BUILTIN_MODEL_IDS,
    BUILTIN_MODELS,
    DEFAULT_CHAT_MODEL,
    DEFAULT_IMAGE_PROCESSING_METHOD,
    DEFAULT_OPERATION_MODEL_PREFERENCES,
    DEFAULT_OPERATION_MODEL_FALLBACK_PREFERENCES,
    DEFAULT_VISIBLE_CHAT_MODEL_ORDER,
)
from proxy_settings import DEFAULT_PROXY_ENABLED_OPERATIONS

load_dotenv()

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "chatbot.db")
IMAGE_STORAGE_DIR = (os.getenv("IMAGE_STORAGE_DIR") or os.path.join(BASE_DIR, "data", "images")).strip()
PROJECT_WORKSPACE_ROOT = (os.getenv("PROJECT_WORKSPACE_ROOT") or os.path.join(BASE_DIR, "data", "workspaces")).strip()
PROXIES_PATH = os.path.join(BASE_DIR, "proxies.txt")
AGENT_TRACE_LOG_PATH = (os.getenv("AGENT_TRACE_LOG_PATH") or os.path.join(BASE_DIR, "logs", "agent-trace.log")).strip()
SECRET_KEY = (os.getenv("FLASK_SECRET_KEY") or os.getenv("SECRET_KEY") or "dev-only-change-me").strip()
LOGIN_PIN = (os.getenv("LOGIN_PIN") or "").strip()
DEEPSEEK_API_KEY = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
OPENROUTER_API_KEY = (os.getenv("OPENROUTER_API_KEY") or "").strip()
OPENROUTER_HTTP_REFERER = (os.getenv("OPENROUTER_HTTP_REFERER") or os.getenv("OPENROUTER_SITE_URL") or "").strip()
OPENROUTER_APP_TITLE = (os.getenv("OPENROUTER_APP_TITLE") or os.getenv("OPENROUTER_X_TITLE") or "").strip()

AVAILABLE_MODELS = [{"id": model["id"], "name": model["name"]} for model in BUILTIN_MODELS]
AVAILABLE_MODEL_IDS = set(BUILTIN_MODEL_IDS)


def _parse_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value in (None, ""):
        return default
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return default


def _parse_bool_env(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value in (None, ""):
        return default
    return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}


def _parse_float_env(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value in (None, ""):
        return default
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return default


LOGIN_SESSION_TIMEOUT_MINUTES = max(1, _parse_int_env("LOGIN_SESSION_TIMEOUT_MINUTES", 30))
LOGIN_MAX_FAILED_ATTEMPTS = max(1, _parse_int_env("LOGIN_MAX_FAILED_ATTEMPTS", 3))
LOGIN_LOCKOUT_SECONDS = max(1, _parse_int_env("LOGIN_LOCKOUT_SECONDS", 300))
LOGIN_REMEMBER_SESSION_DAYS = max(1, _parse_int_env("LOGIN_REMEMBER_SESSION_DAYS", 3650))


IMAGE_MAX_BYTES = 10 * 1024 * 1024
IMAGE_ALLOWED_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
}

DOCUMENT_ALLOWED_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/pdf",
    "text/plain",
    "text/csv",
    "text/markdown",
}
DOCUMENT_MAX_BYTES = 20 * 1024 * 1024
DOCUMENT_MAX_TEXT_CHARS = 50_000
DOCUMENT_STORAGE_DIR = (os.getenv("DOCUMENT_STORAGE_DIR") or os.path.join(BASE_DIR, "data", "documents")).strip()
YOUTUBE_TRANSCRIPTS_ENABLED = _parse_bool_env("YOUTUBE_TRANSCRIPTS_ENABLED", False)
YOUTUBE_TRANSCRIPTS_DISABLED_FEATURE_ERROR = "YouTube video transcript feature is disabled in .env."
YOUTUBE_TRANSCRIPT_MODEL_SIZE = (os.getenv("YOUTUBE_TRANSCRIPT_MODEL_SIZE") or "small").strip() or "small"
YOUTUBE_TRANSCRIPT_DEVICE = (os.getenv("YOUTUBE_TRANSCRIPT_DEVICE") or "auto").strip() or "auto"
YOUTUBE_TRANSCRIPT_COMPUTE_TYPE = (os.getenv("YOUTUBE_TRANSCRIPT_COMPUTE_TYPE") or "int8").strip() or "int8"
YOUTUBE_TRANSCRIPT_DEFAULT_LANGUAGE = (os.getenv("YOUTUBE_TRANSCRIPT_DEFAULT_LANGUAGE") or "").strip()
OCR_ENABLED = _parse_bool_env("OCR_ENABLED", True)
CONVERSATION_MEMORY_ENABLED = _parse_bool_env("CONVERSATION_MEMORY_ENABLED", True)
OCR_PROVIDER = (os.getenv("OCR_PROVIDER") or "paddleocr").strip().lower() or "paddleocr"
OCR_SUPPORTED_PROVIDERS = {"paddleocr", "easyocr"}
OCR_PRELOAD_ON_STARTUP = _parse_bool_env("OCR_PRELOAD", True)
IMAGE_UPLOADS_ENABLED = OCR_ENABLED or bool(OPENROUTER_API_KEY) or bool(DEEPSEEK_API_KEY)

SUB_AGENT_TIMEOUT_MIN_SECONDS = 5
SUB_AGENT_TIMEOUT_MAX_SECONDS = 900
SUB_AGENT_DEFAULT_TIMEOUT_SECONDS = 240
SUB_AGENT_RETRY_ATTEMPTS_MIN = 0
SUB_AGENT_RETRY_ATTEMPTS_MAX = 5
SUB_AGENT_DEFAULT_RETRY_ATTEMPTS = 2
SUB_AGENT_RETRY_DELAY_MIN_SECONDS = 0
SUB_AGENT_RETRY_DELAY_MAX_SECONDS = 60
SUB_AGENT_DEFAULT_RETRY_DELAY_SECONDS = 5
SUB_AGENT_MAX_STEPS_MIN = 1
SUB_AGENT_MAX_STEPS_MAX = 12
SUB_AGENT_DEFAULT_MAX_STEPS = 6
MAX_PARALLEL_TOOLS_MIN = 1
MAX_PARALLEL_TOOLS_MAX = 12
DEFAULT_MAX_PARALLEL_TOOLS = 4
SUB_AGENT_DEFAULT_MAX_PARALLEL_TOOLS = 2
SUB_AGENT_ALLOWED_TOOL_NAMES = [
    "search_web",
    "fetch_url",
    "fetch_url_summarized",
    "grep_fetched_content",
    "search_news_ddgs",
    "search_news_google",
]
CHAT_SUMMARY_DEFAULT_DETAIL_LEVEL = "balanced"
CHAT_SUMMARY_DETAIL_LEVELS = {"very_concise", "concise", "balanced", "detailed", "comprehensive"}
CONTEXT_SELECTION_ALLOWED_STRATEGIES = {"classic", "entropy", "entropy_rag_hybrid"}
ENTROPY_PROFILE_PRESETS = {"conservative", "balanced", "aggressive"}
CLARIFICATION_QUESTION_LIMIT_MIN = 1
CLARIFICATION_QUESTION_LIMIT_MAX = 25
CLARIFICATION_DEFAULT_MAX_QUESTIONS = 5

WEB_CACHE_TTL_HOURS_MIN = 0
WEB_CACHE_TTL_HOURS_MAX = 168
DEFAULT_WEB_CACHE_TTL_HOURS = 24
OPENROUTER_PROMPT_CACHE_DEFAULT_ENABLED = True

FETCH_TIMEOUT = 20
FETCH_MAX_SIZE = 5 * 1024 * 1024
FETCH_MAX_REDIRECTS = 5
CACHE_TTL_HOURS = DEFAULT_WEB_CACHE_TTL_HOURS
SEARCH_MAX_RESULTS = 5
CONTENT_MAX_CHARS = 100_000
FETCH_SUMMARY_TOKEN_THRESHOLD = max(400, _parse_int_env("FETCH_SUMMARY_TOKEN_THRESHOLD", 3500))
FETCH_SUMMARY_MAX_CHARS = max(2000, min(CONTENT_MAX_CHARS, _parse_int_env("FETCH_SUMMARY_MAX_CHARS", 8000)))
FETCH_SUMMARIZE_MAX_INPUT_CHARS = max(4_000, min(CONTENT_MAX_CHARS, _parse_int_env("FETCH_SUMMARIZE_MAX_INPUT_CHARS", 80_000)))
FETCH_SUMMARIZE_MAX_OUTPUT_TOKENS = max(200, min(4_000, _parse_int_env("FETCH_SUMMARIZE_MAX_OUTPUT_TOKENS", 2400)))
FETCH_SUMMARY_GENERAL_TOP_K = max(1, min(6, _parse_int_env("FETCH_SUMMARY_GENERAL_TOP_K", 3)))
FETCH_SUMMARY_QUERY_TOP_K = max(1, min(8, _parse_int_env("FETCH_SUMMARY_QUERY_TOP_K", 4)))
FETCH_SUMMARY_EXCERPT_MAX_CHARS = max(200, min(1200, _parse_int_env("FETCH_SUMMARY_EXCERPT_MAX_CHARS", 500)))
CHAT_SUMMARY_TRIGGER_TOKEN_COUNT = max(1_000, min(200_000, _parse_int_env("CHAT_SUMMARY_TRIGGER_TOKEN_COUNT", 80_000)))
CHAT_SUMMARY_MODE = (os.getenv("CHAT_SUMMARY_MODE") or "auto").strip().lower()
CHAT_SUMMARY_MODEL = (os.getenv("CHAT_SUMMARY_MODEL") or DEFAULT_CHAT_MODEL).strip() or DEFAULT_CHAT_MODEL
CHAT_SUMMARY_ALLOWED_MODES = {"auto", "conservative", "never", "aggressive"}
PROMPT_MAX_INPUT_TOKENS = max(8_000, min(120_000, _parse_int_env("PROMPT_MAX_INPUT_TOKENS", 100_000)))
PROMPT_RESPONSE_TOKEN_RESERVE = max(1_000, min(32_000, _parse_int_env("PROMPT_RESPONSE_TOKEN_RESERVE", 8_000)))
PROMPT_RECENT_HISTORY_MAX_TOKENS = max(1_000, min(PROMPT_MAX_INPUT_TOKENS, _parse_int_env("PROMPT_RECENT_HISTORY_MAX_TOKENS", 70_000)))
PROMPT_SUMMARY_MAX_TOKENS = max(500, min(PROMPT_MAX_INPUT_TOKENS, _parse_int_env("PROMPT_SUMMARY_MAX_TOKENS", 15_000)))
PROMPT_RAG_MAX_TOKENS = max(0, min(PROMPT_MAX_INPUT_TOKENS, _parse_int_env("PROMPT_RAG_MAX_TOKENS", 6_000)))
PROMPT_RAG_AUTO_MAX_TOKENS = max(
    0,
    min(PROMPT_RAG_MAX_TOKENS, _parse_int_env("PROMPT_RAG_AUTO_MAX_TOKENS", min(3_000, PROMPT_RAG_MAX_TOKENS))),
)
PROMPT_TOOL_TRACE_MAX_TOKENS = max(0, min(PROMPT_MAX_INPUT_TOKENS, _parse_int_env("PROMPT_TOOL_TRACE_MAX_TOKENS", 500)))
PROMPT_TOOL_MEMORY_MAX_TOKENS = max(0, min(PROMPT_MAX_INPUT_TOKENS, _parse_int_env("PROMPT_TOOL_MEMORY_MAX_TOKENS", 1_500)))
PROMPT_PREFLIGHT_SUMMARY_TOKEN_COUNT = max(2_000, min(200_000, _parse_int_env("PROMPT_PREFLIGHT_SUMMARY_TOKEN_COUNT", 90_000)))
CANVAS_PROMPT_DEFAULT_MAX_LINES = max(100, min(3_000, _parse_int_env("CANVAS_PROMPT_DEFAULT_MAX_LINES", 250)))
CANVAS_PROMPT_DEFAULT_MAX_TOKENS = max(500, min(50_000, _parse_int_env("CANVAS_PROMPT_DEFAULT_MAX_TOKENS", 4_000)))
CANVAS_EXPAND_DEFAULT_MAX_LINES = max(100, min(4_000, _parse_int_env("CANVAS_EXPAND_DEFAULT_MAX_LINES", 1_600)))
CANVAS_SCROLL_WINDOW_LINES = max(50, min(800, _parse_int_env("CANVAS_SCROLL_WINDOW_LINES", 200)))
AGENT_CONTEXT_COMPACTION_THRESHOLD = max(0.5, min(0.98, _parse_float_env("AGENT_CONTEXT_COMPACTION_THRESHOLD", 0.85)))
AGENT_CONTEXT_COMPACTION_KEEP_RECENT_ROUNDS = max(
    0,
    min(6, _parse_int_env("AGENT_CONTEXT_COMPACTION_KEEP_RECENT_ROUNDS", 2)),
)
AGENT_TOOL_RESULT_TRANSCRIPT_MAX_CHARS = max(
    8_000,
    min(CONTENT_MAX_CHARS, _parse_int_env("AGENT_TOOL_RESULT_TRANSCRIPT_MAX_CHARS", 16_000)),
)
SUMMARY_SOURCE_TARGET_TOKENS = max(1_000, min(40_000, _parse_int_env("SUMMARY_SOURCE_TARGET_TOKENS", 6_000)))
SUMMARY_RETRY_MIN_SOURCE_TOKENS = max(500, min(SUMMARY_SOURCE_TARGET_TOKENS, _parse_int_env("SUMMARY_RETRY_MIN_SOURCE_TOKENS", 1_500)))

DEFAULT_ACTIVE_TOOL_NAMES = [
    "append_scratchpad",
    "replace_scratchpad",
    "read_scratchpad",
    "save_to_conversation_memory",
    "delete_conversation_memory_entry",
    "ask_clarifying_question",
    "sub_agent",
    "image_explain",
    "search_knowledge_base",
    "search_tool_memory",
    "search_web",
    "fetch_url",
    "fetch_url_summarized",
    "grep_fetched_content",
    "search_news_ddgs",
    "search_news_google",
    "create_canvas_document",
    "expand_canvas_document",
    "batch_read_canvas_documents",
    "scroll_canvas_document",
    "search_canvas_document",
    "validate_canvas_document",
    "rewrite_canvas_document",
    "replace_canvas_lines",
    "insert_canvas_lines",
    "delete_canvas_lines",
    "create_directory",
    "create_file",
    "update_file",
    "read_file",
    "list_dir",
    "search_files",
    "write_project_tree",
    "validate_project_workspace",
]

PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
]

MAX_USER_PREFERENCES_LENGTH = 2000
MAX_AI_PERSONALITY_LENGTH = 2000
MAX_ASSISTANT_BEHAVIOR_LENGTH = MAX_USER_PREFERENCES_LENGTH + MAX_AI_PERSONALITY_LENGTH + 128
MAX_PERSONA_NAME_LENGTH = 80
MAX_PERSONA_COUNT = 50
SCRATCHPAD_DEFAULT_SECTION = "notes"
SCRATCHPAD_SECTION_ORDER = (
    "lessons",
    "profile",
    "notes",
    "problems",
    "tasks",
    "preferences",
    "domain",
)
SCRATCHPAD_SECTION_METADATA = {
    "lessons": {
        "title": "Lessons Learned",
        "description": "Reliable patterns, postmortems, and takeaways that should change future decisions.",
    },
    "profile": {
        "title": "User Profile & Mindset",
        "description": "Durable clues about how the user thinks, decides, and frames problems.",
    },
    "notes": {
        "title": "General Notes",
        "description": "Durable general uncategorized context that does not fit the other sections.",
    },
    "problems": {
        "title": "Open Problems",
        "description": "Recurring or durable unresolved issues worth revisiting across conversations.",
    },
    "tasks": {
        "title": "In-Progress Tasks",
        "description": "Longer-running cross-conversation workstreams the assistant should preserve continuity on.",
    },
    "preferences": {
        "title": "User Preferences",
        "description": "Stable language, formatting, and collaboration preferences.",
    },
    "domain": {
        "title": "Domain Facts",
        "description": "Durable facts about the user's stack, systems, or technical domain.",
    },
}
SCRATCHPAD_SECTION_SETTING_KEYS = {
    section_id: f"scratchpad_{section_id}"
    for section_id in SCRATCHPAD_SECTION_ORDER
}
SCRATCHPAD_ADMIN_EDITING_ENABLED = _parse_bool_env("SCRATCHPAD_ADMIN_EDITING_ENABLED", False)
RAG_ENABLED = _parse_bool_env("RAG_ENABLED", True)
RAG_AUTO_INJECT_TOP_K = max(1, min(8, _parse_int_env("RAG_AUTO_INJECT_TOP_K", 3)))
RAG_SEARCH_DEFAULT_TOP_K = max(1, min(12, _parse_int_env("RAG_SEARCH_DEFAULT_TOP_K", 5)))
RAG_AUTO_INJECT_THRESHOLD = max(0.0, min(1.0, _parse_float_env("RAG_AUTO_INJECT_THRESHOLD", 0.50)))
RAG_SEARCH_MIN_SIMILARITY = max(0.0, min(1.0, _parse_float_env("RAG_SEARCH_MIN_SIMILARITY", 0.35)))
RAG_CHUNK_SIZE = max(300, min(CONTENT_MAX_CHARS, _parse_int_env("RAG_CHUNK_SIZE", 1_800)))
RAG_CHUNK_OVERLAP = max(0, min(RAG_CHUNK_SIZE // 2, _parse_int_env("RAG_CHUNK_OVERLAP", 250)))
RAG_MAX_CHUNKS_PER_SOURCE = max(1, min(4, _parse_int_env("RAG_MAX_CHUNKS_PER_SOURCE", 2)))
RAG_QUERY_EXPANSION_ENABLED = _parse_bool_env("RAG_QUERY_EXPANSION_ENABLED", True)
RAG_QUERY_EXPANSION_MAX_VARIANTS = max(1, min(4, _parse_int_env("RAG_QUERY_EXPANSION_MAX_VARIANTS", 2)))
RAG_TEMPORAL_DECAY_ALPHA = max(0.0, min(1.0, _parse_float_env("RAG_TEMPORAL_DECAY_ALPHA", 0.15)))
RAG_TEMPORAL_DECAY_LAMBDA = max(0.0, min(1.0, _parse_float_env("RAG_TEMPORAL_DECAY_LAMBDA", 0.05)))
RAG_SENSITIVITY_PRESETS = {
    "flexible": 0.25,
    "normal": 0.35,
    "strict": 0.55,
}
RAG_CONTEXT_SIZE_PRESETS = {
    "small": 2,
    "medium": 5,
    "large": 8,
}
RAG_SOURCE_CONVERSATION = "conversation"
RAG_SOURCE_TOOL_RESULT = "tool_result"
RAG_SOURCE_TOOL_MEMORY = "tool_memory"
RAG_SOURCE_UPLOADED_DOCUMENT = "uploaded_document"
RAG_SUPPORTED_SOURCE_TYPES = {
    RAG_SOURCE_CONVERSATION,
    RAG_SOURCE_TOOL_RESULT,
    RAG_SOURCE_TOOL_MEMORY,
    RAG_SOURCE_UPLOADED_DOCUMENT,
}
RAG_SUPPORTED_CATEGORIES = {
    RAG_SOURCE_CONVERSATION,
    RAG_SOURCE_TOOL_RESULT,
    RAG_SOURCE_TOOL_MEMORY,
    RAG_SOURCE_UPLOADED_DOCUMENT,
}
RAG_TOOL_RESULT_MAX_TEXT_CHARS = 12_000
RAG_TOOL_RESULT_SUMMARY_MAX_CHARS = 1_000
FETCH_RAW_TOOL_RESULT_MAX_TEXT_CHARS = max(
    RAG_TOOL_RESULT_MAX_TEXT_CHARS,
    min(CONTENT_MAX_CHARS, _parse_int_env("FETCH_RAW_TOOL_RESULT_MAX_TEXT_CHARS", 24_000)),
)
TOOL_MEMORY_TTL_DEFAULT_SECONDS = max(3_600, _parse_int_env("TOOL_MEMORY_TTL_DEFAULT_SECONDS", 604_800))
TOOL_MEMORY_TTL_WEB_SECONDS = max(3_600, _parse_int_env("TOOL_MEMORY_TTL_WEB_SECONDS", 43_200))
TOOL_MEMORY_TTL_NEWS_SECONDS = max(1_800, _parse_int_env("TOOL_MEMORY_TTL_NEWS_SECONDS", 7_200))
RAG_DISABLED_INGEST_ERROR = (
    "Manual RAG ingestion is disabled. RAG now only indexes conversation history and successful text-like tool results."
)
RAG_DISABLED_FEATURE_ERROR = "RAG is disabled in configuration. Set RAG_ENABLED=true to use it."
OCR_DISABLED_FEATURE_ERROR = "OCR is disabled in configuration. Set OCR_ENABLED=true to use OCR."
IMAGE_UPLOADS_DISABLED_FEATURE_ERROR = (
    "Image uploads are disabled in configuration. Configure OCR_ENABLED=true or a remote model provider to use image uploads."
)


def _nearest_preset_name(value: float, presets: dict[str, float | int], fallback: str) -> str:
    if fallback not in presets:
        raise ValueError("Fallback preset must exist.")
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return fallback
    return min(presets, key=lambda name: abs(float(presets[name]) - numeric_value))


RAG_DEFAULT_SENSITIVITY_PRESET = _nearest_preset_name(
    RAG_AUTO_INJECT_THRESHOLD,
    RAG_SENSITIVITY_PRESETS,
    "normal",
)
RAG_DEFAULT_CONTEXT_SIZE_PRESET = _nearest_preset_name(
    RAG_AUTO_INJECT_TOP_K,
    RAG_CONTEXT_SIZE_PRESETS,
    "medium",
)

DEFAULT_SETTINGS = {
    "user_preferences": "",
    "general_instructions": "",
    "ai_personality": "",
    "default_persona_id": "",
    "scratchpad": "",
    "scratchpad_lessons": "",
    "scratchpad_profile": "",
    "scratchpad_notes": "",
    "scratchpad_problems": "",
    "scratchpad_tasks": "",
    "scratchpad_preferences": "",
    "scratchpad_domain": "",
    "max_steps": "5",
    "max_parallel_tools": str(DEFAULT_MAX_PARALLEL_TOOLS),
    "temperature": "0.7",
    "clarification_max_questions": str(CLARIFICATION_DEFAULT_MAX_QUESTIONS),
    "sub_agent_max_steps": str(SUB_AGENT_DEFAULT_MAX_STEPS),
    "sub_agent_timeout_seconds": str(SUB_AGENT_DEFAULT_TIMEOUT_SECONDS),
    "sub_agent_retry_attempts": str(SUB_AGENT_DEFAULT_RETRY_ATTEMPTS),
    "sub_agent_retry_delay_seconds": str(SUB_AGENT_DEFAULT_RETRY_DELAY_SECONDS),
    "sub_agent_max_parallel_tools": "",
    "sub_agent_allowed_tool_names": json.dumps(SUB_AGENT_ALLOWED_TOOL_NAMES, ensure_ascii=False),
    "web_cache_ttl_hours": str(DEFAULT_WEB_CACHE_TTL_HOURS),
    "openrouter_prompt_cache_enabled": "true" if OPENROUTER_PROMPT_CACHE_DEFAULT_ENABLED else "false",
    "custom_models": "[]",
    "visible_model_order": json.dumps(DEFAULT_VISIBLE_CHAT_MODEL_ORDER, ensure_ascii=False),
    "operation_model_preferences": json.dumps(DEFAULT_OPERATION_MODEL_PREFERENCES, ensure_ascii=False),
    "operation_model_fallback_preferences": json.dumps(DEFAULT_OPERATION_MODEL_FALLBACK_PREFERENCES, ensure_ascii=False),
    "image_processing_method": DEFAULT_IMAGE_PROCESSING_METHOD,
    "image_helper_model": "",
    "active_tools": json.dumps(DEFAULT_ACTIVE_TOOL_NAMES, ensure_ascii=False),
    "proxy_enabled_operations": json.dumps(DEFAULT_PROXY_ENABLED_OPERATIONS, ensure_ascii=False),
    "rag_auto_inject": "true",
    "rag_sensitivity": RAG_DEFAULT_SENSITIVITY_PRESET,
    "rag_context_size": RAG_DEFAULT_CONTEXT_SIZE_PRESET,
    "rag_source_types": json.dumps(
        [
            RAG_SOURCE_CONVERSATION,
            RAG_SOURCE_TOOL_RESULT,
            RAG_SOURCE_TOOL_MEMORY,
            RAG_SOURCE_UPLOADED_DOCUMENT,
        ],
        ensure_ascii=False,
    ),
    "rag_auto_inject_source_types": json.dumps(
        [
            RAG_SOURCE_CONVERSATION,
            RAG_SOURCE_TOOL_RESULT,
            RAG_SOURCE_TOOL_MEMORY,
            RAG_SOURCE_UPLOADED_DOCUMENT,
        ],
        ensure_ascii=False,
    ),
    "tool_memory_auto_inject": "false",
    "fetch_url_token_threshold": str(FETCH_SUMMARY_TOKEN_THRESHOLD),
    "fetch_url_clip_aggressiveness": "50",
    "canvas_prompt_max_lines": str(CANVAS_PROMPT_DEFAULT_MAX_LINES),
    "canvas_prompt_max_tokens": str(CANVAS_PROMPT_DEFAULT_MAX_TOKENS),
    "canvas_expand_max_lines": str(CANVAS_EXPAND_DEFAULT_MAX_LINES),
    "canvas_scroll_window_lines": str(CANVAS_SCROLL_WINDOW_LINES),
    "chat_summary_trigger_token_count": str(CHAT_SUMMARY_TRIGGER_TOKEN_COUNT),
    "chat_summary_mode": CHAT_SUMMARY_MODE if CHAT_SUMMARY_MODE in CHAT_SUMMARY_ALLOWED_MODES else "auto",
    "chat_summary_detail_level": CHAT_SUMMARY_DEFAULT_DETAIL_LEVEL,
    "summary_skip_first": "2",
    "summary_skip_last": "1",
    "context_selection_strategy": "classic",
    "entropy_profile": "balanced",
    "entropy_rag_budget_ratio": "35",
    "entropy_protect_code_blocks": "true",
    "entropy_protect_tool_results": "true",
    "entropy_reference_boost": "true",
    "reasoning_auto_collapse": "false",
    "pruning_enabled": "false",
    "pruning_token_threshold": str(CHAT_SUMMARY_TRIGGER_TOKEN_COUNT),
    "pruning_batch_size": "10",
}


def get_feature_flags() -> dict:
    return {
        "rag_enabled": RAG_ENABLED,
        "ocr_enabled": OCR_ENABLED,
        "conversation_memory_enabled": CONVERSATION_MEMORY_ENABLED,
        "image_uploads_enabled": IMAGE_UPLOADS_ENABLED,
        "youtube_transcripts_enabled": YOUTUBE_TRANSCRIPTS_ENABLED,
        "deepseek_api_configured": bool(DEEPSEEK_API_KEY),
        "openrouter_api_configured": bool(OPENROUTER_API_KEY),
        "remote_image_provider_configured": bool(OPENROUTER_API_KEY or DEEPSEEK_API_KEY),
        "scratchpad_admin_editing": SCRATCHPAD_ADMIN_EDITING_ENABLED,
        "login_pin_enabled": bool(LOGIN_PIN),
    }
