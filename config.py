from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import sqlite3

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

_INSECURE_SECRET_KEY_VALUES = {
    "dev-only-change-me",
    "change-me",
    "replace-me",
    "your-secret-key",
    "secret",
}

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "chatbot.db")
IMAGE_STORAGE_DIR = (os.getenv("IMAGE_STORAGE_DIR") or os.path.join(BASE_DIR, "data", "images")).strip()
PROJECT_WORKSPACE_ROOT = (os.getenv("PROJECT_WORKSPACE_ROOT") or os.path.join(BASE_DIR, "data", "workspaces")).strip()
PROXIES_PATH = os.path.join(BASE_DIR, "proxies.txt")
AGENT_TRACE_LOG_PATH = (os.getenv("AGENT_TRACE_LOG_PATH") or os.path.join(BASE_DIR, "logs", "agent-trace.log")).strip()


def _hash_sensitive_value(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def hash_login_pin_value(value: str) -> str:
    return _hash_sensitive_value(value)


def _read_secret_key() -> str:
    secret_value = (os.getenv("FLASK_SECRET_KEY") or os.getenv("SECRET_KEY") or "").strip()
    if not secret_value or secret_value.lower() in _INSECURE_SECRET_KEY_VALUES:
        raise RuntimeError(
            "FLASK_SECRET_KEY must be configured with a strong non-default value. "
            "Set it in .env or the environment before starting the app."
        )
    return secret_value


SECRET_KEY = _read_secret_key()
_login_pin_env = (os.getenv("LOGIN_PIN") or "").strip()
LOGIN_PIN_HASH = _hash_sensitive_value(_login_pin_env) if _login_pin_env else ""
LOGIN_PIN = None
del _login_pin_env
DEEPSEEK_API_KEY = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
OPENROUTER_API_KEY = (os.getenv("OPENROUTER_API_KEY") or "").strip()
MINIMAX_API_KEY = (os.getenv("MINIMAX_API_KEY") or "").strip()
OPENROUTER_HTTP_REFERER = (os.getenv("OPENROUTER_HTTP_REFERER") or os.getenv("OPENROUTER_SITE_URL") or "").strip()
OPENROUTER_APP_TITLE = (os.getenv("OPENROUTER_APP_TITLE") or os.getenv("OPENROUTER_X_TITLE") or "").strip()

AVAILABLE_MODELS = [{"id": model["id"], "name": model["name"]} for model in BUILTIN_MODELS]
AVAILABLE_MODEL_IDS = set(BUILTIN_MODEL_IDS)


def get_login_pin_hash() -> str:
    raw_override = globals().get("LOGIN_PIN")
    if raw_override is not None:
        raw_value = str(raw_override or "").strip()
        return _hash_sensitive_value(raw_value) if raw_value else ""
    return str(globals().get("LOGIN_PIN_HASH") or "").strip()


def is_login_pin_configured() -> bool:
    return bool(get_login_pin_hash())


def _coerce_bool(value, default: bool) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _coerce_int(value, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        normalized = int(default)
    if minimum is not None:
        normalized = max(int(minimum), normalized)
    if maximum is not None:
        normalized = min(int(maximum), normalized)
    return normalized


def _coerce_float(value, default: float, minimum: float | None = None, maximum: float | None = None) -> float:
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        normalized = float(default)
    if minimum is not None:
        normalized = max(float(minimum), normalized)
    if maximum is not None:
        normalized = min(float(maximum), normalized)
    return normalized


def _parse_int_env(name: str, default: int) -> int:
    return _coerce_int(os.getenv(name), default)


def _parse_bool_env(name: str, default: bool) -> bool:
    return _coerce_bool(os.getenv(name), default)


def _parse_float_env(name: str, default: float) -> float:
    return _coerce_float(os.getenv(name), default)


AGENT_TRACE_LOG_ENABLED = _parse_bool_env("AGENT_TRACE_LOG_ENABLED", True)
AGENT_TRACE_LOG_INCLUDE_RAW = _parse_bool_env("AGENT_TRACE_LOG_INCLUDE_RAW", True)

# Centralized application logging
APP_LOG_ENABLED = _parse_bool_env("APP_LOG_ENABLED", True)
APP_LOG_LEVEL = (os.getenv("APP_LOG_LEVEL") or "INFO").strip().upper()
APP_LOG_PATH = (os.getenv("APP_LOG_PATH") or os.path.join(BASE_DIR, "logs", "app.log")).strip()
APP_LOG_MAX_BYTES = max(1024, _parse_int_env("APP_LOG_MAX_BYTES", 2_000_000))
APP_LOG_BACKUP_COUNT = max(1, _parse_int_env("APP_LOG_BACKUP_COUNT", 5))
APP_LOG_CONSOLE_ENABLED = _parse_bool_env("APP_LOG_CONSOLE_ENABLED", False)


LOGIN_SESSION_TIMEOUT_MINUTES = max(1, _parse_int_env("LOGIN_SESSION_TIMEOUT_MINUTES", 30))
LOGIN_MAX_FAILED_ATTEMPTS = max(1, _parse_int_env("LOGIN_MAX_FAILED_ATTEMPTS", 3))
LOGIN_LOCKOUT_SECONDS = max(1, _parse_int_env("LOGIN_LOCKOUT_SECONDS", 300))
LOGIN_REMEMBER_SESSION_DAYS = max(1, _parse_int_env("LOGIN_REMEMBER_SESSION_DAYS", 30))
TRUST_PROXY_HEADERS = _parse_bool_env("TRUST_PROXY_HEADERS", False)
FORCE_HTTPS = _parse_bool_env("FORCE_HTTPS", False)
SESSION_COOKIE_SECURE = _parse_bool_env("SESSION_COOKIE_SECURE", FORCE_HTTPS)
_preferred_url_scheme = (os.getenv("PREFERRED_URL_SCHEME") or ("https" if FORCE_HTTPS else "http")).strip().lower()
PREFERRED_URL_SCHEME = _preferred_url_scheme if _preferred_url_scheme in {"http", "https"} else "http"
SECURITY_HSTS_ENABLED = _parse_bool_env("SECURITY_HSTS_ENABLED", False)
SECURITY_HSTS_MAX_AGE = max(0, _parse_int_env("SECURITY_HSTS_MAX_AGE", 31_536_000))
SECURITY_HSTS_INCLUDE_SUBDOMAINS = _parse_bool_env("SECURITY_HSTS_INCLUDE_SUBDOMAINS", True)
SECURITY_HSTS_PRELOAD = _parse_bool_env("SECURITY_HSTS_PRELOAD", False)
SECURITY_RATE_LIMIT_REDIS_ENABLED = _parse_bool_env("SECURITY_RATE_LIMIT_REDIS_ENABLED", False)
SECURITY_RATE_LIMIT_REDIS_URL = (os.getenv("SECURITY_RATE_LIMIT_REDIS_URL") or "").strip()


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
    "scroll_fetched_content",
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
SEARCH_TOOL_QUERY_LIMIT_MIN = 1
SEARCH_TOOL_QUERY_LIMIT_MAX = 20
DEFAULT_SEARCH_TOOL_QUERY_LIMIT = 5

WEB_CACHE_TTL_HOURS_MIN = 0
WEB_CACHE_TTL_HOURS_MAX = 168
DEFAULT_WEB_CACHE_TTL_HOURS = 24
OPENROUTER_PROMPT_CACHE_DEFAULT_ENABLED = True
OPENROUTER_ANTHROPIC_CACHE_TTL_DEFAULT = "5m"  # "5m" (ephemeral, 5 min) or "1h" (ephemeral, 1 hour)

FETCH_TIMEOUT = 20
FETCH_MAX_SIZE = 5 * 1024 * 1024
FETCH_MAX_REDIRECTS = 5
FETCH_HTML_CONVERTER_MODES = {"internal", "external", "hybrid"}
CACHE_TTL_HOURS = DEFAULT_WEB_CACHE_TTL_HOURS
SEARCH_MAX_RESULTS = 5
CONTENT_MAX_CHARS = 100_000
FETCH_SUMMARY_TOKEN_THRESHOLD = max(400, _parse_int_env("FETCH_SUMMARY_TOKEN_THRESHOLD", 3500))
FETCH_SUMMARY_MAX_CHARS = max(2000, min(CONTENT_MAX_CHARS, _parse_int_env("FETCH_SUMMARY_MAX_CHARS", 8000)))
FETCH_SUMMARIZE_MAX_INPUT_CHARS = max(
    4_000, min(CONTENT_MAX_CHARS, _parse_int_env("FETCH_SUMMARIZE_MAX_INPUT_CHARS", 80_000))
)
FETCH_SUMMARIZE_MAX_OUTPUT_TOKENS = max(200, min(4_000, _parse_int_env("FETCH_SUMMARIZE_MAX_OUTPUT_TOKENS", 2400)))
FETCH_SUMMARY_GENERAL_TOP_K = max(1, min(6, _parse_int_env("FETCH_SUMMARY_GENERAL_TOP_K", 3)))
FETCH_SUMMARY_QUERY_TOP_K = max(1, min(8, _parse_int_env("FETCH_SUMMARY_QUERY_TOP_K", 4)))
FETCH_SUMMARY_EXCERPT_MAX_CHARS = max(200, min(1200, _parse_int_env("FETCH_SUMMARY_EXCERPT_MAX_CHARS", 500)))
CHAT_SUMMARY_TRIGGER_TOKEN_COUNT = max(1_000, min(200_000, _parse_int_env("CHAT_SUMMARY_TRIGGER_TOKEN_COUNT", 120_000)))
CHAT_SUMMARY_MODE = (os.getenv("CHAT_SUMMARY_MODE") or "auto").strip().lower()
CHAT_SUMMARY_MODEL = (os.getenv("CHAT_SUMMARY_MODEL") or DEFAULT_CHAT_MODEL).strip() or DEFAULT_CHAT_MODEL
CHAT_SUMMARY_ALLOWED_MODES = {"auto", "conservative", "never", "aggressive"}
SUMMARY_RETRY_REDUCTION_FACTOR = max(0.5, min(0.95, _parse_float_env("SUMMARY_RETRY_REDUCTION_FACTOR", 0.80)))
PROMPT_MAX_INPUT_TOKENS = max(8_000, min(120_000, _parse_int_env("PROMPT_MAX_INPUT_TOKENS", 100_000)))
PROMPT_RESPONSE_TOKEN_RESERVE = max(1_000, min(32_000, _parse_int_env("PROMPT_RESPONSE_TOKEN_RESERVE", 8_000)))
PROMPT_RECENT_HISTORY_MAX_TOKENS = max(
    1_000, min(PROMPT_MAX_INPUT_TOKENS, _parse_int_env("PROMPT_RECENT_HISTORY_MAX_TOKENS", 90_000))
)
PROMPT_SUMMARY_MAX_TOKENS = max(500, min(PROMPT_MAX_INPUT_TOKENS, _parse_int_env("PROMPT_SUMMARY_MAX_TOKENS", 15_000)))
PROMPT_RAG_MAX_TOKENS = max(0, min(PROMPT_MAX_INPUT_TOKENS, _parse_int_env("PROMPT_RAG_MAX_TOKENS", 6_000)))
PROMPT_RAG_AUTO_MAX_TOKENS = max(
    0,
    min(PROMPT_RAG_MAX_TOKENS, _parse_int_env("PROMPT_RAG_AUTO_MAX_TOKENS", min(3_000, PROMPT_RAG_MAX_TOKENS))),
)
PROMPT_TOOL_TRACE_MAX_TOKENS = max(
    0, min(PROMPT_MAX_INPUT_TOKENS, _parse_int_env("PROMPT_TOOL_TRACE_MAX_TOKENS", 2_000))
)
PROMPT_TOOL_MEMORY_MAX_TOKENS = max(
    0, min(PROMPT_MAX_INPUT_TOKENS, _parse_int_env("PROMPT_TOOL_MEMORY_MAX_TOKENS", 3_000))
)
PROMPT_PREFLIGHT_SUMMARY_TOKEN_COUNT = max(
    2_000, min(200_000, _parse_int_env("PROMPT_PREFLIGHT_SUMMARY_TOKEN_COUNT", 110_000))
)
CANVAS_PROMPT_DEFAULT_MAX_LINES = max(100, min(3_000, _parse_int_env("CANVAS_PROMPT_DEFAULT_MAX_LINES", 250)))
CANVAS_PROMPT_DEFAULT_MAX_TOKENS = max(500, min(50_000, _parse_int_env("CANVAS_PROMPT_DEFAULT_MAX_TOKENS", 4_000)))
CANVAS_PROMPT_DEFAULT_MAX_CHARS = max(1_000, min(200_000, _parse_int_env("CANVAS_PROMPT_DEFAULT_MAX_CHARS", 20_000)))
CANVAS_PROMPT_CODE_LINE_MAX_CHARS = max(40, min(1_000, _parse_int_env("CANVAS_PROMPT_CODE_LINE_MAX_CHARS", 180)))
CANVAS_PROMPT_TEXT_LINE_MAX_CHARS = max(40, min(1_000, _parse_int_env("CANVAS_PROMPT_TEXT_LINE_MAX_CHARS", 100)))
CANVAS_EXPAND_DEFAULT_MAX_LINES = max(100, min(4_000, _parse_int_env("CANVAS_EXPAND_DEFAULT_MAX_LINES", 1_600)))
CANVAS_SCROLL_WINDOW_LINES = max(50, min(800, _parse_int_env("CANVAS_SCROLL_WINDOW_LINES", 200)))
AGENT_CONTEXT_COMPACTION_THRESHOLD = max(0.5, min(0.98, _parse_float_env("AGENT_CONTEXT_COMPACTION_THRESHOLD", 0.85)))
AGENT_CONTEXT_COMPACTION_KEEP_RECENT_ROUNDS = max(
    0,
    min(6, _parse_int_env("AGENT_CONTEXT_COMPACTION_KEEP_RECENT_ROUNDS", 2)),
)
PRUNING_TARGET_REDUCTION_RATIO = max(0.1, min(0.9, _parse_float_env("PRUNING_TARGET_REDUCTION_RATIO", 0.65)))
PRUNING_MIN_TARGET_TOKENS = max(50, min(5_000, _parse_int_env("PRUNING_MIN_TARGET_TOKENS", 160)))
PRUNE_WEIGHT_ENTROPY = max(0.0, min(1.0, _parse_float_env("PRUNE_WEIGHT_ENTROPY", 0.35)))
PRUNE_WEIGHT_RAG = max(0.0, min(1.0, _parse_float_env("PRUNE_WEIGHT_RAG", 0.30)))
PRUNE_WEIGHT_STALENESS = max(0.0, min(1.0, _parse_float_env("PRUNE_WEIGHT_STALENESS", 0.25)))
PRUNE_WEIGHT_TOKEN = max(0.0, min(1.0, _parse_float_env("PRUNE_WEIGHT_TOKEN", 0.10)))
AGENT_TOOL_RESULT_TRANSCRIPT_MAX_CHARS = max(
    8_000,
    min(CONTENT_MAX_CHARS, _parse_int_env("AGENT_TOOL_RESULT_TRANSCRIPT_MAX_CHARS", 16_000)),
)
SUMMARY_SOURCE_TARGET_TOKENS = max(1_000, min(40_000, _parse_int_env("SUMMARY_SOURCE_TARGET_TOKENS", 6_000)))
SUMMARY_RETRY_MIN_SOURCE_TOKENS = max(
    500, min(SUMMARY_SOURCE_TARGET_TOKENS, _parse_int_env("SUMMARY_RETRY_MIN_SOURCE_TOKENS", 1_500))
)

DEFAULT_ACTIVE_TOOL_NAMES = [
    "append_scratchpad",
    "replace_scratchpad",
    "read_scratchpad",
    "save_to_conversation_memory",
    "delete_conversation_memory_entry",
    "save_to_persona_memory",
    "delete_persona_memory_entry",
    "delete_tool_result",
    "list_tool_memory",
    "ask_clarifying_question",
    "sub_agent",
    "image_explain",
    "transcribe_youtube_video",
    "search_knowledge_base",
    "search_web",
    "fetch_url",
    "fetch_url_summarized",
    "scroll_fetched_content",
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
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
]

MAX_USER_PREFERENCES_LENGTH = 100_000
MAX_AI_PERSONALITY_LENGTH = 100_000
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
SCRATCHPAD_SECTION_SETTING_KEYS = {section_id: f"scratchpad_{section_id}" for section_id in SCRATCHPAD_SECTION_ORDER}
SCRATCHPAD_ADMIN_EDITING_ENABLED = _parse_bool_env("SCRATCHPAD_ADMIN_EDITING_ENABLED", False)
RAG_ENABLED = _parse_bool_env("RAG_ENABLED", True)
LOW_RESOURCE_MODE = _parse_bool_env("LOW_RESOURCE_MODE", False)
RAG_AUTO_INJECT_TOP_K = max(1, min(8, _parse_int_env("RAG_AUTO_INJECT_TOP_K", 2 if LOW_RESOURCE_MODE else 3)))
RAG_SEARCH_DEFAULT_TOP_K = max(1, min(12, _parse_int_env("RAG_SEARCH_DEFAULT_TOP_K", 5)))
RAG_AUTO_INJECT_THRESHOLD = max(0.0, min(1.0, _parse_float_env("RAG_AUTO_INJECT_THRESHOLD", 0.50)))
RAG_SEARCH_MIN_SIMILARITY = max(0.0, min(1.0, _parse_float_env("RAG_SEARCH_MIN_SIMILARITY", 0.35)))
RAG_CHUNK_SIZE = max(300, min(CONTENT_MAX_CHARS, _parse_int_env("RAG_CHUNK_SIZE", 1_800)))
RAG_CHUNK_OVERLAP = max(0, min(RAG_CHUNK_SIZE // 2, _parse_int_env("RAG_CHUNK_OVERLAP", 250)))
RAG_MAX_CHUNKS_PER_SOURCE = max(1, min(4, _parse_int_env("RAG_MAX_CHUNKS_PER_SOURCE", 2)))
RAG_QUERY_EXPANSION_ENABLED = _parse_bool_env("RAG_QUERY_EXPANSION_ENABLED", True)
RAG_QUERY_EXPANSION_MAX_VARIANTS = max(
    1, min(4, _parse_int_env("RAG_QUERY_EXPANSION_MAX_VARIANTS", 1 if LOW_RESOURCE_MODE else 2))
)
RAG_TEMPORAL_DECAY_ALPHA = max(0.0, min(1.0, _parse_float_env("RAG_TEMPORAL_DECAY_ALPHA", 0.15)))
RAG_TEMPORAL_DECAY_LAMBDA = max(0.0, min(1.0, _parse_float_env("RAG_TEMPORAL_DECAY_LAMBDA", 0.05)))
RAG_EMBED_MODEL = (os.getenv("RAG_EMBED_MODEL") or os.getenv("BGE_M3_MODEL_PATH") or "BAAI/bge-m3").strip()
RAG_EMBED_BATCH_SIZE = max(1, _parse_int_env("RAG_EMBED_BATCH_SIZE", _parse_int_env("BGE_M3_BATCH_SIZE", 32)))
RAG_EMBED_CACHE_ENABLED = _parse_bool_env("RAG_EMBED_CACHE_ENABLED", True)
RAG_EMBED_CACHE_MAX_ENTRIES = max(100, _parse_int_env("RAG_EMBED_CACHE_MAX_ENTRIES", 2000))
RAG_QUERY_PARALLEL_COLLECTIONS = _parse_bool_env("RAG_QUERY_PARALLEL_COLLECTIONS", True)
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
TOOL_MEMORY_ENABLED = _parse_bool_env("TOOL_MEMORY_ENABLED", True)
TOOL_MEMORY_MAX_ENTRIES = max(100, _parse_int_env("TOOL_MEMORY_MAX_ENTRIES", 500))
FORCE_MEMORY_CLEANUP_AT_PERCENT = max(0.5, min(0.98, _parse_float_env("FORCE_MEMORY_CLEANUP_AT_PERCENT", 0.85)))
MEMORY_CLEANUP_MIN_TOOL_RESULTS = max(1, _parse_int_env("MEMORY_CLEANUP_MIN_TOOL_RESULTS", 3))
RAG_DISABLED_INGEST_ERROR = (
    "Manual RAG ingestion is disabled. RAG now only indexes conversation history and successful text-like tool results."
)
RAG_DISABLED_FEATURE_ERROR = "RAG is disabled in configuration. Set RAG_ENABLED=true to use it."
OCR_DISABLED_FEATURE_ERROR = "OCR is disabled in configuration. Set OCR_ENABLED=true to use OCR."
IMAGE_UPLOADS_DISABLED_FEATURE_ERROR = "Image uploads are disabled in configuration. Configure OCR_ENABLED=true or a remote model provider to use image uploads."


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


def _runtime_setting_bool(value, default: bool) -> bool:
    return _coerce_bool(value, default)


def _runtime_setting_int(value, default: int, minimum: int, maximum: int) -> int:
    return _coerce_int(value, default, minimum, maximum)


def _runtime_setting_float(value, default: float, minimum: float, maximum: float) -> float:
    return _coerce_float(value, default, minimum, maximum)


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
    "search_tool_query_limit": str(DEFAULT_SEARCH_TOOL_QUERY_LIMIT),
    "sub_agent_max_steps": str(SUB_AGENT_DEFAULT_MAX_STEPS),
    "sub_agent_timeout_seconds": str(SUB_AGENT_DEFAULT_TIMEOUT_SECONDS),
    "sub_agent_retry_attempts": str(SUB_AGENT_DEFAULT_RETRY_ATTEMPTS),
    "sub_agent_retry_delay_seconds": str(SUB_AGENT_DEFAULT_RETRY_DELAY_SECONDS),
    "sub_agent_max_parallel_tools": "",
    "sub_agent_allowed_tool_names": json.dumps(SUB_AGENT_ALLOWED_TOOL_NAMES, ensure_ascii=False),
    "sub_agent_canvas_auto_save": "true",
    "sub_agent_canvas_auto_open": "false",
    "web_cache_ttl_hours": str(DEFAULT_WEB_CACHE_TTL_HOURS),
    "activity_enabled": "true",
    "activity_retention_days": "30",
    "openrouter_prompt_cache_enabled": "true" if OPENROUTER_PROMPT_CACHE_DEFAULT_ENABLED else "false",
    "openrouter_anthropic_cache_ttl": OPENROUTER_ANTHROPIC_CACHE_TTL_DEFAULT,
    "openrouter_http_referer": OPENROUTER_HTTP_REFERER,
    "openrouter_app_title": OPENROUTER_APP_TITLE,
    "login_session_timeout_minutes": str(LOGIN_SESSION_TIMEOUT_MINUTES),
    "login_max_failed_attempts": str(LOGIN_MAX_FAILED_ATTEMPTS),
    "login_lockout_seconds": str(LOGIN_LOCKOUT_SECONDS),
    "login_remember_session_days": str(LOGIN_REMEMBER_SESSION_DAYS),
    "custom_models": "[]",
    "visible_model_order": json.dumps(DEFAULT_VISIBLE_CHAT_MODEL_ORDER, ensure_ascii=False),
    "operation_model_preferences": json.dumps(DEFAULT_OPERATION_MODEL_PREFERENCES, ensure_ascii=False),
    "operation_model_fallback_preferences": json.dumps(
        DEFAULT_OPERATION_MODEL_FALLBACK_PREFERENCES, ensure_ascii=False
    ),
    "image_processing_method": DEFAULT_IMAGE_PROCESSING_METHOD,
    "image_helper_model": "",
    "conversation_memory_enabled": "true" if CONVERSATION_MEMORY_ENABLED else "false",
    "ocr_enabled": "true" if OCR_ENABLED else "false",
    "ocr_provider": OCR_PROVIDER,
    "rag_enabled": "true" if RAG_ENABLED else "false",
    "youtube_transcripts_enabled": "true" if YOUTUBE_TRANSCRIPTS_ENABLED else "false",
    "youtube_transcript_model_size": YOUTUBE_TRANSCRIPT_MODEL_SIZE,
    "youtube_transcript_language": YOUTUBE_TRANSCRIPT_DEFAULT_LANGUAGE,
    "active_tools": json.dumps(DEFAULT_ACTIVE_TOOL_NAMES, ensure_ascii=False),
    "proxy_enabled_operations": json.dumps(DEFAULT_PROXY_ENABLED_OPERATIONS, ensure_ascii=False),
    "rag_auto_inject": "true",
    "rag_sensitivity": RAG_DEFAULT_SENSITIVITY_PRESET,
    "rag_context_size": RAG_DEFAULT_CONTEXT_SIZE_PRESET,
    "chat_summary_model": CHAT_SUMMARY_MODEL,
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
    "fetch_html_converter_mode": "hybrid",
    "fetch_url_summarized_max_input_chars": str(FETCH_SUMMARIZE_MAX_INPUT_CHARS),
    "fetch_url_summarized_max_output_tokens": str(FETCH_SUMMARIZE_MAX_OUTPUT_TOKENS),
    "fetch_raw_max_text_chars": str(FETCH_RAW_TOOL_RESULT_MAX_TEXT_CHARS),
    "fetch_summary_max_chars": str(FETCH_SUMMARY_MAX_CHARS),
    "rag_chunk_size": str(RAG_CHUNK_SIZE),
    "rag_chunk_overlap": str(RAG_CHUNK_OVERLAP),
    "rag_max_chunks_per_source": str(RAG_MAX_CHUNKS_PER_SOURCE),
    "rag_search_top_k": str(RAG_SEARCH_DEFAULT_TOP_K),
    "rag_search_min_similarity": str(RAG_SEARCH_MIN_SIMILARITY),
    "rag_query_expansion_enabled": "true" if RAG_QUERY_EXPANSION_ENABLED else "false",
    "rag_query_expansion_max_variants": str(RAG_QUERY_EXPANSION_MAX_VARIANTS),
    "prompt_max_input_tokens": str(PROMPT_MAX_INPUT_TOKENS),
    "prompt_response_token_reserve": str(PROMPT_RESPONSE_TOKEN_RESERVE),
    "prompt_recent_history_max_tokens": str(PROMPT_RECENT_HISTORY_MAX_TOKENS),
    "prompt_summary_max_tokens": str(PROMPT_SUMMARY_MAX_TOKENS),
    "prompt_preflight_summary_token_count": str(PROMPT_PREFLIGHT_SUMMARY_TOKEN_COUNT),
    "prompt_rag_max_tokens": str(PROMPT_RAG_MAX_TOKENS),
    "prompt_tool_memory_max_tokens": str(PROMPT_TOOL_MEMORY_MAX_TOKENS),
    "prompt_tool_trace_max_tokens": str(PROMPT_TOOL_TRACE_MAX_TOKENS),
    "summary_source_target_tokens": str(SUMMARY_SOURCE_TARGET_TOKENS),
    "summary_retry_min_source_tokens": str(SUMMARY_RETRY_MIN_SOURCE_TOKENS),
    "canvas_prompt_max_lines": str(CANVAS_PROMPT_DEFAULT_MAX_LINES),
    "canvas_prompt_max_tokens": str(CANVAS_PROMPT_DEFAULT_MAX_TOKENS),
    "canvas_prompt_max_chars": str(CANVAS_PROMPT_DEFAULT_MAX_CHARS),
    "canvas_prompt_code_line_max_chars": str(CANVAS_PROMPT_CODE_LINE_MAX_CHARS),
    "canvas_prompt_text_line_max_chars": str(CANVAS_PROMPT_TEXT_LINE_MAX_CHARS),
    "canvas_expand_max_lines": str(CANVAS_EXPAND_DEFAULT_MAX_LINES),
    "canvas_scroll_window_lines": str(CANVAS_SCROLL_WINDOW_LINES),
    "chat_summary_trigger_token_count": str(CHAT_SUMMARY_TRIGGER_TOKEN_COUNT),
    "chat_summary_mode": CHAT_SUMMARY_MODE if CHAT_SUMMARY_MODE in CHAT_SUMMARY_ALLOWED_MODES else "auto",
    "chat_summary_detail_level": CHAT_SUMMARY_DEFAULT_DETAIL_LEVEL,
    "summary_skip_first": "2",
    "summary_skip_last": "1",
    "context_compaction_threshold": str(AGENT_CONTEXT_COMPACTION_THRESHOLD),
    "context_compaction_keep_recent_rounds": str(AGENT_CONTEXT_COMPACTION_KEEP_RECENT_ROUNDS),
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
    "pruning_target_reduction_ratio": str(PRUNING_TARGET_REDUCTION_RATIO),
    "pruning_min_target_tokens": str(PRUNING_MIN_TARGET_TOKENS),
    "tool_memory_ttl_default_seconds": str(TOOL_MEMORY_TTL_DEFAULT_SECONDS),
    "tool_memory_ttl_web_seconds": str(TOOL_MEMORY_TTL_WEB_SECONDS),
    "tool_memory_ttl_news_seconds": str(TOOL_MEMORY_TTL_NEWS_SECONDS),
}


_RUNTIME_BASE_VALUES = {
    "OPENROUTER_HTTP_REFERER": OPENROUTER_HTTP_REFERER,
    "OPENROUTER_APP_TITLE": OPENROUTER_APP_TITLE,
    "LOGIN_SESSION_TIMEOUT_MINUTES": LOGIN_SESSION_TIMEOUT_MINUTES,
    "LOGIN_MAX_FAILED_ATTEMPTS": LOGIN_MAX_FAILED_ATTEMPTS,
    "LOGIN_LOCKOUT_SECONDS": LOGIN_LOCKOUT_SECONDS,
    "LOGIN_REMEMBER_SESSION_DAYS": LOGIN_REMEMBER_SESSION_DAYS,
    "CONVERSATION_MEMORY_ENABLED": CONVERSATION_MEMORY_ENABLED,
    "OCR_ENABLED": OCR_ENABLED,
    "OCR_PROVIDER": OCR_PROVIDER,
    "IMAGE_UPLOADS_ENABLED": IMAGE_UPLOADS_ENABLED,
    "YOUTUBE_TRANSCRIPTS_ENABLED": YOUTUBE_TRANSCRIPTS_ENABLED,
    "YOUTUBE_TRANSCRIPT_MODEL_SIZE": YOUTUBE_TRANSCRIPT_MODEL_SIZE,
    "YOUTUBE_TRANSCRIPT_DEFAULT_LANGUAGE": YOUTUBE_TRANSCRIPT_DEFAULT_LANGUAGE,
    "RAG_ENABLED": RAG_ENABLED,
    "CHAT_SUMMARY_MODEL": CHAT_SUMMARY_MODEL,
    "RAG_CHUNK_SIZE": RAG_CHUNK_SIZE,
    "RAG_CHUNK_OVERLAP": RAG_CHUNK_OVERLAP,
    "RAG_MAX_CHUNKS_PER_SOURCE": RAG_MAX_CHUNKS_PER_SOURCE,
    "RAG_SEARCH_DEFAULT_TOP_K": RAG_SEARCH_DEFAULT_TOP_K,
    "RAG_SEARCH_MIN_SIMILARITY": RAG_SEARCH_MIN_SIMILARITY,
    "RAG_QUERY_EXPANSION_ENABLED": RAG_QUERY_EXPANSION_ENABLED,
    "RAG_QUERY_EXPANSION_MAX_VARIANTS": RAG_QUERY_EXPANSION_MAX_VARIANTS,
    "TOOL_MEMORY_TTL_DEFAULT_SECONDS": TOOL_MEMORY_TTL_DEFAULT_SECONDS,
    "TOOL_MEMORY_TTL_WEB_SECONDS": TOOL_MEMORY_TTL_WEB_SECONDS,
    "TOOL_MEMORY_TTL_NEWS_SECONDS": TOOL_MEMORY_TTL_NEWS_SECONDS,
    "FETCH_RAW_TOOL_RESULT_MAX_TEXT_CHARS": FETCH_RAW_TOOL_RESULT_MAX_TEXT_CHARS,
    "FETCH_SUMMARY_MAX_CHARS": FETCH_SUMMARY_MAX_CHARS,
}


def _read_persisted_runtime_settings(database_path: str | None = None) -> dict[str, str]:
    resolved_database_path = str(database_path or DB_PATH or "").strip()
    if not resolved_database_path or not os.path.exists(resolved_database_path):
        return {}

    try:
        with sqlite3.connect(resolved_database_path, timeout=1) as conn:
            rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
    except sqlite3.Error:
        return {}

    return {str(key or ""): str(value or "") for key, value in rows if str(key or "").strip()}


def apply_persisted_runtime_settings(database_path: str | None = None) -> dict[str, str]:
    persisted = _read_persisted_runtime_settings(database_path)

    global OPENROUTER_HTTP_REFERER
    global OPENROUTER_APP_TITLE
    global LOGIN_SESSION_TIMEOUT_MINUTES
    global LOGIN_MAX_FAILED_ATTEMPTS
    global LOGIN_LOCKOUT_SECONDS
    global LOGIN_REMEMBER_SESSION_DAYS
    global CONVERSATION_MEMORY_ENABLED
    global OCR_ENABLED
    global OCR_PROVIDER
    global IMAGE_UPLOADS_ENABLED
    global YOUTUBE_TRANSCRIPTS_ENABLED
    global YOUTUBE_TRANSCRIPT_MODEL_SIZE
    global YOUTUBE_TRANSCRIPT_DEFAULT_LANGUAGE
    global RAG_ENABLED
    global CHAT_SUMMARY_MODEL
    global RAG_CHUNK_SIZE
    global RAG_CHUNK_OVERLAP
    global RAG_MAX_CHUNKS_PER_SOURCE
    global RAG_SEARCH_DEFAULT_TOP_K
    global RAG_SEARCH_MIN_SIMILARITY
    global RAG_QUERY_EXPANSION_ENABLED
    global RAG_QUERY_EXPANSION_MAX_VARIANTS
    global TOOL_MEMORY_TTL_DEFAULT_SECONDS
    global TOOL_MEMORY_TTL_WEB_SECONDS
    global TOOL_MEMORY_TTL_NEWS_SECONDS
    global FETCH_RAW_TOOL_RESULT_MAX_TEXT_CHARS
    global FETCH_SUMMARY_MAX_CHARS

    OPENROUTER_HTTP_REFERER = str(
        persisted.get("openrouter_http_referer", _RUNTIME_BASE_VALUES["OPENROUTER_HTTP_REFERER"]) or ""
    ).strip()
    OPENROUTER_APP_TITLE = str(
        persisted.get("openrouter_app_title", _RUNTIME_BASE_VALUES["OPENROUTER_APP_TITLE"]) or ""
    ).strip()
    LOGIN_SESSION_TIMEOUT_MINUTES = _runtime_setting_int(
        persisted.get("login_session_timeout_minutes"),
        _RUNTIME_BASE_VALUES["LOGIN_SESSION_TIMEOUT_MINUTES"],
        1,
        10_080,
    )
    LOGIN_MAX_FAILED_ATTEMPTS = _runtime_setting_int(
        persisted.get("login_max_failed_attempts"),
        _RUNTIME_BASE_VALUES["LOGIN_MAX_FAILED_ATTEMPTS"],
        1,
        50,
    )
    LOGIN_LOCKOUT_SECONDS = _runtime_setting_int(
        persisted.get("login_lockout_seconds"),
        _RUNTIME_BASE_VALUES["LOGIN_LOCKOUT_SECONDS"],
        1,
        86_400,
    )
    LOGIN_REMEMBER_SESSION_DAYS = _runtime_setting_int(
        persisted.get("login_remember_session_days"),
        _RUNTIME_BASE_VALUES["LOGIN_REMEMBER_SESSION_DAYS"],
        1,
        3_650,
    )
    CONVERSATION_MEMORY_ENABLED = _runtime_setting_bool(
        persisted.get("conversation_memory_enabled"),
        _RUNTIME_BASE_VALUES["CONVERSATION_MEMORY_ENABLED"],
    )
    OCR_ENABLED = _runtime_setting_bool(persisted.get("ocr_enabled"), _RUNTIME_BASE_VALUES["OCR_ENABLED"])
    normalized_ocr_provider = (
        str(persisted.get("ocr_provider", _RUNTIME_BASE_VALUES["OCR_PROVIDER"]) or "").strip().lower()
    )
    if normalized_ocr_provider in OCR_SUPPORTED_PROVIDERS:
        OCR_PROVIDER = normalized_ocr_provider
    YOUTUBE_TRANSCRIPTS_ENABLED = _runtime_setting_bool(
        persisted.get("youtube_transcripts_enabled"),
        _RUNTIME_BASE_VALUES["YOUTUBE_TRANSCRIPTS_ENABLED"],
    )
    YOUTUBE_TRANSCRIPT_MODEL_SIZE = (
        str(
            persisted.get("youtube_transcript_model_size", _RUNTIME_BASE_VALUES["YOUTUBE_TRANSCRIPT_MODEL_SIZE"]) or ""
        ).strip()
        or _RUNTIME_BASE_VALUES["YOUTUBE_TRANSCRIPT_MODEL_SIZE"]
    )
    YOUTUBE_TRANSCRIPT_DEFAULT_LANGUAGE = str(
        persisted.get("youtube_transcript_language", _RUNTIME_BASE_VALUES["YOUTUBE_TRANSCRIPT_DEFAULT_LANGUAGE"]) or ""
    ).strip()
    RAG_ENABLED = _runtime_setting_bool(persisted.get("rag_enabled"), _RUNTIME_BASE_VALUES["RAG_ENABLED"])
    CHAT_SUMMARY_MODEL = (
        str(persisted.get("chat_summary_model", _RUNTIME_BASE_VALUES["CHAT_SUMMARY_MODEL"]) or "").strip()
        or DEFAULT_CHAT_MODEL
    )
    RAG_CHUNK_SIZE = _runtime_setting_int(
        persisted.get("rag_chunk_size"),
        _RUNTIME_BASE_VALUES["RAG_CHUNK_SIZE"],
        300,
        CONTENT_MAX_CHARS,
    )
    RAG_CHUNK_OVERLAP = _runtime_setting_int(
        persisted.get("rag_chunk_overlap"),
        _RUNTIME_BASE_VALUES["RAG_CHUNK_OVERLAP"],
        0,
        max(0, RAG_CHUNK_SIZE // 2),
    )
    RAG_MAX_CHUNKS_PER_SOURCE = _runtime_setting_int(
        persisted.get("rag_max_chunks_per_source"),
        _RUNTIME_BASE_VALUES["RAG_MAX_CHUNKS_PER_SOURCE"],
        1,
        20,
    )
    RAG_SEARCH_DEFAULT_TOP_K = _runtime_setting_int(
        persisted.get("rag_search_top_k"),
        _RUNTIME_BASE_VALUES["RAG_SEARCH_DEFAULT_TOP_K"],
        1,
        50,
    )
    RAG_SEARCH_MIN_SIMILARITY = _runtime_setting_float(
        persisted.get("rag_search_min_similarity"),
        _RUNTIME_BASE_VALUES["RAG_SEARCH_MIN_SIMILARITY"],
        0.0,
        1.0,
    )
    RAG_QUERY_EXPANSION_ENABLED = _runtime_setting_bool(
        persisted.get("rag_query_expansion_enabled"),
        _RUNTIME_BASE_VALUES["RAG_QUERY_EXPANSION_ENABLED"],
    )
    RAG_QUERY_EXPANSION_MAX_VARIANTS = _runtime_setting_int(
        persisted.get("rag_query_expansion_max_variants"),
        _RUNTIME_BASE_VALUES["RAG_QUERY_EXPANSION_MAX_VARIANTS"],
        1,
        10,
    )
    TOOL_MEMORY_TTL_DEFAULT_SECONDS = _runtime_setting_int(
        persisted.get("tool_memory_ttl_default_seconds"),
        _RUNTIME_BASE_VALUES["TOOL_MEMORY_TTL_DEFAULT_SECONDS"],
        60,
        31_536_000,
    )
    TOOL_MEMORY_TTL_WEB_SECONDS = _runtime_setting_int(
        persisted.get("tool_memory_ttl_web_seconds"),
        _RUNTIME_BASE_VALUES["TOOL_MEMORY_TTL_WEB_SECONDS"],
        60,
        31_536_000,
    )
    TOOL_MEMORY_TTL_NEWS_SECONDS = _runtime_setting_int(
        persisted.get("tool_memory_ttl_news_seconds"),
        _RUNTIME_BASE_VALUES["TOOL_MEMORY_TTL_NEWS_SECONDS"],
        60,
        31_536_000,
    )
    FETCH_RAW_TOOL_RESULT_MAX_TEXT_CHARS = _runtime_setting_int(
        persisted.get("fetch_raw_max_text_chars"),
        _RUNTIME_BASE_VALUES["FETCH_RAW_TOOL_RESULT_MAX_TEXT_CHARS"],
        1_000,
        CONTENT_MAX_CHARS,
    )
    FETCH_SUMMARY_MAX_CHARS = _runtime_setting_int(
        persisted.get("fetch_summary_max_chars"),
        _RUNTIME_BASE_VALUES["FETCH_SUMMARY_MAX_CHARS"],
        500,
        CONTENT_MAX_CHARS,
    )
    IMAGE_UPLOADS_ENABLED = OCR_ENABLED or bool(OPENROUTER_API_KEY) or bool(DEEPSEEK_API_KEY) or bool(MINIMAX_API_KEY)

    DEFAULT_SETTINGS.update(
        {
            "openrouter_http_referer": OPENROUTER_HTTP_REFERER,
            "openrouter_app_title": OPENROUTER_APP_TITLE,
            "login_session_timeout_minutes": str(LOGIN_SESSION_TIMEOUT_MINUTES),
            "login_max_failed_attempts": str(LOGIN_MAX_FAILED_ATTEMPTS),
            "login_lockout_seconds": str(LOGIN_LOCKOUT_SECONDS),
            "login_remember_session_days": str(LOGIN_REMEMBER_SESSION_DAYS),
            "conversation_memory_enabled": "true" if CONVERSATION_MEMORY_ENABLED else "false",
            "ocr_enabled": "true" if OCR_ENABLED else "false",
            "ocr_provider": OCR_PROVIDER,
            "rag_enabled": "true" if RAG_ENABLED else "false",
            "youtube_transcripts_enabled": "true" if YOUTUBE_TRANSCRIPTS_ENABLED else "false",
            "youtube_transcript_model_size": YOUTUBE_TRANSCRIPT_MODEL_SIZE,
            "youtube_transcript_language": YOUTUBE_TRANSCRIPT_DEFAULT_LANGUAGE,
            "chat_summary_model": CHAT_SUMMARY_MODEL,
            "rag_chunk_size": str(RAG_CHUNK_SIZE),
            "rag_chunk_overlap": str(RAG_CHUNK_OVERLAP),
            "rag_max_chunks_per_source": str(RAG_MAX_CHUNKS_PER_SOURCE),
            "rag_search_top_k": str(RAG_SEARCH_DEFAULT_TOP_K),
            "rag_search_min_similarity": str(RAG_SEARCH_MIN_SIMILARITY),
            "rag_query_expansion_enabled": "true" if RAG_QUERY_EXPANSION_ENABLED else "false",
            "rag_query_expansion_max_variants": str(RAG_QUERY_EXPANSION_MAX_VARIANTS),
            "tool_memory_ttl_default_seconds": str(TOOL_MEMORY_TTL_DEFAULT_SECONDS),
            "tool_memory_ttl_web_seconds": str(TOOL_MEMORY_TTL_WEB_SECONDS),
            "tool_memory_ttl_news_seconds": str(TOOL_MEMORY_TTL_NEWS_SECONDS),
            "fetch_raw_max_text_chars": str(FETCH_RAW_TOOL_RESULT_MAX_TEXT_CHARS),
            "fetch_summary_max_chars": str(FETCH_SUMMARY_MAX_CHARS),
        }
    )
    return persisted


_RUNTIME_PROPAGATION_NAMES = {
    "CHAT_SUMMARY_MODEL",
    "CONVERSATION_MEMORY_ENABLED",
    "FETCH_RAW_TOOL_RESULT_MAX_TEXT_CHARS",
    "FETCH_SUMMARY_MAX_CHARS",
    "IMAGE_UPLOADS_ENABLED",
    "LOGIN_LOCKOUT_SECONDS",
    "LOGIN_MAX_FAILED_ATTEMPTS",
    "LOGIN_REMEMBER_SESSION_DAYS",
    "LOGIN_SESSION_TIMEOUT_MINUTES",
    "OCR_ENABLED",
    "OCR_PROVIDER",
    "OPENROUTER_APP_TITLE",
    "OPENROUTER_HTTP_REFERER",
    "RAG_CHUNK_OVERLAP",
    "RAG_CHUNK_SIZE",
    "RAG_ENABLED",
    "RAG_MAX_CHUNKS_PER_SOURCE",
    "RAG_QUERY_EXPANSION_ENABLED",
    "RAG_QUERY_EXPANSION_MAX_VARIANTS",
    "RAG_SEARCH_DEFAULT_TOP_K",
    "RAG_SEARCH_MIN_SIMILARITY",
    "TOOL_MEMORY_TTL_DEFAULT_SECONDS",
    "TOOL_MEMORY_TTL_NEWS_SECONDS",
    "TOOL_MEMORY_TTL_WEB_SECONDS",
    "YOUTUBE_TRANSCRIPT_DEFAULT_LANGUAGE",
    "YOUTUBE_TRANSCRIPT_MODEL_SIZE",
    "YOUTUBE_TRANSCRIPTS_ENABLED",
}

_RUNTIME_PROPAGATION_MODULES = (
    "agent",
    "db",
    "doc_service",
    "image_service",
    "messages",
    "ocr_service",

    "rag_service",
    "routes.chat",
    "routes.conversations",
    "routes.pages",
    "tool_registry",
    "video_transcript_service",
)


def propagate_runtime_settings_to_loaded_modules() -> None:
    import sys

    for module_name in _RUNTIME_PROPAGATION_MODULES:
        module = sys.modules.get(module_name)
        if module is None:
            continue
        for attr_name in _RUNTIME_PROPAGATION_NAMES:
            if hasattr(module, attr_name):
                setattr(module, attr_name, globals()[attr_name])

    model_registry_module = sys.modules.get("model_registry")
    refreshed_deepseek_client = None
    if model_registry_module is not None:
        get_provider_client = getattr(model_registry_module, "get_provider_client", None)
        cache_clear = getattr(get_provider_client, "cache_clear", None)
        if callable(cache_clear):
            cache_clear()
        deepseek_provider = getattr(model_registry_module, "DEEPSEEK_PROVIDER", None)
        if callable(get_provider_client) and deepseek_provider:
            try:
                refreshed_deepseek_client = get_provider_client(deepseek_provider)
            except Exception:
                refreshed_deepseek_client = None

    if refreshed_deepseek_client is not None:
        for module_name in ("agent", "routes.conversations"):
            module = sys.modules.get(module_name)
            if module is not None and hasattr(module, "client"):
                setattr(module, "client", refreshed_deepseek_client)

    ocr_service_module = sys.modules.get("ocr_service")
    if ocr_service_module is not None and hasattr(ocr_service_module, "_ocr_engine"):
        ocr_service_module._ocr_engine = None

    video_transcript_module = sys.modules.get("video_transcript_service")
    if video_transcript_module is not None:
        if hasattr(video_transcript_module, "_WHISPER_MODEL"):
            video_transcript_module._WHISPER_MODEL = None
        if hasattr(video_transcript_module, "_WHISPER_MODEL_KEY"):
            video_transcript_module._WHISPER_MODEL_KEY = None


def get_feature_flags(settings: dict | None = None) -> dict:
    source = settings if isinstance(settings, dict) else {}
    rag_enabled = _runtime_setting_bool(source.get("rag_enabled"), RAG_ENABLED)
    ocr_enabled = _runtime_setting_bool(source.get("ocr_enabled"), OCR_ENABLED)
    conversation_memory_enabled = _runtime_setting_bool(
        source.get("conversation_memory_enabled"),
        CONVERSATION_MEMORY_ENABLED,
    )
    youtube_transcripts_enabled = _runtime_setting_bool(
        source.get("youtube_transcripts_enabled"),
        YOUTUBE_TRANSCRIPTS_ENABLED,
    )
    image_uploads_enabled = ocr_enabled or bool(OPENROUTER_API_KEY) or bool(DEEPSEEK_API_KEY) or bool(MINIMAX_API_KEY)
    return {
        "rag_enabled": rag_enabled,
        "ocr_enabled": ocr_enabled,
        "conversation_memory_enabled": conversation_memory_enabled,
        "image_uploads_enabled": image_uploads_enabled,
        "youtube_transcripts_enabled": youtube_transcripts_enabled,
        "deepseek_api_configured": bool(DEEPSEEK_API_KEY),
        "openrouter_api_configured": bool(OPENROUTER_API_KEY),
        "minimax_api_configured": bool(MINIMAX_API_KEY),
        "remote_image_provider_configured": bool(OPENROUTER_API_KEY or DEEPSEEK_API_KEY or MINIMAX_API_KEY),
        "scratchpad_admin_editing": SCRATCHPAD_ADMIN_EDITING_ENABLED,
        "login_pin_enabled": is_login_pin_configured(),
    }


def get_runtime_setting(key: str):
    """Merkezi runtime ayar erişim noktası.

    Bu fonksiyon, _RUNTIME_PROPAGATION_NAMES'daki ayarlara her zaman güncel
    değerleri döndürür. "from config import X" yerine bu fonksiyonun
    kullanılması, global state'in modüler bağımlılıklarını azaltır.

    Args:
        key: Ayar adı (örn: "RAG_ENABLED", "CHAT_SUMMARY_MODEL")

    Returns:
        Ayarın güncel değeri

    Raises:
        KeyError: Anahtar _RUNTIME_PROPAGATION_NAMES'da bulunamadığında
    """
    if key not in _RUNTIME_PROPAGATION_NAMES:
        raise KeyError(f"'{key}' is not a runtime setting")
    return globals()[key]


def _runtime_settings_snapshot() -> dict:
    """Tüm runtime ayarlarının anlık görüntüsünü döndürür."""
    return {key: globals()[key] for key in _RUNTIME_PROPAGATION_NAMES}


def __getattr__(name: str):
    """Module-level attribute erişimi için lazy lookup.

    Bu, "import config; config.RAG_ENABLED" gibi erişimlerde
    her zaman güncel değer döndürür. "from config import X" kullanan
    kodlar için bu geçerli değildir (o andaki değer yakalanır).
    """
    if name in _RUNTIME_PROPAGATION_NAMES:
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
