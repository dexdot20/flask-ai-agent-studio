from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from flask import current_app, has_app_context

from canvas_service import extract_canvas_active_document_id, extract_canvas_documents, extract_canvas_viewports
from config import (
    AGENT_CONTEXT_COMPACTION_KEEP_RECENT_ROUNDS,
    AGENT_CONTEXT_COMPACTION_THRESHOLD,
    CACHE_TTL_HOURS,
    CANVAS_EXPAND_DEFAULT_MAX_LINES,
    CANVAS_PROMPT_CODE_LINE_MAX_CHARS,
    CANVAS_PROMPT_DEFAULT_MAX_CHARS,
    CANVAS_PROMPT_DEFAULT_MAX_LINES,
    CANVAS_PROMPT_TEXT_LINE_MAX_CHARS,
    CANVAS_PROMPT_DEFAULT_MAX_TOKENS,
    CANVAS_SCROLL_WINDOW_LINES,
    CHAT_SUMMARY_ALLOWED_MODES,
    CHAT_SUMMARY_DETAIL_LEVELS,
    CHAT_SUMMARY_MODE,
    CHAT_SUMMARY_TRIGGER_TOKEN_COUNT,
    CONTEXT_SELECTION_ALLOWED_STRATEGIES,
    CONTENT_MAX_CHARS,
    CLARIFICATION_DEFAULT_MAX_QUESTIONS,
    CLARIFICATION_QUESTION_LIMIT_MAX,
    CLARIFICATION_QUESTION_LIMIT_MIN,
    CONVERSATION_MEMORY_ENABLED,
    DB_PATH,
    DEFAULT_WEB_CACHE_TTL_HOURS,
    DEFAULT_SETTINGS,
    OPENROUTER_PROMPT_CACHE_DEFAULT_ENABLED,
    PRUNING_MIN_TARGET_TOKENS,
    PRUNING_TARGET_REDUCTION_RATIO,
    SCRATCHPAD_DEFAULT_SECTION,
    SCRATCHPAD_SECTION_ORDER,
    SCRATCHPAD_SECTION_SETTING_KEYS,
    DOCUMENT_STORAGE_DIR,
    FETCH_RAW_TOOL_RESULT_MAX_TEXT_CHARS,
    FETCH_SUMMARIZE_MAX_INPUT_CHARS,
    FETCH_SUMMARIZE_MAX_OUTPUT_TOKENS,
    FETCH_SUMMARY_TOKEN_THRESHOLD,
    FETCH_URL_TO_CANVAS_CHUNK_CHARS,
    FETCH_URL_TO_CANVAS_CHUNK_THRESHOLD,
    FETCH_URL_TO_CANVAS_MAX_CHUNKS,
    IMAGE_STORAGE_DIR,
    DEFAULT_MAX_PARALLEL_TOOLS,
    ENTROPY_PROFILE_PRESETS,
    MAX_AI_PERSONALITY_LENGTH,
    MAX_PERSONA_COUNT,
    MAX_PERSONA_NAME_LENGTH,
    MAX_USER_PREFERENCES_LENGTH,
    PROMPT_MAX_INPUT_TOKENS,
    PROMPT_PREFLIGHT_SUMMARY_TOKEN_COUNT,
    PROMPT_RAG_MAX_TOKENS,
    PROMPT_RECENT_HISTORY_MAX_TOKENS,
    PROMPT_RESPONSE_TOKEN_RESERVE,
    PROMPT_SUMMARY_MAX_TOKENS,
    PROMPT_TOOL_TRACE_MAX_TOKENS,
    PROMPT_TOOL_MEMORY_MAX_TOKENS,
    RAG_CONTEXT_SIZE_PRESETS,
    RAG_DEFAULT_CONTEXT_SIZE_PRESET,
    RAG_DEFAULT_SENSITIVITY_PRESET,
    RAG_ENABLED,
    RAG_SOURCE_CONVERSATION,
    RAG_SOURCE_TOOL_MEMORY,
    RAG_SOURCE_TOOL_RESULT,
    RAG_SOURCE_UPLOADED_DOCUMENT,
    RAG_SENSITIVITY_PRESETS,
    RAG_TOOL_RESULT_MAX_TEXT_CHARS,
    RAG_TOOL_RESULT_SUMMARY_MAX_CHARS,
    SUMMARY_RETRY_MIN_SOURCE_TOKENS,
    SUMMARY_SOURCE_TARGET_TOKENS,
    MAX_PARALLEL_TOOLS_MAX,
    MAX_PARALLEL_TOOLS_MIN,
    SUB_AGENT_ALLOWED_TOOL_NAMES,
    IMAGE_UPLOADS_ENABLED,
    SUB_AGENT_DEFAULT_RETRY_ATTEMPTS,
    SUB_AGENT_DEFAULT_MAX_STEPS,
    SUB_AGENT_DEFAULT_MAX_PARALLEL_TOOLS,
    SUB_AGENT_DEFAULT_RETRY_DELAY_SECONDS,
    SUB_AGENT_DEFAULT_TIMEOUT_SECONDS,
    SUB_AGENT_MAX_STEPS_MAX,
    SUB_AGENT_MAX_STEPS_MIN,
    SUB_AGENT_RETRY_ATTEMPTS_MAX,
    SUB_AGENT_RETRY_ATTEMPTS_MIN,
    SUB_AGENT_RETRY_DELAY_MAX_SECONDS,
    SUB_AGENT_RETRY_DELAY_MIN_SECONDS,
    SUB_AGENT_TIMEOUT_MAX_SECONDS,
    SUB_AGENT_TIMEOUT_MIN_SECONDS,
    WEB_CACHE_TTL_HOURS_MAX,
    WEB_CACHE_TTL_HOURS_MIN,
)
from proxy_settings import normalize_proxy_enabled_operations
from tool_registry import TOOL_SPEC_BY_NAME
from token_utils import estimate_text_tokens

_db_path = DB_PATH
MESSAGE_USAGE_BREAKDOWN_KEYS = (
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
MESSAGE_USAGE_BREAKDOWN_REDUCTION_ORDER = (
    "tool_specs",
    "internal_state",
    "canvas",
    "scratchpad",
    "tool_trace",
    "tool_memory",
    "rag_context",
    "assistant_tool_calls",
    "tool_results",
    "assistant_history",
    "user_messages",
    "core_instructions",
)
MESSAGE_USAGE_BREAKDOWN_PROTECTED_KEYS = (
    "user_messages",
    "tool_results",
)
CONTENT_HEAVY_CANVAS_TOOL_NAMES = {
    "create_canvas_document",
    "rewrite_canvas_document",
    "replace_canvas_lines",
    "insert_canvas_lines",
}
TOOL_CALL_CONTENT_PREVIEW_MAX_CHARS = 1_000
TOOL_CALL_CONTENT_PREVIEW_MAX_LINES = 48
TOOL_CALL_LINES_PREVIEW_MAX_ITEMS = 24
TOOL_CALL_LINE_PREVIEW_MAX_CHARS = 240
TOOL_CALL_LINES_PREVIEW_MAX_TOTAL_CHARS = 1_000
TOOL_CALL_METADATA_LIST_PREVIEW_MAX_ITEMS = 12
TOOL_CALL_METADATA_ITEM_PREVIEW_MAX_CHARS = 120
LEGACY_MESSAGE_USAGE_BREAKDOWN_KEYS = {
    "core_instructions": ("system_prompt", "final_instruction"),
}
MESSAGE_TOOL_TRACE_STATES = {"running", "done", "error"}
SUB_AGENT_TRACE_MAX_RUNS = 8
SUB_AGENT_TRACE_MAX_MESSAGES = 24
SUB_AGENT_TRACE_MAX_TOOL_CALLS = 8
SUB_AGENT_TRACE_MAX_ARTIFACTS = 16
VISIBLE_CHAT_ROLES = {"user", "assistant", "summary"}
SUMMARY_TRIGGER_TOKEN_ROLES = {"user", "assistant", "tool"}
RAG_SOURCE_TYPE_SETTING_OPTIONS = (
    RAG_SOURCE_CONVERSATION,
    RAG_SOURCE_TOOL_RESULT,
    RAG_SOURCE_TOOL_MEMORY,
    RAG_SOURCE_UPLOADED_DOCUMENT,
)
STATE_MUTATION_TARGET_CONVERSATION_MEMORY = "conversation_memory"
STATE_MUTATION_TARGET_SCRATCHPAD_SECTION = "scratchpad_section"
STATE_MUTATION_TARGET_USER_PROFILE = "user_profile"
STATE_MUTATION_OPERATION_APPEND = "append"
STATE_MUTATION_OPERATION_DELETE = "delete"
STATE_MUTATION_OPERATION_REPLACE = "replace"
STATE_MUTATION_OPERATION_UPSERT = "upsert"
STATE_MUTATION_TARGET_KINDS = {
    STATE_MUTATION_TARGET_CONVERSATION_MEMORY,
    STATE_MUTATION_TARGET_SCRATCHPAD_SECTION,
    STATE_MUTATION_TARGET_USER_PROFILE,
}
STATE_MUTATION_OPERATIONS = {
    STATE_MUTATION_OPERATION_APPEND,
    STATE_MUTATION_OPERATION_DELETE,
    STATE_MUTATION_OPERATION_REPLACE,
    STATE_MUTATION_OPERATION_UPSERT,
}


def configure_db_path(path: str | None = None) -> str:
    global _db_path
    _db_path = path or DB_PATH
    return _db_path


def get_configured_db_path() -> str:
    if has_app_context():
        return current_app.config.get("DATABASE_PATH") or _db_path
    return _db_path


def get_db(database_path: str | None = None):
    db_path = str(database_path or get_configured_db_path()).strip() or get_configured_db_path()
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                title      TEXT    NOT NULL DEFAULT 'New Chat',
                model      TEXT    NOT NULL DEFAULT 'deepseek-chat',
                persona_id INTEGER REFERENCES personas(id) ON DELETE SET NULL,
                created_at TEXT    NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT    NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS messages (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id   INTEGER NOT NULL,
                position          INTEGER,
                role              TEXT    NOT NULL,
                content           TEXT    NOT NULL,
                metadata          TEXT,
                tool_calls        TEXT,
                tool_call_id      TEXT,
                prompt_tokens     INTEGER,
                completion_tokens INTEGER,
                total_tokens      INTEGER,
                deleted_at        TEXT,
                created_at        TEXT    NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS app_settings (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS personas (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                name                 TEXT NOT NULL,
                general_instructions TEXT NOT NULL DEFAULT '',
                ai_personality       TEXT NOT NULL DEFAULT '',
                created_at           TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at           TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS user_profile (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 1.0,
                source     TEXT,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS conversation_memory (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                message_id      INTEGER,
                entry_type      TEXT NOT NULL,
                key             TEXT NOT NULL,
                value           TEXT NOT NULL,
                created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
                FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS model_invocations (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id      INTEGER NOT NULL,
                assistant_message_id INTEGER,
                source_message_id    INTEGER,
                step                 INTEGER NOT NULL DEFAULT 0,
                call_index           INTEGER NOT NULL DEFAULT 0,
                call_type            TEXT NOT NULL DEFAULT 'agent_step',
                is_retry             INTEGER NOT NULL DEFAULT 0,
                retry_reason         TEXT,
                sub_agent_depth      INTEGER NOT NULL DEFAULT 0,
                provider             TEXT NOT NULL,
                api_model            TEXT NOT NULL,
                request_payload      TEXT NOT NULL,
                response_summary     TEXT,
                created_at           TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
                FOREIGN KEY (assistant_message_id) REFERENCES messages(id) ON DELETE SET NULL,
                FOREIGN KEY (source_message_id) REFERENCES messages(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS conversation_state_mutations (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id   INTEGER NOT NULL,
                source_message_id INTEGER,
                target_kind       TEXT NOT NULL,
                target_key        TEXT NOT NULL,
                operation         TEXT NOT NULL,
                before_value      TEXT,
                after_value       TEXT,
                reverted_at       TEXT,
                created_at        TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
                FOREIGN KEY (source_message_id) REFERENCES messages(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS image_assets (
                image_id         TEXT PRIMARY KEY,
                conversation_id  INTEGER NOT NULL,
                message_id       INTEGER,
                filename         TEXT NOT NULL,
                mime_type        TEXT NOT NULL,
                storage_path     TEXT NOT NULL,
                initial_analysis TEXT,
                created_at       TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
                FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS web_cache (
                key       TEXT PRIMARY KEY,
                value     TEXT NOT NULL,
                cached_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS rag_documents (
                source_key TEXT PRIMARY KEY,
                source_name TEXT NOT NULL,
                source_type TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'general',
                chunk_count INTEGER NOT NULL DEFAULT 0,
                metadata TEXT,
                expires_at TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TRIGGER IF NOT EXISTS trg_messages_assign_position
            AFTER INSERT ON messages
            FOR EACH ROW
            WHEN NEW.position IS NULL
            BEGIN
                UPDATE messages
                   SET position = (
                       SELECT COALESCE(MAX(position), 0) + 1
                       FROM messages
                       WHERE conversation_id = NEW.conversation_id
                         AND id <> NEW.id
                   )
                 WHERE id = NEW.id;
            END;
            CREATE TABLE IF NOT EXISTS file_assets (
                file_id          TEXT PRIMARY KEY,
                conversation_id  INTEGER NOT NULL,
                message_id       INTEGER,
                filename         TEXT NOT NULL,
                mime_type        TEXT NOT NULL,
                storage_path     TEXT NOT NULL,
                extracted_text   TEXT,
                created_at       TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
                FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS video_assets (
                video_id            TEXT PRIMARY KEY,
                conversation_id     INTEGER NOT NULL,
                message_id          INTEGER,
                platform            TEXT NOT NULL DEFAULT 'youtube',
                source_url          TEXT NOT NULL,
                source_video_id     TEXT,
                title               TEXT,
                transcript_text     TEXT NOT NULL,
                transcript_language TEXT,
                duration_seconds    INTEGER,
                created_at          TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
                FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE SET NULL
            );
            CREATE INDEX IF NOT EXISTS idx_image_assets_conversation_created
            ON image_assets(conversation_id, created_at, image_id);
            CREATE INDEX IF NOT EXISTS idx_file_assets_conversation_created
            ON file_assets(conversation_id, created_at, file_id);
            CREATE INDEX IF NOT EXISTS idx_video_assets_conversation_created
            ON video_assets(conversation_id, created_at, video_id);
            CREATE INDEX IF NOT EXISTS idx_conversation_memory_conversation_created
            ON conversation_memory(conversation_id, created_at, id);
            CREATE INDEX IF NOT EXISTS idx_model_invocations_conversation_created
            ON model_invocations(conversation_id, created_at, id);
            CREATE INDEX IF NOT EXISTS idx_model_invocations_assistant_message
            ON model_invocations(assistant_message_id, id);
            CREATE INDEX IF NOT EXISTS idx_model_invocations_source_message
            ON model_invocations(source_message_id, id);
            CREATE INDEX IF NOT EXISTS idx_conversation_state_mutations_conversation_source
            ON conversation_state_mutations(conversation_id, source_message_id, id);
            CREATE INDEX IF NOT EXISTS idx_conversation_state_mutations_target
            ON conversation_state_mutations(target_kind, target_key, id);
            CREATE INDEX IF NOT EXISTS idx_personas_updated_at
            ON personas(updated_at, id);
            """
        )


def ensure_messages_metadata_column() -> None:
    with get_db() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(messages)").fetchall()}
        if "metadata" not in columns:
            conn.execute("ALTER TABLE messages ADD COLUMN metadata TEXT")


def ensure_messages_tool_history_columns() -> None:
    with get_db() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(messages)").fetchall()}
        if "tool_calls" not in columns:
            conn.execute("ALTER TABLE messages ADD COLUMN tool_calls TEXT")
        if "tool_call_id" not in columns:
            conn.execute("ALTER TABLE messages ADD COLUMN tool_call_id TEXT")


def ensure_messages_position_column() -> None:
    with get_db() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(messages)").fetchall()}
        if "position" not in columns:
            conn.execute("ALTER TABLE messages ADD COLUMN position INTEGER")

        rows = conn.execute(
            "SELECT id, conversation_id, position FROM messages ORDER BY conversation_id, id"
        ).fetchall()
        last_position_by_conversation = {}
        for row in rows:
            conversation_id = row["conversation_id"]
            current_position = row["position"]
            if isinstance(current_position, int) and current_position > 0:
                last_position_by_conversation[conversation_id] = current_position
                continue
            next_position = last_position_by_conversation.get(conversation_id, 0) + 1
            conn.execute("UPDATE messages SET position = ? WHERE id = ?", (next_position, row["id"]))
            last_position_by_conversation[conversation_id] = next_position
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_conversation_position ON messages(conversation_id, position, id)"
        )


def ensure_messages_deleted_at_column() -> None:
    with get_db() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(messages)").fetchall()}
        if "deleted_at" not in columns:
            conn.execute("ALTER TABLE messages ADD COLUMN deleted_at TEXT")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_conversation_deleted_position ON messages(conversation_id, deleted_at, position, id)"
        )


def ensure_rag_documents_expires_at_column() -> None:
    with get_db() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(rag_documents)").fetchall()}
        if "expires_at" not in columns:
            conn.execute("ALTER TABLE rag_documents ADD COLUMN expires_at TEXT")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_rag_documents_expires_at ON rag_documents(expires_at, category, updated_at)"
        )


def delete_rag_document_records(source_keys: Iterable[str]) -> None:
    normalized_keys = [str(source_key or "").strip() for source_key in source_keys if str(source_key or "").strip()]
    if not normalized_keys:
        return

    placeholders = ", ".join("?" for _ in normalized_keys)
    with get_db() as conn:
        conn.execute(f"DELETE FROM rag_documents WHERE source_key IN ({placeholders})", tuple(normalized_keys))


def get_expired_rag_document_source_keys(now_iso: str | None = None) -> list[str]:
    reference_time = str(now_iso or "").strip() or datetime_utc_now_iso()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT source_key FROM rag_documents WHERE expires_at IS NOT NULL AND expires_at <= ? ORDER BY expires_at ASC",
            (reference_time,),
        ).fetchall()
    return [str(row["source_key"] or "").strip() for row in rows if str(row["source_key"] or "").strip()]


def datetime_utc_now_iso() -> str:
    with get_db() as conn:
        row = conn.execute("SELECT datetime('now') AS now_iso").fetchone()
    return str(row["now_iso"] or "").strip()


def initialize_database() -> None:
    init_db()
    ensure_persona_schema()
    ensure_messages_metadata_column()
    ensure_messages_tool_history_columns()
    ensure_messages_position_column()
    ensure_messages_deleted_at_column()
    ensure_rag_documents_expires_at_column()


def _normalize_user_profile_value(value, max_length: int = 500) -> str:
    return " ".join(str(value or "").strip().split())[:max_length]


def _persona_row_to_dict(row) -> dict | None:
    if not row:
        return None
    return {
        "id": int(row["id"]),
        "name": str(row["name"] or "").strip(),
        "general_instructions": normalize_assistant_behavior_text(row["general_instructions"]),
        "ai_personality": normalize_assistant_behavior_text(row["ai_personality"]),
        "created_at": str(row["created_at"] or "").strip(),
        "updated_at": str(row["updated_at"] or "").strip(),
    }


def _coerce_positive_int(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def normalize_persona_name(value) -> str:
    return " ".join(str(value or "").strip().split())[:MAX_PERSONA_NAME_LENGTH]


def _normalize_persona_behavior(value, max_length: int) -> str:
    return normalize_assistant_behavior_text(value)[:max_length]


def _get_persona_by_id(conn, persona_id: int | None) -> dict | None:
    normalized_persona_id = _coerce_positive_int(persona_id)
    if normalized_persona_id is None:
        return None
    row = conn.execute(
        """SELECT id, name, general_instructions, ai_personality, created_at, updated_at
           FROM personas WHERE id = ?""",
        (normalized_persona_id,),
    ).fetchone()
    return _persona_row_to_dict(row)


def _migrate_global_behavior_to_default_persona(conn) -> None:
    row = conn.execute("SELECT COUNT(*) AS count FROM personas").fetchone()
    if int(row["count"] or 0) > 0:
        return

    settings_rows = conn.execute(
        "SELECT key, value FROM app_settings WHERE key IN (?, ?, ?)",
        ("general_instructions", "user_preferences", "ai_personality"),
    ).fetchall()
    settings = {str(setting_row["key"] or "").strip(): setting_row["value"] for setting_row in settings_rows}
    general_instructions = normalize_assistant_behavior_text(settings.get("general_instructions", ""))
    if not general_instructions:
        general_instructions = normalize_assistant_behavior_text(settings.get("user_preferences", ""))
    ai_personality = normalize_assistant_behavior_text(settings.get("ai_personality", ""))
    if not general_instructions and not ai_personality:
        return

    cursor = conn.execute(
        "INSERT INTO personas (name, general_instructions, ai_personality) VALUES (?, ?, ?)",
        (
            "Default",
            general_instructions[:MAX_USER_PREFERENCES_LENGTH],
            ai_personality[:MAX_AI_PERSONALITY_LENGTH],
        ),
    )
    persona_id = _coerce_positive_int(cursor.lastrowid)
    if persona_id is None:
        return

    _upsert_app_setting(conn, "default_persona_id", str(persona_id))
    _upsert_app_setting(conn, "general_instructions", "")
    _upsert_app_setting(conn, "user_preferences", "")
    _upsert_app_setting(conn, "ai_personality", "")


def ensure_persona_schema() -> None:
    with get_db() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS personas (
                   id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                   name                 TEXT NOT NULL,
                   general_instructions TEXT NOT NULL DEFAULT '',
                   ai_personality       TEXT NOT NULL DEFAULT '',
                   created_at           TEXT NOT NULL DEFAULT (datetime('now')),
                   updated_at           TEXT NOT NULL DEFAULT (datetime('now'))
               )"""
        )
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(conversations)").fetchall()}
        if "persona_id" not in columns:
            conn.execute(
                "ALTER TABLE conversations ADD COLUMN persona_id INTEGER REFERENCES personas(id) ON DELETE SET NULL"
            )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_personas_updated_at ON personas(updated_at, id)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversations_persona_id ON conversations(persona_id, updated_at, id)"
        )
        _migrate_global_behavior_to_default_persona(conn)


CONVERSATION_MEMORY_ENTRY_TYPES = {"user_info", "task_context", "tool_result", "decision"}


def _conversation_memory_row_to_dict(row) -> dict | None:
    if not row:
        return None
    return {
        "id": int(row["id"]),
        "conversation_id": int(row["conversation_id"]),
        "message_id": int(row["message_id"]) if row["message_id"] is not None else None,
        "entry_type": str(row["entry_type"] or "").strip(),
        "key": str(row["key"] or "").strip(),
        "value": str(row["value"] or "").strip(),
        "created_at": str(row["created_at"] or "").strip(),
    }


def _find_conversation_memory_entry_by_key(conversation_id: int, key: str) -> dict | None:
    normalized_conversation_id = int(conversation_id or 0)
    normalized_key = _normalize_conversation_memory_key(key)
    if normalized_conversation_id <= 0 or not normalized_key:
        return None

    with get_db() as conn:
        row = conn.execute(
            """SELECT id, conversation_id, message_id, entry_type, key, value, created_at
               FROM conversation_memory
               WHERE conversation_id = ?
                 AND lower(key) = lower(?)
               ORDER BY created_at DESC, id DESC
               LIMIT 1""",
            (normalized_conversation_id, normalized_key),
        ).fetchone()
    return _conversation_memory_row_to_dict(row)


def _normalize_conversation_memory_entry_type(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in CONVERSATION_MEMORY_ENTRY_TYPES:
        raise ValueError("Unsupported conversation memory entry type.")
    return normalized


def _normalize_conversation_memory_key(value: str, max_length: int = 120) -> str:
    normalized = " ".join(str(value or "").strip().split())[:max_length]
    if not normalized:
        raise ValueError("Conversation memory key is required.")
    return normalized


def _normalize_conversation_memory_value(value: str, max_length: int = 1500) -> str:
    normalized = " ".join(str(value or "").strip().split())[:max_length]
    if not normalized:
        raise ValueError("Conversation memory value is required.")
    return normalized


def insert_conversation_memory_entry(
    conversation_id: int,
    entry_type: str,
    key: str,
    value: str,
    message_id: int | None = None,
    *,
    mutation_context: dict | None = None,
) -> dict:
    normalized_conversation_id = int(conversation_id or 0)
    if normalized_conversation_id <= 0:
        raise ValueError("conversation_id is required.")

    normalized_entry_type = _normalize_conversation_memory_entry_type(entry_type)
    normalized_key = _normalize_conversation_memory_key(key)
    normalized_value = _normalize_conversation_memory_value(value)
    normalized_message_id = int(message_id) if message_id not in (None, "") and int(message_id) > 0 else None
    existing_entry = _find_conversation_memory_entry_by_key(normalized_conversation_id, normalized_key)

    with get_db() as conn:
        if existing_entry:
            entry_id = int(existing_entry["id"])
            conn.execute(
                """UPDATE conversation_memory
                   SET message_id = ?, entry_type = ?, key = ?, value = ?, created_at = datetime('now')
                   WHERE id = ? AND conversation_id = ?""",
                (
                    normalized_message_id,
                    normalized_entry_type,
                    normalized_key,
                    normalized_value,
                    entry_id,
                    normalized_conversation_id,
                ),
            )
        else:
            cursor = conn.execute(
                """INSERT INTO conversation_memory (
                       conversation_id, message_id, entry_type, key, value
                   ) VALUES (?, ?, ?, ?, ?)""",
                (
                    normalized_conversation_id,
                    normalized_message_id,
                    normalized_entry_type,
                    normalized_key,
                    normalized_value,
                ),
            )
            entry_id = int(cursor.lastrowid)
        row = conn.execute(
            """SELECT id, conversation_id, message_id, entry_type, key, value, created_at
               FROM conversation_memory
               WHERE id = ?""",
            (entry_id,),
        ).fetchone()
    entry = _conversation_memory_row_to_dict(row) or {}
    entry["updated_existing"] = existing_entry is not None
    before_snapshot = dict(existing_entry) if isinstance(existing_entry, dict) else None
    after_snapshot = {key: value for key, value in entry.items() if key != "updated_existing"}
    if before_snapshot != after_snapshot:
        record_conversation_state_mutation(
            normalized_conversation_id,
            source_message_id=_normalize_state_mutation_source_message_id((mutation_context or {}).get("source_message_id")),
            target_kind=STATE_MUTATION_TARGET_CONVERSATION_MEMORY,
            target_key=normalized_key,
            operation=STATE_MUTATION_OPERATION_UPSERT,
            before_value=before_snapshot,
            after_value=after_snapshot,
        )
    return entry


def get_conversation_memory_entry(entry_id: int, conversation_id: int | None = None) -> dict | None:
    normalized_entry_id = int(entry_id or 0)
    if normalized_entry_id <= 0 or not CONVERSATION_MEMORY_ENABLED:
        return None

    normalized_conversation_id = int(conversation_id or 0) if conversation_id not in (None, "") else None
    query = [
        "SELECT id, conversation_id, message_id, entry_type, key, value, created_at",
        "FROM conversation_memory",
        "WHERE id = ?",
    ]
    params: list[int] = [normalized_entry_id]
    if normalized_conversation_id is not None and normalized_conversation_id > 0:
        query.append("AND conversation_id = ?")
        params.append(normalized_conversation_id)

    with get_db() as conn:
        row = conn.execute("\n".join(query), tuple(params)).fetchone()
    return _conversation_memory_row_to_dict(row)


def update_conversation_memory_entry(
    entry_id: int,
    conversation_id: int,
    entry_type: str,
    key: str,
    value: str,
    message_id: int | None = None,
    *,
    mutation_context: dict | None = None,
) -> dict | None:
    normalized_entry_id = int(entry_id or 0)
    normalized_conversation_id = int(conversation_id or 0)
    if normalized_entry_id <= 0 or normalized_conversation_id <= 0 or not CONVERSATION_MEMORY_ENABLED:
        return None

    current_entry = get_conversation_memory_entry(normalized_entry_id, normalized_conversation_id)
    if not current_entry:
        return None

    normalized_entry_type = _normalize_conversation_memory_entry_type(entry_type)
    normalized_key = _normalize_conversation_memory_key(key)
    normalized_value = _normalize_conversation_memory_value(value)
    normalized_message_id = (
        int(message_id)
        if message_id not in (None, "") and int(message_id) > 0
        else current_entry.get("message_id")
    )

    with get_db() as conn:
        conn.execute(
            """UPDATE conversation_memory
               SET entry_type = ?, key = ?, value = ?, message_id = ?
               WHERE id = ? AND conversation_id = ?""",
            (
                normalized_entry_type,
                normalized_key,
                normalized_value,
                normalized_message_id,
                normalized_entry_id,
                normalized_conversation_id,
            ),
        )

    updated_entry = get_conversation_memory_entry(normalized_entry_id, normalized_conversation_id)
    before_snapshot = dict(current_entry) if isinstance(current_entry, dict) else None
    after_snapshot = dict(updated_entry) if isinstance(updated_entry, dict) else None
    if before_snapshot != after_snapshot:
        record_conversation_state_mutation(
            normalized_conversation_id,
            source_message_id=_normalize_state_mutation_source_message_id((mutation_context or {}).get("source_message_id")),
            target_kind=STATE_MUTATION_TARGET_CONVERSATION_MEMORY,
            target_key=normalized_key,
            operation=STATE_MUTATION_OPERATION_UPSERT,
            before_value=before_snapshot,
            after_value=after_snapshot,
        )
    return updated_entry


def get_conversation_memory(conversation_id: int, limit: int = 40) -> list[dict]:
    normalized_conversation_id = int(conversation_id or 0)
    if normalized_conversation_id <= 0 or not CONVERSATION_MEMORY_ENABLED:
        return []

    normalized_limit = max(1, min(200, int(limit or 40)))
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, conversation_id, message_id, entry_type, key, value, created_at
               FROM conversation_memory
               WHERE conversation_id = ?
               ORDER BY created_at ASC, id ASC
               LIMIT ?""",
            (normalized_conversation_id, normalized_limit),
        ).fetchall()
    return [entry for entry in (_conversation_memory_row_to_dict(row) for row in rows) if entry]


def delete_conversation_memory_entry(
    entry_id: int,
    conversation_id: int,
    *,
    mutation_context: dict | None = None,
) -> bool:
    normalized_entry_id = int(entry_id or 0)
    normalized_conversation_id = int(conversation_id or 0)
    if normalized_entry_id <= 0 or normalized_conversation_id <= 0:
        return False

    current_entry = get_conversation_memory_entry(normalized_entry_id, normalized_conversation_id)
    if not current_entry:
        return False

    with get_db() as conn:
        cursor = conn.execute(
            "DELETE FROM conversation_memory WHERE id = ? AND conversation_id = ?",
            (normalized_entry_id, normalized_conversation_id),
        )
    deleted = int(cursor.rowcount or 0) > 0
    if deleted:
        record_conversation_state_mutation(
            normalized_conversation_id,
            source_message_id=_normalize_state_mutation_source_message_id((mutation_context or {}).get("source_message_id")),
            target_kind=STATE_MUTATION_TARGET_CONVERSATION_MEMORY,
            target_key=str(current_entry.get("key") or "").strip(),
            operation=STATE_MUTATION_OPERATION_DELETE,
            before_value=dict(current_entry),
            after_value=None,
        )
    return deleted


def _normalize_state_mutation_target_kind(value: str) -> str:
    normalized = str(value or "").strip()
    if normalized not in STATE_MUTATION_TARGET_KINDS:
        raise ValueError(f"Unsupported state mutation target kind: {value!r}")
    return normalized


def _normalize_state_mutation_operation(value: str) -> str:
    normalized = str(value or "").strip()
    if normalized not in STATE_MUTATION_OPERATIONS:
        raise ValueError(f"Unsupported state mutation operation: {value!r}")
    return normalized


def _normalize_state_mutation_target_key(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError("State mutation target key is required.")
    return normalized[:200]


def _normalize_state_mutation_source_message_id(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return None
    return normalized if normalized > 0 else None


def serialize_state_mutation_value(value) -> str | None:
    if value is None:
        return None
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return json.dumps(str(value), ensure_ascii=False, separators=(",", ":"))


def parse_state_mutation_value(raw_value):
    if raw_value is None:
        return None
    if isinstance(raw_value, (dict, list, int, float, bool)):
        return raw_value
    if isinstance(raw_value, str):
        stripped = raw_value.strip()
        if not stripped:
            return ""
        try:
            return json.loads(stripped)
        except Exception:
            return raw_value
    try:
        return json.loads(raw_value)
    except Exception:
        return str(raw_value)


def record_conversation_state_mutation(
    conversation_id: int,
    *,
    source_message_id: int | None = None,
    target_kind: str,
    target_key: str,
    operation: str,
    before_value=None,
    after_value=None,
) -> dict | None:
    normalized_conversation_id = int(conversation_id or 0)
    if normalized_conversation_id <= 0:
        return None

    normalized_target_kind = _normalize_state_mutation_target_kind(target_kind)
    normalized_target_key = _normalize_state_mutation_target_key(target_key)
    normalized_operation = _normalize_state_mutation_operation(operation)
    normalized_source_message_id = _normalize_state_mutation_source_message_id(source_message_id)

    with get_db() as conn:
        cursor = conn.execute(
            """INSERT INTO conversation_state_mutations (
                   conversation_id, source_message_id, target_kind, target_key,
                   operation, before_value, after_value
               ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                normalized_conversation_id,
                normalized_source_message_id,
                normalized_target_kind,
                normalized_target_key,
                normalized_operation,
                serialize_state_mutation_value(before_value),
                serialize_state_mutation_value(after_value),
            ),
        )
    return {
        "id": int(cursor.lastrowid or 0),
        "conversation_id": normalized_conversation_id,
        "source_message_id": normalized_source_message_id,
        "target_kind": normalized_target_kind,
        "target_key": normalized_target_key,
        "operation": normalized_operation,
    }


def _state_mutation_target_identity(row) -> tuple:
    target_kind = str(row["target_kind"] or "").strip()
    target_key = str(row["target_key"] or "").strip()
    if target_kind == STATE_MUTATION_TARGET_CONVERSATION_MEMORY:
        return (target_kind, int(row["conversation_id"] or 0), target_key)
    return (target_kind, target_key)


def _load_state_mutation_history_for_target(conn, target_identity: tuple) -> list[dict]:
    if not target_identity:
        return []

    if target_identity[0] == STATE_MUTATION_TARGET_CONVERSATION_MEMORY:
        _target_kind, target_conversation_id, target_key = target_identity
        rows = conn.execute(
            """SELECT id, conversation_id, source_message_id, target_kind, target_key,
                      operation, before_value, after_value, reverted_at, created_at
               FROM conversation_state_mutations
               WHERE target_kind = ? AND conversation_id = ? AND target_key = ?
               ORDER BY id ASC""",
            (STATE_MUTATION_TARGET_CONVERSATION_MEMORY, int(target_conversation_id), str(target_key)),
        ).fetchall()
    else:
        target_kind, target_key = target_identity
        rows = conn.execute(
            """SELECT id, conversation_id, source_message_id, target_kind, target_key,
                      operation, before_value, after_value, reverted_at, created_at
               FROM conversation_state_mutations
               WHERE target_kind = ? AND target_key = ?
               ORDER BY id ASC""",
            (str(target_kind), str(target_key)),
        ).fetchall()
    return [dict(row) for row in rows]


def _extract_scratchpad_mutation_content(value) -> str:
    if isinstance(value, dict):
        return normalize_scratchpad_text(value.get("content", ""))
    return normalize_scratchpad_text(value)


def _extract_scratchpad_appended_notes(value) -> list[str]:
    if not isinstance(value, dict):
        return []
    notes = value.get("appended_notes") if isinstance(value.get("appended_notes"), list) else []
    normalized_notes = []
    seen_notes = set()
    for raw_note in notes:
        normalized_note = " ".join(str(raw_note or "").strip().split())
        if not normalized_note or normalized_note in seen_notes:
            continue
        seen_notes.add(normalized_note)
        normalized_notes.append(normalized_note)
    return normalized_notes


def _replay_scratchpad_state(baseline_value, remaining_mutations: list[dict]) -> dict:
    content = _extract_scratchpad_mutation_content(baseline_value)
    for mutation in remaining_mutations:
        operation = str(mutation.get("operation") or "").strip()
        after_value = parse_state_mutation_value(mutation.get("after_value"))
        if operation == STATE_MUTATION_OPERATION_REPLACE:
            content = _extract_scratchpad_mutation_content(after_value)
            continue
        if operation != STATE_MUTATION_OPERATION_APPEND:
            continue
        current_lines = content.splitlines() if content else []
        current_set = set(current_lines)
        for note in _extract_scratchpad_appended_notes(after_value):
            if note in current_set:
                continue
            current_lines.append(note)
            current_set.add(note)
        content = normalize_scratchpad_text("\n".join(current_lines))
    return {"content": content}


def _replay_generic_state(baseline_value, remaining_mutations: list[dict]):
    state = baseline_value
    for mutation in remaining_mutations:
        operation = str(mutation.get("operation") or "").strip()
        after_value = parse_state_mutation_value(mutation.get("after_value"))
        if operation == STATE_MUTATION_OPERATION_DELETE:
            state = None
            continue
        state = after_value
    return state


def _apply_replayed_state_to_target(conn, target_identity: tuple, next_state) -> None:
    if not target_identity:
        return

    target_kind = target_identity[0]
    if target_kind == STATE_MUTATION_TARGET_SCRATCHPAD_SECTION:
        _target_kind, section_id = target_identity
        normalized_section_id = normalize_scratchpad_section_id(section_id)
        section_key = SCRATCHPAD_SECTION_SETTING_KEYS[normalized_section_id]
        section_content = _extract_scratchpad_mutation_content(next_state)
        _upsert_app_setting(conn, section_key, section_content)
        if normalized_section_id == SCRATCHPAD_DEFAULT_SECTION:
            _upsert_app_setting(conn, "scratchpad", "")
        return

    if target_kind == STATE_MUTATION_TARGET_USER_PROFILE:
        _target_kind, profile_key = target_identity
        conn.execute("DELETE FROM user_profile WHERE key = ?", (str(profile_key),))
        if not isinstance(next_state, dict):
            return
        value = _normalize_user_profile_value(next_state.get("value"))
        if not value:
            return
        conn.execute(
            """INSERT INTO user_profile (key, value, confidence, source, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                str(next_state.get("key") or profile_key),
                value,
                float(next_state.get("confidence") or 0.0),
                str(next_state.get("source") or "manual"),
                str(next_state.get("updated_at") or "").strip()
                or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            ),
        )
        return

    if target_kind == STATE_MUTATION_TARGET_CONVERSATION_MEMORY:
        _target_kind, target_conversation_id, memory_key = target_identity
        conn.execute(
            "DELETE FROM conversation_memory WHERE conversation_id = ? AND key = ?",
            (int(target_conversation_id), str(memory_key)),
        )
        if not isinstance(next_state, dict):
            return
        conn.execute(
            """INSERT INTO conversation_memory (id, conversation_id, message_id, entry_type, key, value, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                int(next_state.get("id") or 0) or None,
                int(next_state.get("conversation_id") or target_conversation_id),
                _normalize_state_mutation_source_message_id(next_state.get("message_id")),
                _normalize_conversation_memory_entry_type(next_state.get("entry_type") or "task_context"),
                _normalize_conversation_memory_key(next_state.get("key") or memory_key),
                _normalize_conversation_memory_value(next_state.get("value") or ""),
                str(next_state.get("created_at") or "").strip()
                or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            ),
        )


def revert_conversation_state_mutations(
    conversation_id: int,
    *,
    source_message_ids: Iterable[int] | None = None,
) -> dict:
    normalized_conversation_id = int(conversation_id or 0)
    if normalized_conversation_id <= 0:
        return {"reverted_count": 0, "targets": []}

    normalized_source_message_ids = None
    if source_message_ids is not None:
        normalized_source_message_ids = [
            int(message_id)
            for message_id in source_message_ids
            if int(message_id or 0) > 0
        ]
        if not normalized_source_message_ids:
            return {"reverted_count": 0, "targets": []}

    with get_db() as conn:
        query = [
            "SELECT id, conversation_id, source_message_id, target_kind, target_key, operation, before_value, after_value, reverted_at, created_at",
            "FROM conversation_state_mutations",
            "WHERE conversation_id = ? AND reverted_at IS NULL",
        ]
        params: list[object] = [normalized_conversation_id]
        if normalized_source_message_ids is not None:
            placeholders = ", ".join("?" for _ in normalized_source_message_ids)
            query.append(f"AND source_message_id IN ({placeholders})")
            params.extend(normalized_source_message_ids)
        query.append("ORDER BY id DESC")
        target_rows = [dict(row) for row in conn.execute("\n".join(query), tuple(params)).fetchall()]
        if not target_rows:
            return {"reverted_count": 0, "targets": []}

        rows_by_target: dict[tuple, list[dict]] = {}
        for row in target_rows:
            rows_by_target.setdefault(_state_mutation_target_identity(row), []).append(row)

        reverted_ids: list[int] = []
        affected_targets: list[dict] = []
        reverted_at = "datetime('now')"

        for target_identity, rollback_rows in rows_by_target.items():
            history_rows = _load_state_mutation_history_for_target(conn, target_identity)
            if not history_rows:
                continue

            rollback_ids = {int(row["id"] or 0) for row in rollback_rows if int(row["id"] or 0) > 0}
            remaining_rows = [
                row
                for row in history_rows
                if row.get("reverted_at") in (None, "") and int(row.get("id") or 0) not in rollback_ids
            ]
            baseline_value = parse_state_mutation_value(history_rows[0].get("before_value"))
            target_kind = target_identity[0]
            if target_kind == STATE_MUTATION_TARGET_SCRATCHPAD_SECTION:
                next_state = _replay_scratchpad_state(baseline_value, remaining_rows)
            else:
                next_state = _replay_generic_state(baseline_value, remaining_rows)
            _apply_replayed_state_to_target(conn, target_identity, next_state)
            reverted_ids.extend(sorted(rollback_ids))
            affected_targets.append(
                {
                    "target_kind": target_kind,
                    "target_key": target_identity[-1],
                    "reverted_mutation_count": len(rollback_ids),
                }
            )

        if reverted_ids:
            placeholders = ", ".join("?" for _ in reverted_ids)
            conn.execute(
                f"UPDATE conversation_state_mutations SET reverted_at = datetime('now') WHERE id IN ({placeholders})",
                tuple(reverted_ids),
            )

    return {
        "reverted_count": len(reverted_ids),
        "targets": affected_targets,
    }


def _build_user_profile_fact_key(value: str) -> str:
    normalized_value = _normalize_user_profile_value(value)
    digest = hashlib.sha1(normalized_value.encode("utf-8")).hexdigest()
    return f"fact:{digest}"


def _is_user_profile_fact_candidate(value: str) -> bool:
    normalized_value = _normalize_user_profile_value(value).casefold()
    if not normalized_value:
        return False
    keywords = (
        "the user",
        "user prefers",
        "user wants",
        "user is",
        "user uses",
        "user works",
        "prefers",
        "likes",
        "kullanıcı",
        "kullanici",
        "tercih",
        "istiyor",
        "kullanıyor",
        "çalışıyor",
        "works on",
        "working on",
        "name is",
        "adı",
    )
    return any(keyword in normalized_value for keyword in keywords)


def upsert_user_profile_entry(
    key: str,
    value: str,
    confidence: float = 1.0,
    source: str = "manual",
    *,
    conversation_id: int | None = None,
    source_message_id: int | None = None,
) -> dict | None:
    normalized_key = str(key or "").strip()[:120]
    normalized_value = _normalize_user_profile_value(value)
    normalized_source = str(source or "").strip()[:80] or "manual"
    try:
        normalized_confidence = float(confidence)
    except (TypeError, ValueError):
        normalized_confidence = 1.0
    normalized_confidence = max(0.0, min(1.0, normalized_confidence))

    if not normalized_key or not normalized_value:
        return None

    with get_db() as conn:
        previous_row = conn.execute(
            "SELECT key, value, confidence, source, updated_at FROM user_profile WHERE key = ?",
            (normalized_key,),
        ).fetchone()
        conn.execute(
            """INSERT INTO user_profile (key, value, confidence, source, updated_at)
               VALUES (?, ?, ?, ?, datetime('now'))
               ON CONFLICT(key) DO UPDATE SET
                   value = excluded.value,
                   confidence = excluded.confidence,
                   source = excluded.source,
                   updated_at = datetime('now')""",
            (normalized_key, normalized_value, normalized_confidence, normalized_source),
        )
        updated_row = conn.execute(
            "SELECT key, value, confidence, source, updated_at FROM user_profile WHERE key = ?",
            (normalized_key,),
        ).fetchone()
    entry = {
        "key": normalized_key,
        "value": normalized_value,
        "confidence": normalized_confidence,
        "source": normalized_source,
    }
    if updated_row:
        entry["updated_at"] = updated_row["updated_at"]

    before_snapshot = dict(previous_row) if previous_row else None
    if int(conversation_id or 0) > 0 and before_snapshot != entry:
        record_conversation_state_mutation(
            int(conversation_id),
            source_message_id=_normalize_state_mutation_source_message_id(source_message_id),
            target_kind=STATE_MUTATION_TARGET_USER_PROFILE,
            target_key=normalized_key,
            operation=STATE_MUTATION_OPERATION_UPSERT,
            before_value=before_snapshot,
            after_value=entry,
        )
    return entry


def upsert_user_profile_facts(
    facts: list[str],
    confidence: float = 0.8,
    source: str = "summary_extraction",
    *,
    conversation_id: int | None = None,
    source_message_id: int | None = None,
) -> list[dict]:
    stored: list[dict] = []
    for raw_fact in facts or []:
        normalized_fact = _normalize_user_profile_value(raw_fact)
        if not normalized_fact or not _is_user_profile_fact_candidate(normalized_fact):
            continue
        entry = upsert_user_profile_entry(
            _build_user_profile_fact_key(normalized_fact),
            normalized_fact,
            confidence=confidence,
            source=source,
            conversation_id=conversation_id,
            source_message_id=source_message_id,
        )
        if entry is not None:
            stored.append(entry)
    return stored


def get_user_profile_entries(limit: int | None = None) -> list[dict]:
    query = "SELECT key, value, confidence, source, updated_at FROM user_profile ORDER BY confidence DESC, updated_at DESC, key ASC"
    params: tuple[object, ...] = ()
    if isinstance(limit, int) and limit > 0:
        query += " LIMIT ?"
        params = (limit,)
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [
        {
            "key": str(row["key"] or "").strip(),
            "value": str(row["value"] or "").strip(),
            "confidence": float(row["confidence"] or 0.0),
            "source": str(row["source"] or "").strip(),
            "updated_at": str(row["updated_at"] or "").strip(),
        }
        for row in rows
        if str(row["key"] or "").strip() and str(row["value"] or "").strip()
    ]


def build_user_profile_system_context(max_tokens: int = 500, limit: int = 12) -> str | None:
    if max_tokens <= 0:
        return None

    entries = get_user_profile_entries(limit=limit)
    if not entries:
        return None

    lines: list[str] = []
    total_tokens = 0
    for entry in entries:
        line = f"- {entry['value']}"
        line_tokens = estimate_text_tokens(line)
        if lines and total_tokens + line_tokens > max_tokens:
            break
        if not lines and line_tokens > max_tokens:
            break
        lines.append(line)
        total_tokens += line_tokens
    if not lines:
        return None
    return "\n".join(lines)


def _guess_extension_for_mime_type(mime_type: str) -> str:
    normalized = str(mime_type or "").strip().lower()
    return {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
    }.get(normalized, "")


def _normalize_initial_image_analysis(value) -> dict | None:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            return None
    if not isinstance(value, dict):
        return None

    cleaned = {}
    analysis_method = str(value.get("analysis_method") or "").strip()
    if analysis_method:
        cleaned["analysis_method"] = analysis_method[:40]

    for key in ("ocr_text", "vision_summary", "assistant_guidance"):
        text = str(value.get(key) or "").strip()
        if text:
            cleaned[key] = text[:CONTENT_MAX_CHARS]

    key_points = value.get("key_points") if isinstance(value.get("key_points"), list) else []
    normalized_points = []
    for point in key_points[:8]:
        point_text = str(point or "").strip()
        if point_text and point_text not in normalized_points:
            normalized_points.append(point_text[:300])
    if normalized_points:
        cleaned["key_points"] = normalized_points

    return cleaned or None


def create_image_asset(conversation_id: int, filename: str, mime_type: str, image_bytes: bytes) -> dict:
    normalized_filename = os.path.basename(str(filename or "").strip())[:255]
    normalized_mime_type = str(mime_type or "").strip().lower()[:120]
    if not conversation_id:
        raise ValueError("conversation_id is required to persist an image.")
    if not normalized_filename:
        raise ValueError("filename is required.")
    if not image_bytes:
        raise ValueError("image_bytes is required.")

    image_id = uuid4().hex
    extension = _guess_extension_for_mime_type(normalized_mime_type)
    relative_path = os.path.join(image_id[:2], f"{image_id}{extension}")
    absolute_path = os.path.join(IMAGE_STORAGE_DIR, relative_path)
    os.makedirs(os.path.dirname(absolute_path), exist_ok=True)

    with open(absolute_path, "wb") as handle:
        handle.write(image_bytes)

    with get_db() as conn:
        conn.execute(
            """INSERT INTO image_assets (
                   image_id, conversation_id, filename, mime_type, storage_path
               ) VALUES (?, ?, ?, ?, ?)""",
            (image_id, conversation_id, normalized_filename, normalized_mime_type, absolute_path),
        )
        row = conn.execute(
            """SELECT image_id, conversation_id, message_id, filename, mime_type,
                      storage_path, initial_analysis, created_at
               FROM image_assets WHERE image_id = ?""",
            (image_id,),
        ).fetchone()
    return image_asset_row_to_dict(row)


def update_image_asset(image_id: str, *, message_id: int | None = None, initial_analysis: dict | None = None) -> dict | None:
    normalized_image_id = str(image_id or "").strip()
    if not normalized_image_id:
        return None

    assignments = []
    params = []
    if message_id is not None:
        assignments.append("message_id = ?")
        params.append(int(message_id))
    normalized_analysis = _normalize_initial_image_analysis(initial_analysis)
    if normalized_analysis is not None:
        assignments.append("initial_analysis = ?")
        params.append(json.dumps(normalized_analysis, ensure_ascii=False))

    if assignments:
        with get_db() as conn:
            conn.execute(
                f"UPDATE image_assets SET {', '.join(assignments)} WHERE image_id = ?",
                (*params, normalized_image_id),
            )

    return get_image_asset(normalized_image_id)


def image_asset_row_to_dict(row) -> dict | None:
    if not row:
        return None
    return {
        "image_id": row["image_id"],
        "conversation_id": row["conversation_id"],
        "message_id": row["message_id"],
        "filename": row["filename"],
        "mime_type": row["mime_type"],
        "storage_path": row["storage_path"],
        "initial_analysis": _normalize_initial_image_analysis(row["initial_analysis"]),
        "created_at": row["created_at"],
    }


def get_image_asset(image_id: str, conversation_id: int | None = None) -> dict | None:
    normalized_image_id = str(image_id or "").strip()
    if not normalized_image_id:
        return None
    query = (
        "SELECT image_id, conversation_id, message_id, filename, mime_type, storage_path, initial_analysis, created_at "
        "FROM image_assets WHERE image_id = ?"
    )
    params = [normalized_image_id]
    if conversation_id is not None:
        query += " AND conversation_id = ?"
        params.append(int(conversation_id))

    with get_db() as conn:
        row = conn.execute(query, tuple(params)).fetchone()
    return image_asset_row_to_dict(row)


def get_latest_conversation_image_asset(conversation_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            """SELECT image_id, conversation_id, message_id, filename, mime_type, storage_path, initial_analysis, created_at
               FROM image_assets
               WHERE conversation_id = ?
               ORDER BY created_at DESC, image_id DESC
               LIMIT 1""",
            (conversation_id,),
        ).fetchone()
    return image_asset_row_to_dict(row)


def read_image_asset_bytes(image_id: str, conversation_id: int | None = None) -> tuple[dict | None, bytes | None]:
    asset = get_image_asset(image_id, conversation_id=conversation_id)
    if not asset:
        return None, None
    storage_path = str(asset.get("storage_path") or "").strip()
    if not storage_path or not os.path.isfile(storage_path):
        return asset, None
    with open(storage_path, "rb") as handle:
        return asset, handle.read()


def delete_conversation_image_assets(conversation_id: int) -> list[str]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT storage_path FROM image_assets WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchall()
        conn.execute("DELETE FROM image_assets WHERE conversation_id = ?", (conversation_id,))

    deleted_paths = []
    for row in rows:
        storage_path = str(row["storage_path"] or "").strip()
        if not storage_path:
            continue
        try:
            os.remove(storage_path)
            deleted_paths.append(storage_path)
        except FileNotFoundError:
            continue
        except OSError:
            continue

        parent = Path(storage_path).parent
        root = Path(IMAGE_STORAGE_DIR)
        while parent != root and parent.exists():
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent

    return deleted_paths


def delete_image_asset(image_id: str, conversation_id: int | None = None) -> bool:
    asset = get_image_asset(image_id, conversation_id=conversation_id)
    if not asset:
        return False

    with get_db() as conn:
        conn.execute("DELETE FROM image_assets WHERE image_id = ?", (asset["image_id"],))

    storage_path = str(asset.get("storage_path") or "").strip()
    if storage_path:
        try:
            os.remove(storage_path)
        except FileNotFoundError:
            pass
        except OSError:
            pass
    return True


# --- File asset CRUD ---------------------------------------------------

def _guess_extension_for_document_mime(mime_type: str) -> str:
    normalized = str(mime_type or "").strip().lower()
    return {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "application/pdf": ".pdf",
        "text/plain": ".txt",
        "text/csv": ".csv",
        "text/markdown": ".md",
    }.get(normalized, "")


def create_file_asset(conversation_id: int, filename: str, mime_type: str, doc_bytes: bytes, extracted_text: str | None = None) -> dict:
    normalized_filename = os.path.basename(str(filename or "").strip())[:255]
    normalized_mime_type = str(mime_type or "").strip().lower()[:120]
    if not conversation_id:
        raise ValueError("conversation_id is required to persist a file.")
    if not normalized_filename:
        raise ValueError("filename is required.")
    if not doc_bytes:
        raise ValueError("doc_bytes is required.")

    file_id = uuid4().hex
    extension = _guess_extension_for_document_mime(normalized_mime_type)
    relative_path = os.path.join(file_id[:2], f"{file_id}{extension}")
    absolute_path = os.path.join(DOCUMENT_STORAGE_DIR, relative_path)
    os.makedirs(os.path.dirname(absolute_path), exist_ok=True)

    with open(absolute_path, "wb") as handle:
        handle.write(doc_bytes)

    with get_db() as conn:
        conn.execute(
            """INSERT INTO file_assets (
                   file_id, conversation_id, filename, mime_type, storage_path, extracted_text
               ) VALUES (?, ?, ?, ?, ?, ?)""",
            (file_id, conversation_id, normalized_filename, normalized_mime_type, absolute_path, extracted_text),
        )
        row = conn.execute(
            """SELECT file_id, conversation_id, message_id, filename, mime_type,
                      storage_path, extracted_text, created_at
               FROM file_assets WHERE file_id = ?""",
            (file_id,),
        ).fetchone()
    return _file_asset_row_to_dict(row)


def update_file_asset(file_id: str, *, message_id: int | None = None) -> dict | None:
    normalized_id = str(file_id or "").strip()
    if not normalized_id:
        return None
    assignments = []
    params = []
    if message_id is not None:
        assignments.append("message_id = ?")
        params.append(int(message_id))
    if assignments:
        with get_db() as conn:
            conn.execute(
                f"UPDATE file_assets SET {', '.join(assignments)} WHERE file_id = ?",
                (*params, normalized_id),
            )
    return get_file_asset(normalized_id)


def _file_asset_row_to_dict(row) -> dict | None:
    if not row:
        return None
    return {
        "file_id": row["file_id"],
        "conversation_id": row["conversation_id"],
        "message_id": row["message_id"],
        "filename": row["filename"],
        "mime_type": row["mime_type"],
        "storage_path": row["storage_path"],
        "extracted_text": row["extracted_text"],
        "created_at": row["created_at"],
    }


def get_file_asset(file_id: str, conversation_id: int | None = None) -> dict | None:
    normalized_id = str(file_id or "").strip()
    if not normalized_id:
        return None
    query = (
        "SELECT file_id, conversation_id, message_id, filename, mime_type, storage_path, extracted_text, created_at "
        "FROM file_assets WHERE file_id = ?"
    )
    params = [normalized_id]
    if conversation_id is not None:
        query += " AND conversation_id = ?"
        params.append(int(conversation_id))
    with get_db() as conn:
        row = conn.execute(query, tuple(params)).fetchone()
    return _file_asset_row_to_dict(row)


def delete_file_asset(file_id: str, conversation_id: int | None = None) -> bool:
    asset = get_file_asset(file_id, conversation_id=conversation_id)
    if not asset:
        return False
    with get_db() as conn:
        conn.execute("DELETE FROM file_assets WHERE file_id = ?", (asset["file_id"],))
    storage_path = str(asset.get("storage_path") or "").strip()
    if storage_path:
        try:
            os.remove(storage_path)
        except (FileNotFoundError, OSError):
            pass
    return True


def delete_conversation_file_assets(conversation_id: int) -> list[str]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT storage_path FROM file_assets WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchall()
        conn.execute("DELETE FROM file_assets WHERE conversation_id = ?", (conversation_id,))

    deleted_paths = []
    for row in rows:
        storage_path = str(row["storage_path"] or "").strip()
        if not storage_path:
            continue
        try:
            os.remove(storage_path)
            deleted_paths.append(storage_path)
        except (FileNotFoundError, OSError):
            continue
        parent = Path(storage_path).parent
        root = Path(DOCUMENT_STORAGE_DIR)
        while parent != root and parent.exists():
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
    return deleted_paths


def create_video_asset(
    conversation_id: int,
    *,
    source_url: str,
    source_video_id: str = "",
    title: str = "",
    transcript_text: str,
    transcript_language: str = "",
    duration_seconds: int | None = None,
    platform: str = "youtube",
) -> dict:
    normalized_source_url = str(source_url or "").strip()[:2000]
    normalized_source_video_id = str(source_video_id or "").strip()[:64]
    normalized_title = str(title or "").strip()[:255]
    normalized_text = str(transcript_text or "").strip()
    normalized_language = str(transcript_language or "").strip()[:40]
    normalized_platform = str(platform or "").strip().lower()[:40] or "youtube"
    try:
        normalized_duration = max(0, int(duration_seconds)) if duration_seconds is not None else None
    except (TypeError, ValueError):
        normalized_duration = None

    if not conversation_id:
        raise ValueError("conversation_id is required to persist a video transcript.")
    if not normalized_source_url:
        raise ValueError("source_url is required.")
    if not normalized_text:
        raise ValueError("transcript_text is required.")

    video_id = uuid4().hex
    with get_db() as conn:
        conn.execute(
            """INSERT INTO video_assets (
                   video_id, conversation_id, platform, source_url, source_video_id,
                   title, transcript_text, transcript_language, duration_seconds
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                video_id,
                conversation_id,
                normalized_platform,
                normalized_source_url,
                normalized_source_video_id or None,
                normalized_title or None,
                normalized_text,
                normalized_language or None,
                normalized_duration,
            ),
        )
        row = conn.execute(
            """SELECT video_id, conversation_id, message_id, platform, source_url, source_video_id,
                      title, transcript_text, transcript_language, duration_seconds, created_at
               FROM video_assets WHERE video_id = ?""",
            (video_id,),
        ).fetchone()
    return _video_asset_row_to_dict(row)


def update_video_asset(video_id: str, *, message_id: int | None = None) -> dict | None:
    normalized_id = str(video_id or "").strip()
    if not normalized_id:
        return None
    if message_id is not None:
        with get_db() as conn:
            conn.execute(
                "UPDATE video_assets SET message_id = ? WHERE video_id = ?",
                (int(message_id), normalized_id),
            )
    return get_video_asset(normalized_id)


def _video_asset_row_to_dict(row) -> dict | None:
    if not row:
        return None
    return {
        "video_id": row["video_id"],
        "conversation_id": row["conversation_id"],
        "message_id": row["message_id"],
        "platform": row["platform"],
        "source_url": row["source_url"],
        "source_video_id": row["source_video_id"],
        "title": row["title"],
        "transcript_text": row["transcript_text"],
        "transcript_language": row["transcript_language"],
        "duration_seconds": row["duration_seconds"],
        "created_at": row["created_at"],
    }


def get_video_asset(video_id: str, conversation_id: int | None = None) -> dict | None:
    normalized_id = str(video_id or "").strip()
    if not normalized_id:
        return None
    query = (
        "SELECT video_id, conversation_id, message_id, platform, source_url, source_video_id, "
        "title, transcript_text, transcript_language, duration_seconds, created_at "
        "FROM video_assets WHERE video_id = ?"
    )
    params = [normalized_id]
    if conversation_id is not None:
        query += " AND conversation_id = ?"
        params.append(int(conversation_id))
    with get_db() as conn:
        row = conn.execute(query, tuple(params)).fetchone()
    return _video_asset_row_to_dict(row)


def delete_video_asset(video_id: str, conversation_id: int | None = None) -> bool:
    asset = get_video_asset(video_id, conversation_id=conversation_id)
    if not asset:
        return False
    with get_db() as conn:
        conn.execute("DELETE FROM video_assets WHERE video_id = ?", (asset["video_id"],))
    return True


def delete_conversation_video_assets(conversation_id: int) -> list[str]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT video_id FROM video_assets WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchall()
        conn.execute("DELETE FROM video_assets WHERE conversation_id = ?", (conversation_id,))
    return [str(row["video_id"] or "").strip() for row in rows if str(row["video_id"] or "").strip()]


def _strip_private_message_metadata_fields(
    metadata: dict | None,
    *,
    include_private_fields: bool = False,
) -> dict:
    if not isinstance(metadata, dict):
        return {}
    cleaned = dict(metadata)
    if not include_private_fields:
        cleaned.pop("reasoning_content", None)
        cleaned.pop("_edit_replay_deleted", None)
    return cleaned


def parse_message_metadata(raw_metadata, *, include_private_fields: bool = False) -> dict:
    if isinstance(raw_metadata, dict):
        return _strip_private_message_metadata_fields(
            raw_metadata,
            include_private_fields=include_private_fields,
        )
    if not raw_metadata:
        return {}
    try:
        parsed = json.loads(raw_metadata)
    except Exception:
        return {}
    return _strip_private_message_metadata_fields(
        parsed if isinstance(parsed, dict) else {},
        include_private_fields=include_private_fields,
    )


def _normalize_message_attachment(entry) -> dict | None:
    if not isinstance(entry, dict):
        return None

    kind = str(entry.get("kind") or "").strip().lower()
    if kind not in {"image", "document", "video"}:
        return None

    cleaned = {"kind": kind}
    if kind == "image":
        image_id = str(entry.get("image_id") or "").strip()[:64]
        image_name = str(entry.get("image_name") or "").strip()[:255]
        image_mime_type = str(entry.get("image_mime_type") or "").strip()[:120]
        analysis_method = str(entry.get("analysis_method") or "").strip()[:40]
        ocr_text = str(entry.get("ocr_text") or "").strip()[:CONTENT_MAX_CHARS]
        vision_summary = str(entry.get("vision_summary") or "").strip()[:CONTENT_MAX_CHARS]
        assistant_guidance = str(entry.get("assistant_guidance") or "").strip()[:CONTENT_MAX_CHARS]
        key_points = entry.get("key_points") if isinstance(entry.get("key_points"), list) else []

        if image_id:
            cleaned["image_id"] = image_id
        if image_name:
            cleaned["image_name"] = image_name
        if image_mime_type:
            cleaned["image_mime_type"] = image_mime_type
        if analysis_method:
            cleaned["analysis_method"] = analysis_method
        if ocr_text:
            cleaned["ocr_text"] = ocr_text
        if vision_summary:
            cleaned["vision_summary"] = vision_summary
        if assistant_guidance:
            cleaned["assistant_guidance"] = assistant_guidance
        if key_points:
            normalized_points = []
            for point in key_points[:8]:
                point_text = str(point or "").strip()
                if point_text and point_text not in normalized_points:
                    normalized_points.append(point_text[:300])
            if normalized_points:
                cleaned["key_points"] = normalized_points

        if not cleaned.get("image_id") and not cleaned.get("image_name"):
            return None
        return cleaned

    if kind == "video":
        video_id = str(entry.get("video_id") or "").strip()[:64]
        video_title = str(entry.get("video_title") or "").strip()[:255]
        video_url = str(entry.get("video_url") or "").strip()[:2000]
        video_platform = str(entry.get("video_platform") or "").strip()[:40]
        transcript_context_block = str(entry.get("transcript_context_block") or "").strip()[:CONTENT_MAX_CHARS]
        transcript_language = str(entry.get("transcript_language") or "").strip()[:40]

        if video_id:
            cleaned["video_id"] = video_id
        if video_title:
            cleaned["video_title"] = video_title
        if video_url:
            cleaned["video_url"] = video_url
        if video_platform:
            cleaned["video_platform"] = video_platform
        if transcript_context_block:
            cleaned["transcript_context_block"] = transcript_context_block
        if transcript_language:
            cleaned["transcript_language"] = transcript_language
        if entry.get("transcript_text_truncated") is True:
            cleaned["transcript_text_truncated"] = True

        if not cleaned.get("video_id") and not cleaned.get("video_url"):
            return None
        return cleaned

    file_id = str(entry.get("file_id") or "").strip()[:64]
    file_name = str(entry.get("file_name") or "").strip()[:255]
    file_mime_type = str(entry.get("file_mime_type") or "").strip()[:120]
    file_context_block = str(entry.get("file_context_block") or "").strip()[:CONTENT_MAX_CHARS]
    submission_mode = str(entry.get("submission_mode") or "").strip().lower()[:20]
    canvas_mode = str(entry.get("canvas_mode") or "").strip().lower()[:40]
    visual_page_image_ids = entry.get("visual_page_image_ids") if isinstance(entry.get("visual_page_image_ids"), list) else []
    visual_page_numbers = entry.get("visual_page_numbers") if isinstance(entry.get("visual_page_numbers"), list) else []
    visual_failed_pages = entry.get("visual_failed_pages") if isinstance(entry.get("visual_failed_pages"), list) else []
    visual_page_count = entry.get("visual_page_count")
    visual_total_page_count = entry.get("visual_total_page_count")
    visual_page_limit = entry.get("visual_page_limit")

    if file_id:
        cleaned["file_id"] = file_id
    if file_name:
        cleaned["file_name"] = file_name
    if file_mime_type:
        cleaned["file_mime_type"] = file_mime_type
    if entry.get("file_text_truncated") is True:
        cleaned["file_text_truncated"] = True
    if file_context_block:
        cleaned["file_context_block"] = file_context_block
    if submission_mode in {"text", "visual"}:
        cleaned["submission_mode"] = submission_mode
    if canvas_mode:
        cleaned["canvas_mode"] = canvas_mode
    normalized_visual_page_ids = []
    for value in visual_page_image_ids[:8]:
        image_id = str(value or "").strip()[:64]
        if image_id and image_id not in normalized_visual_page_ids:
            normalized_visual_page_ids.append(image_id)
    if normalized_visual_page_ids:
        cleaned["visual_page_image_ids"] = normalized_visual_page_ids

    normalized_visual_page_numbers = []
    for value in visual_page_numbers[:16]:
        try:
            page_number = int(value)
        except (TypeError, ValueError):
            continue
        if page_number < 1 or page_number in normalized_visual_page_numbers:
            continue
        normalized_visual_page_numbers.append(page_number)
    if normalized_visual_page_numbers:
        cleaned["visual_page_numbers"] = normalized_visual_page_numbers

    normalized_visual_failed_pages = []
    for value in visual_failed_pages[:16]:
        try:
            page_number = int(value)
        except (TypeError, ValueError):
            continue
        if page_number < 1 or page_number in normalized_visual_failed_pages:
            continue
        normalized_visual_failed_pages.append(page_number)
    if normalized_visual_failed_pages:
        cleaned["visual_failed_pages"] = normalized_visual_failed_pages

    if entry.get("visual_pages_partial") is True:
        cleaned["visual_pages_partial"] = True

    try:
        page_count = int(visual_page_count)
    except (TypeError, ValueError):
        page_count = 0
    if page_count > 0:
        cleaned["visual_page_count"] = min(page_count, len(normalized_visual_page_ids) or page_count)
    try:
        total_page_count = int(visual_total_page_count)
    except (TypeError, ValueError):
        total_page_count = 0
    if total_page_count > 0:
        cleaned["visual_total_page_count"] = max(total_page_count, cleaned.get("visual_page_count") or 0)
    try:
        normalized_page_limit = int(visual_page_limit)
    except (TypeError, ValueError):
        normalized_page_limit = 0
    if normalized_page_limit > 0:
        cleaned["visual_page_limit"] = normalized_page_limit
    if entry.get("visual_pages_truncated") is True:
        cleaned["visual_pages_truncated"] = True

    if not cleaned.get("file_id") and not cleaned.get("file_name"):
        return None
    return cleaned


def extract_message_attachments(metadata: dict | None) -> list[dict]:
    source = metadata if isinstance(metadata, dict) else {}
    normalized = []
    seen = set()

    def append_attachment(raw_attachment) -> None:
        cleaned = _normalize_message_attachment(raw_attachment)
        if not cleaned:
            return
        if cleaned["kind"] == "image":
            dedupe_key = (
                "image",
                cleaned.get("image_id") or "",
                cleaned.get("image_name") or "",
            )
        elif cleaned["kind"] == "video":
            dedupe_key = (
                "video",
                cleaned.get("video_id") or "",
                cleaned.get("video_url") or "",
            )
        else:
            dedupe_key = (
                "document",
                cleaned.get("file_id") or "",
                cleaned.get("file_name") or "",
            )
        if dedupe_key in seen:
            return
        seen.add(dedupe_key)
        normalized.append(cleaned)

    raw_attachments = source.get("attachments") if isinstance(source.get("attachments"), list) else []
    for entry in raw_attachments[:24]:
        append_attachment(entry)

    legacy_image = {
        "kind": "image",
        "image_id": source.get("image_id"),
        "image_name": source.get("image_name"),
        "image_mime_type": source.get("image_mime_type"),
        "analysis_method": source.get("analysis_method"),
        "ocr_text": source.get("ocr_text"),
        "vision_summary": source.get("vision_summary"),
        "assistant_guidance": source.get("assistant_guidance"),
        "key_points": source.get("key_points"),
    }
    append_attachment(legacy_image)

    legacy_document = {
        "kind": "document",
        "file_id": source.get("file_id"),
        "file_name": source.get("file_name"),
        "file_mime_type": source.get("file_mime_type"),
        "file_text_truncated": source.get("file_text_truncated") is True,
        "file_context_block": source.get("file_context_block"),
    }
    append_attachment(legacy_document)

    legacy_video = {
        "kind": "video",
        "video_id": source.get("video_id"),
        "video_title": source.get("video_title"),
        "video_url": source.get("video_url"),
        "video_platform": source.get("video_platform"),
        "transcript_context_block": source.get("transcript_context_block"),
        "transcript_language": source.get("transcript_language"),
        "transcript_text_truncated": source.get("transcript_text_truncated") is True,
    }
    append_attachment(legacy_video)

    return normalized


def _normalize_message_tool_calls(raw_tool_calls) -> list[dict]:
    if isinstance(raw_tool_calls, str):
        try:
            raw_tool_calls = json.loads(raw_tool_calls)
        except Exception:
            return []

    if not isinstance(raw_tool_calls, list):
        return []

    normalized = []
    for entry in raw_tool_calls[:32]:
        if not isinstance(entry, dict):
            continue
        tool_id = str(entry.get("id") or "").strip()[:120]
        tool_type = str(entry.get("type") or "function").strip()[:40] or "function"
        function = entry.get("function") if isinstance(entry.get("function"), dict) else {}
        function_name = str(function.get("name") or "").strip()[:80]
        raw_arguments = _compact_canvas_tool_call_arguments(function_name, function.get("arguments"))
        if isinstance(raw_arguments, (dict, list)):
            arguments = json.dumps(raw_arguments, ensure_ascii=False)
        else:
            arguments = str(raw_arguments or "").strip()
        if not function_name:
            continue
        normalized.append(
            {
                "id": tool_id,
                "type": tool_type,
                "function": {
                    "name": function_name,
                    "arguments": arguments,
                },
            }
        )
    return normalized


def _parse_tool_call_arguments_payload(raw_arguments):
    if isinstance(raw_arguments, (dict, list)):
        return raw_arguments
    if not isinstance(raw_arguments, str):
        return raw_arguments

    normalized = raw_arguments.strip()
    if not normalized:
        return ""

    try:
        return json.loads(normalized)
    except Exception:
        return raw_arguments


def _trim_tool_call_argument_text(value, *, label: str) -> str:
    normalized = str(value or "")
    if not normalized:
        return ""

    lines = normalized.splitlines() or [normalized]
    if len(normalized) <= TOOL_CALL_CONTENT_PREVIEW_MAX_CHARS and len(lines) <= TOOL_CALL_CONTENT_PREVIEW_MAX_LINES:
        return normalized

    preview = "\n".join(lines[:TOOL_CALL_CONTENT_PREVIEW_MAX_LINES])
    if len(preview) > TOOL_CALL_CONTENT_PREVIEW_MAX_CHARS:
        preview = preview[:TOOL_CALL_CONTENT_PREVIEW_MAX_CHARS].rstrip()
    if not preview:
        return f"[TRIMMED {label}: original {len(lines)} lines, {len(normalized)} chars]"
    return f"{preview}… [TRIMMED {label}: original {len(lines)} lines, {len(normalized)} chars]"


def _trim_tool_call_argument_lines(raw_lines) -> list[str]:
    if not isinstance(raw_lines, list):
        return []

    normalized_lines = [str(item or "") for item in raw_lines]
    serialized = json.dumps(normalized_lines, ensure_ascii=False)
    if (
        len(normalized_lines) <= TOOL_CALL_LINES_PREVIEW_MAX_ITEMS
        and len(serialized) <= TOOL_CALL_LINES_PREVIEW_MAX_TOTAL_CHARS
    ):
        return normalized_lines

    preview_lines: list[str] = []
    preview_chars = 0
    for line in normalized_lines[:TOOL_CALL_LINES_PREVIEW_MAX_ITEMS]:
        clipped_line = str(line or "")
        if len(clipped_line) > TOOL_CALL_LINE_PREVIEW_MAX_CHARS:
            clipped_line = clipped_line[:TOOL_CALL_LINE_PREVIEW_MAX_CHARS].rstrip() + "…"
        projected = preview_chars + len(clipped_line)
        if preview_lines and projected > TOOL_CALL_LINES_PREVIEW_MAX_TOTAL_CHARS:
            break
        preview_lines.append(clipped_line)
        preview_chars = projected

    total_chars = sum(len(line) for line in normalized_lines)
    preview_lines.append(f"[TRIMMED canvas lines: original {len(normalized_lines)} lines, {total_chars} chars]")
    return preview_lines


def _trim_tool_call_argument_items(raw_values, *, label: str) -> list[str]:
    if not isinstance(raw_values, list):
        return []

    normalized_values = [str(item or "") for item in raw_values]
    if len(normalized_values) <= TOOL_CALL_METADATA_LIST_PREVIEW_MAX_ITEMS and all(
        len(value) <= TOOL_CALL_METADATA_ITEM_PREVIEW_MAX_CHARS for value in normalized_values
    ):
        return normalized_values

    preview_values = []
    for value in normalized_values[:TOOL_CALL_METADATA_LIST_PREVIEW_MAX_ITEMS]:
        if len(value) > TOOL_CALL_METADATA_ITEM_PREVIEW_MAX_CHARS:
            value = value[:TOOL_CALL_METADATA_ITEM_PREVIEW_MAX_CHARS].rstrip() + "…"
        preview_values.append(value)
    preview_values.append(f"[TRIMMED {label}: original {len(normalized_values)} items]")
    return preview_values


def _compact_canvas_tool_call_arguments(function_name: str, raw_arguments):
    if function_name not in CONTENT_HEAVY_CANVAS_TOOL_NAMES:
        return raw_arguments

    parsed_arguments = _parse_tool_call_arguments_payload(raw_arguments)
    if not isinstance(parsed_arguments, dict):
        return raw_arguments

    compacted = dict(parsed_arguments)
    if "content" in compacted:
        compacted["content"] = _trim_tool_call_argument_text(compacted.get("content"), label="canvas content")
    if "lines" in compacted:
        compacted["lines"] = _trim_tool_call_argument_lines(compacted.get("lines"))
    for key in ("imports", "exports", "symbols", "dependencies"):
        if key in compacted:
            compacted[key] = _trim_tool_call_argument_items(compacted.get(key), label=key)
    return compacted


def parse_message_tool_calls(raw_tool_calls) -> list[dict]:
    return _normalize_message_tool_calls(raw_tool_calls)


def serialize_message_tool_calls(tool_calls) -> str | None:
    normalized = _normalize_message_tool_calls(tool_calls)
    if not normalized:
        return None
    return json.dumps(normalized, ensure_ascii=False)


def _coerce_non_negative_int(value) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, normalized)


def _protected_breakdown_floor_keys(adjusted: dict[str, int], target_total: int) -> set[str]:
    if target_total <= 0:
        return set()
    present_keys = [key for key in MESSAGE_USAGE_BREAKDOWN_PROTECTED_KEYS if adjusted.get(key, 0) > 0]
    if not present_keys:
        return set()
    return set(present_keys[: min(len(present_keys), target_total)])


def _normalize_usage_breakdown(breakdown: dict | None, target_total: int | None = None) -> dict | None:
    if not isinstance(breakdown, dict):
        return None

    normalized_breakdown = {}
    for key in MESSAGE_USAGE_BREAKDOWN_KEYS:
        if key == "core_instructions":
            has_core_source = "core_instructions" in breakdown or any(
                legacy_key in breakdown for legacy_key in LEGACY_MESSAGE_USAGE_BREAKDOWN_KEYS.get(key, ())
            )
            if not has_core_source:
                normalized = None
            else:
                raw_total = breakdown.get("core_instructions")
                normalized = _coerce_non_negative_int(raw_total) or 0
                for legacy_key in LEGACY_MESSAGE_USAGE_BREAKDOWN_KEYS.get(key, ()):
                    normalized += _coerce_non_negative_int(breakdown.get(legacy_key)) or 0
        else:
            raw_value = breakdown.get(key)
            if raw_value is None:
                for legacy_key in LEGACY_MESSAGE_USAGE_BREAKDOWN_KEYS.get(key, ()): 
                    if legacy_key in breakdown:
                        raw_value = breakdown.get(legacy_key)
                        break
            normalized = _coerce_non_negative_int(raw_value)
        if normalized is not None:
            normalized_breakdown[key] = normalized

    if not normalized_breakdown:
        return None

    if target_total is None:
        return normalized_breakdown

    adjusted = {key: max(0, int(value)) for key, value in normalized_breakdown.items() if value and value > 0}
    current_total = sum(adjusted.values())
    if current_total < target_total:
        adjusted["unknown_provider_overhead"] = adjusted.get("unknown_provider_overhead", 0) + (target_total - current_total)
        return adjusted

    overflow = current_total - target_total
    if overflow <= 0:
        return adjusted

    protected_floor_keys = _protected_breakdown_floor_keys(adjusted, target_total)
    for key in MESSAGE_USAGE_BREAKDOWN_REDUCTION_ORDER:
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


def _normalize_message_usage_call(value: dict | None) -> dict | None:
    if not isinstance(value, dict):
        return None

    cleaned = {}
    for key in (
        "index",
        "step",
        "message_count",
        "tool_schema_tokens",
        "prompt_tokens",
        "prompt_cache_hit_tokens",
        "prompt_cache_miss_tokens",
        "prompt_cache_write_tokens",
        "completion_tokens",
        "total_tokens",
        "estimated_input_tokens",
    ):
        normalized = _coerce_non_negative_int(value.get(key))
        if normalized is not None:
            cleaned[key] = normalized

    call_type = str(value.get("call_type") or "").strip()[:40]
    if call_type:
        cleaned["call_type"] = call_type

    retry_reason = str(value.get("retry_reason") or "").strip()[:80]
    if retry_reason:
        cleaned["retry_reason"] = retry_reason

    if value.get("is_retry") is True:
        cleaned["is_retry"] = True
    if value.get("missing_provider_usage") is True:
        cleaned["missing_provider_usage"] = True
    if value.get("cache_metrics_estimated") is True:
        cleaned["cache_metrics_estimated"] = True

    target_total = cleaned.get("prompt_tokens")
    normalized_breakdown = _normalize_usage_breakdown(
        value.get("input_breakdown"),
        target_total=target_total or cleaned.get("estimated_input_tokens"),
    )
    if normalized_breakdown:
        cleaned["input_breakdown"] = normalized_breakdown

    if target_total is not None:
        cleaned["estimated_input_tokens"] = target_total
    elif normalized_breakdown:
        cleaned["estimated_input_tokens"] = sum(normalized_breakdown.values())

    return cleaned or None


def _normalize_message_usage(value: dict | None) -> dict | None:
    if not isinstance(value, dict):
        return None

    cleaned = {}
    for key in (
        "prompt_tokens",
        "prompt_cache_hit_tokens",
        "prompt_cache_miss_tokens",
        "prompt_cache_write_tokens",
        "completion_tokens",
        "total_tokens",
        "estimated_input_tokens",
        "max_input_tokens_per_call",
        "configured_prompt_max_input_tokens",
    ):
        normalized = _coerce_non_negative_int(value.get(key))
        if normalized is not None:
            cleaned[key] = normalized

    normalized_breakdown = _normalize_usage_breakdown(
        value.get("input_breakdown"),
        target_total=cleaned.get("prompt_tokens") or cleaned.get("estimated_input_tokens"),
    )
    if normalized_breakdown:
        cleaned["input_breakdown"] = normalized_breakdown

    model_calls = []
    raw_model_calls = value.get("model_calls") if isinstance(value.get("model_calls"), list) else []
    for entry in raw_model_calls[:32]:
        normalized_call = _normalize_message_usage_call(entry)
        if normalized_call:
            model_calls.append(normalized_call)
    if model_calls:
        cleaned["model_calls"] = model_calls

    model_call_count = _coerce_non_negative_int(value.get("model_call_count"))
    if model_call_count is None and model_calls:
        model_call_count = len(model_calls)
    elif model_call_count is not None and model_calls:
        model_call_count = max(model_call_count, len(model_calls))
    if model_call_count is not None:
        cleaned["model_call_count"] = model_call_count

    cost = value.get("cost")
    if isinstance(cost, (int, float)) and not isinstance(cost, bool) and cost >= 0:
        cleaned["cost"] = round(float(cost), 6)

    if isinstance(value.get("cost_available"), bool):
        cleaned["cost_available"] = value["cost_available"]
    if value.get("cache_metrics_estimated") is True:
        cleaned["cache_metrics_estimated"] = True
    if value.get("provider_usage_partial") is True:
        cleaned["provider_usage_partial"] = True

    currency = str(value.get("currency") or "").strip()[:16]
    if currency:
        cleaned["currency"] = currency

    provider = str(value.get("provider") or "").strip()[:40]
    if provider:
        cleaned["provider"] = provider

    model = str(value.get("model") or "").strip()[:80]
    if model:
        cleaned["model"] = model

    if cleaned.get("prompt_tokens") is not None:
        cleaned["estimated_input_tokens"] = cleaned["prompt_tokens"]
    elif normalized_breakdown:
        cleaned["estimated_input_tokens"] = sum(normalized_breakdown.values())

    return cleaned or None


def _normalize_message_tool_result(entry: dict) -> dict | None:
    if not isinstance(entry, dict):
        return None

    tool_name = str(entry.get("tool_name") or "").strip()[:80]
    content = str(entry.get("content") or "").strip()[:RAG_TOOL_RESULT_MAX_TEXT_CHARS]
    if not tool_name or not content:
        return None

    cleaned = {
        "tool_name": tool_name,
        "content": content,
    }
    summary = str(entry.get("summary") or "").strip()[:RAG_TOOL_RESULT_SUMMARY_MAX_CHARS]
    if summary:
        cleaned["summary"] = summary
    input_preview = str(entry.get("input_preview") or "").strip()[:300]
    if input_preview:
        cleaned["input_preview"] = input_preview

    raw_content = str(entry.get("raw_content") or "").strip()[:FETCH_RAW_TOOL_RESULT_MAX_TEXT_CHARS]
    if raw_content:
        cleaned["raw_content"] = raw_content

    content_mode = str(entry.get("content_mode") or "").strip()[:80]
    if content_mode:
        cleaned["content_mode"] = content_mode

    summary_notice = str(entry.get("summary_notice") or "").strip()[:300]
    if summary_notice:
        cleaned["summary_notice"] = summary_notice

    for key, max_length in (
        ("recovery_hint", 300),
        ("fetch_diagnostic", 600),
        ("meta_description", 300),
        ("structured_data", 600),
        ("fetch_outcome", 120),
        ("model", 120),
        ("focus", 300),
        ("error", 400),
    ):
        value = str(entry.get(key) or "").strip()[:max_length]
        if value:
            cleaned[key] = value

    if isinstance(entry.get("cleanup_applied"), bool):
        cleaned["cleanup_applied"] = entry["cleanup_applied"]

    if entry.get("raw_content_available") is True:
        cleaned["raw_content_available"] = True

    token_estimate = _coerce_non_negative_int(entry.get("content_token_estimate"))
    if token_estimate is not None:
        cleaned["content_token_estimate"] = token_estimate

    content_char_count = _coerce_non_negative_int(entry.get("content_char_count"))
    if content_char_count is not None:
        cleaned["content_char_count"] = content_char_count

    return cleaned


def _normalize_message_tool_trace_entry(entry: dict) -> dict | None:
    if not isinstance(entry, dict):
        return None

    tool_name = str(entry.get("tool_name") or entry.get("tool") or "").strip()[:80]
    if not tool_name:
        return None

    state = str(entry.get("state") or "").strip().lower()
    if state not in MESSAGE_TOOL_TRACE_STATES:
        state = "done"

    cleaned = {
        "tool_name": tool_name,
        "state": state,
    }

    step = _coerce_non_negative_int(entry.get("step"))
    if step is not None:
        cleaned["step"] = max(1, step)

    preview = str(entry.get("preview") or "").strip()[:300]
    if preview:
        cleaned["preview"] = preview

    summary = str(entry.get("summary") or "").strip()[:RAG_TOOL_RESULT_SUMMARY_MAX_CHARS]
    if summary:
        cleaned["summary"] = summary

    executed_at = str(entry.get("executed_at") or "").strip()[:40]
    if executed_at:
        cleaned["executed_at"] = executed_at

    if isinstance(entry.get("cached"), bool):
        cleaned["cached"] = entry["cached"]

    return cleaned


def extract_message_tool_results(metadata: dict | None) -> list[dict]:
    source = metadata if isinstance(metadata, dict) else {}
    raw_results = source.get("tool_results")
    if not isinstance(raw_results, list):
        return []

    normalized = []
    for entry in raw_results:
        cleaned = _normalize_message_tool_result(entry)
        if cleaned and cleaned not in normalized:
            normalized.append(cleaned)
    return normalized


def extract_message_tool_trace(metadata: dict | None) -> list[dict]:
    source = metadata if isinstance(metadata, dict) else {}
    raw_trace = source.get("tool_trace")
    if not isinstance(raw_trace, list):
        return []

    normalized = []
    for entry in raw_trace[:64]:
        cleaned = _normalize_message_tool_trace_entry(entry)
        if cleaned:
            normalized.append(cleaned)
    return normalized


def _normalize_sub_agent_tool_call_entry(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    name = str(value.get("name") or "").strip()[:80]
    if not name:
        return None
    cleaned = {"name": name}
    preview = str(value.get("preview") or "").strip()[:240]
    if preview:
        cleaned["preview"] = preview
    arguments = str(value.get("arguments") or "").strip()[:1_200]
    if arguments:
        cleaned["arguments"] = arguments
    return cleaned


def _normalize_sub_agent_message_entry(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    role = str(value.get("role") or "").strip()
    if role not in {"assistant", "tool"}:
        return None

    cleaned = {"role": role}
    content = str(value.get("content") or "").strip()[:4_000]
    if content:
        cleaned["content"] = content
    if value.get("content_truncated") is True:
        cleaned["content_truncated"] = True

    if role == "assistant":
        tool_calls = value.get("tool_calls") if isinstance(value.get("tool_calls"), list) else []
        normalized_tool_calls = []
        for item in tool_calls[:SUB_AGENT_TRACE_MAX_TOOL_CALLS]:
            cleaned_call = _normalize_sub_agent_tool_call_entry(item)
            if cleaned_call:
                normalized_tool_calls.append(cleaned_call)
        if normalized_tool_calls:
            cleaned["tool_calls"] = normalized_tool_calls
        if "content" not in cleaned and "tool_calls" not in cleaned:
            return None
        return cleaned

    tool_call_id = str(value.get("tool_call_id") or "").strip()[:120]
    if tool_call_id:
        cleaned["tool_call_id"] = tool_call_id
    if "content" not in cleaned:
        return None
    return cleaned


def _normalize_sub_agent_artifact(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    kind = str(value.get("kind") or "").strip()[:40]
    label = str(value.get("label") or "").strip()[:160]
    item_value = str(value.get("value") or "").strip()[:300]
    if not kind or not label or not item_value:
        return None
    return {
        "kind": kind,
        "label": label,
        "value": item_value,
    }


def _normalize_sub_agent_trace_entry(value) -> dict | None:
    if not isinstance(value, dict):
        return None

    status = str(value.get("status") or "ok").strip().lower()
    if status not in {"running", "ok", "partial", "error"}:
        status = "ok"

    cleaned = {"status": status}
    task = str(value.get("task") or "").strip()[:400]
    if task:
        cleaned["task"] = task
    task_full = str(value.get("task_full") or "").strip()[:4_000]
    if task_full:
        cleaned["task_full"] = task_full
    summary = str(value.get("summary") or "").strip()[:4_000]
    if summary:
        cleaned["summary"] = summary
    model = str(value.get("model") or "").strip()[:120]
    if model:
        cleaned["model"] = model
    error = str(value.get("error") or "").strip()[:800]
    if error:
        cleaned["error"] = error
    reasoning = str(value.get("reasoning") or "").strip()[:4_000]
    if reasoning:
        cleaned["reasoning"] = reasoning
    if value.get("timed_out") is True:
        cleaned["timed_out"] = True
    if value.get("canvas_saved") is True:
        cleaned["canvas_saved"] = True

    canvas_document_id = str(value.get("canvas_document_id") or "").strip()[:120]
    if canvas_document_id:
        cleaned["canvas_document_id"] = canvas_document_id

    canvas_document_title = str(value.get("canvas_document_title") or "").strip()[:300]
    if canvas_document_title:
        cleaned["canvas_document_title"] = canvas_document_title

    fallback_note = str(value.get("fallback_note") or "").strip()[:300]
    if fallback_note:
        cleaned["fallback_note"] = fallback_note

    tool_trace = value.get("tool_trace") if isinstance(value.get("tool_trace"), list) else []
    normalized_tool_trace = []
    for entry in tool_trace[:32]:
        cleaned_entry = _normalize_message_tool_trace_entry(entry)
        if cleaned_entry:
            normalized_tool_trace.append(cleaned_entry)
    if normalized_tool_trace:
        cleaned["tool_trace"] = normalized_tool_trace

    artifacts = value.get("artifacts") if isinstance(value.get("artifacts"), list) else []
    normalized_artifacts = []
    for artifact in artifacts[:SUB_AGENT_TRACE_MAX_ARTIFACTS]:
        cleaned_artifact = _normalize_sub_agent_artifact(artifact)
        if cleaned_artifact:
            normalized_artifacts.append(cleaned_artifact)
    if normalized_artifacts:
        cleaned["artifacts"] = normalized_artifacts

    messages = value.get("messages") if isinstance(value.get("messages"), list) else []
    normalized_messages = []
    for message in messages[:SUB_AGENT_TRACE_MAX_MESSAGES]:
        cleaned_message = _normalize_sub_agent_message_entry(message)
        if cleaned_message:
            normalized_messages.append(cleaned_message)
    if normalized_messages:
        cleaned["messages"] = normalized_messages

    return cleaned if any(key in cleaned for key in {"task", "task_full", "summary", "error", "tool_trace", "artifacts", "messages", "reasoning", "fallback_note", "canvas_saved", "canvas_document_id", "canvas_document_title"}) else None


def extract_sub_agent_traces(metadata: dict | None) -> list[dict]:
    source = metadata if isinstance(metadata, dict) else {}
    raw_value = source.get("sub_agent_traces")
    if not isinstance(raw_value, list):
        return []

    normalized = []
    for entry in raw_value[:SUB_AGENT_TRACE_MAX_RUNS]:
        cleaned = _normalize_sub_agent_trace_entry(entry)
        if cleaned:
            normalized.append(cleaned)
    return normalized


def extract_message_usage(
    metadata: dict | None,
    prompt_tokens=None,
    completion_tokens=None,
    total_tokens=None,
) -> dict | None:
    source = metadata if isinstance(metadata, dict) else {}
    usage = _normalize_message_usage(source.get("usage")) or {}

    fallback_prompt = _coerce_non_negative_int(prompt_tokens)
    fallback_completion = _coerce_non_negative_int(completion_tokens)
    fallback_total = _coerce_non_negative_int(total_tokens)

    if fallback_prompt is not None and "prompt_tokens" not in usage:
        usage["prompt_tokens"] = fallback_prompt
    if fallback_completion is not None and "completion_tokens" not in usage:
        usage["completion_tokens"] = fallback_completion
    if fallback_total is not None and "total_tokens" not in usage:
        usage["total_tokens"] = fallback_total

    target_total = usage.get("prompt_tokens")
    normalized_breakdown = _normalize_usage_breakdown(
        usage.get("input_breakdown"),
        target_total=target_total or usage.get("estimated_input_tokens"),
    )
    if normalized_breakdown:
        usage["input_breakdown"] = normalized_breakdown
    if target_total is not None:
        usage["estimated_input_tokens"] = target_total
    elif normalized_breakdown:
        usage["estimated_input_tokens"] = sum(normalized_breakdown.values())

    return usage or None


def _normalize_clarification_question_payload(value) -> dict | None:
    if not isinstance(value, dict):
        return None

    question_id = str(value.get("id") or "").strip()[:80]
    label = str(value.get("label") or "").strip()[:300]
    input_type = str(value.get("input_type") or "").strip()
    if not question_id or not label or input_type not in {"text", "single_select", "multi_select"}:
        return None

    cleaned = {
        "id": question_id,
        "label": label,
        "input_type": input_type,
    }
    if value.get("required") is False:
        cleaned["required"] = False

    placeholder = str(value.get("placeholder") or "").strip()[:200]
    if placeholder:
        cleaned["placeholder"] = placeholder

    if value.get("allow_free_text") is True:
        cleaned["allow_free_text"] = True

    raw_options = value.get("options") if isinstance(value.get("options"), list) else []
    normalized_options = []
    for option in raw_options[:12]:
        if not isinstance(option, dict):
            continue
        option_label = str(option.get("label") or "").strip()[:120]
        option_value = str(option.get("value") or "").strip()[:120]
        if not option_label or not option_value:
            continue
        normalized_option = {
            "label": option_label,
            "value": option_value,
        }
        description = str(option.get("description") or "").strip()[:200]
        if description:
            normalized_option["description"] = description
        normalized_options.append(normalized_option)
    if normalized_options:
        cleaned["options"] = normalized_options

    return cleaned


def extract_pending_clarification(metadata: dict | None) -> dict | None:
    source = metadata if isinstance(metadata, dict) else {}
    pending = source.get("pending_clarification")
    if not isinstance(pending, dict):
        return None

    questions = pending.get("questions") if isinstance(pending.get("questions"), list) else []
    normalized_questions = []
    question_limit = get_clarification_max_questions()
    for question in questions[:question_limit]:
        normalized_question = _normalize_clarification_question_payload(question)
        if normalized_question is not None:
            normalized_questions.append(normalized_question)
    if not normalized_questions:
        return None

    cleaned = {"questions": normalized_questions}
    intro = str(pending.get("intro") or "").strip()[:300]
    if intro:
        cleaned["intro"] = intro
    submit_label = str(pending.get("submit_label") or "").strip()[:80]
    if submit_label:
        cleaned["submit_label"] = submit_label
    return cleaned


def extract_clarification_response(metadata: dict | None) -> dict | None:
    source = metadata if isinstance(metadata, dict) else {}
    response = source.get("clarification_response")
    if not isinstance(response, dict):
        return None

    cleaned = {}
    assistant_message_id = _coerce_non_negative_int(response.get("assistant_message_id"))
    if assistant_message_id is not None:
        cleaned["assistant_message_id"] = assistant_message_id

    answers = response.get("answers") if isinstance(response.get("answers"), dict) else {}
    normalized_answers = {}
    for key, value in list(answers.items())[:10]:
        key_text = str(key or "").strip()[:80]
        if not key_text or not isinstance(value, dict):
            continue
        display = str(value.get("display") or "").strip()[:500]
        if not display:
            continue
        normalized_answers[key_text] = {"display": display}
    if normalized_answers:
        cleaned["answers"] = normalized_answers

    return cleaned or None


def sanitize_edited_user_message_metadata(metadata: dict | None) -> dict:
    source = parse_message_metadata(metadata)
    attachments = extract_message_attachments(source)
    if not attachments:
        return {}
    return {"attachments": attachments}


def serialize_message_metadata(metadata: dict | None, *, include_private_fields: bool = False) -> str | None:
    metadata = _strip_private_message_metadata_fields(
        metadata if isinstance(metadata, dict) else {},
        include_private_fields=include_private_fields,
    )
    cleaned = {}
    context_injection = str(metadata.get("context_injection") or "").strip()

    attachments = extract_message_attachments(metadata)
    primary_image = next((entry for entry in attachments if entry.get("kind") == "image"), None)
    primary_document = next((entry for entry in attachments if entry.get("kind") == "document"), None)

    ocr_text = (metadata.get("ocr_text") or (primary_image or {}).get("ocr_text") or "").strip()
    vision_summary = (metadata.get("vision_summary") or (primary_image or {}).get("vision_summary") or "").strip()
    analysis_method = (metadata.get("analysis_method") or (primary_image or {}).get("analysis_method") or "").strip()
    assistant_guidance = (
        metadata.get("assistant_guidance") or (primary_image or {}).get("assistant_guidance") or ""
    ).strip()
    image_name = (metadata.get("image_name") or (primary_image or {}).get("image_name") or "").strip()
    image_mime_type = (metadata.get("image_mime_type") or (primary_image or {}).get("image_mime_type") or "").strip()
    image_id = (metadata.get("image_id") or (primary_image or {}).get("image_id") or "").strip()
    key_points = metadata.get("key_points") if isinstance(metadata.get("key_points"), list) else (primary_image or {}).get("key_points")
    summary_source = (metadata.get("summary_source") or "").strip()
    generated_at = (metadata.get("generated_at") or "").strip()
    reasoning_content = str(metadata.get("reasoning_content") or "").strip()

    if attachments:
        cleaned["attachments"] = attachments

    if reasoning_content:
        cleaned["reasoning_content"] = reasoning_content[:CONTENT_MAX_CHARS]

    if ocr_text:
        cleaned["ocr_text"] = ocr_text
    if vision_summary:
        cleaned["vision_summary"] = vision_summary
    if analysis_method:
        cleaned["analysis_method"] = analysis_method[:40]
    if assistant_guidance:
        cleaned["assistant_guidance"] = assistant_guidance
    if image_name:
        cleaned["image_name"] = image_name[:255]
    if image_mime_type:
        cleaned["image_mime_type"] = image_mime_type
    if image_id:
        cleaned["image_id"] = image_id[:64]
    if isinstance(key_points, list):
        normalized_points = []
        for point in key_points:
            point_text = str(point or "").strip()
            if point_text and point_text not in normalized_points:
                normalized_points.append(point_text[:300])
        if normalized_points:
            cleaned["key_points"] = normalized_points[:8]
    if metadata.get("is_pruned") is True:
        cleaned["is_pruned"] = True
    pruned_original = str(metadata.get("pruned_original") or "").strip()
    if pruned_original:
        cleaned["pruned_original"] = pruned_original[:CONTENT_MAX_CHARS]
    if metadata.get("is_summary") is True:
        cleaned["is_summary"] = True
    if metadata.get("covered_ids_truncated") is True:
        cleaned["covered_ids_truncated"] = True
    if summary_source:
        cleaned["summary_source"] = summary_source[:120]
    if generated_at:
        cleaned["generated_at"] = generated_at[:80]
    if context_injection:
        cleaned["context_injection"] = context_injection[:CONTENT_MAX_CHARS]

    for key in (
        "covers_from_position",
        "covers_to_position",
        "summary_position",
        "covered_message_count",
        "covered_tool_call_message_count",
        "covered_tool_message_count",
        "trigger_threshold",
        "trigger_token_count",
        "visible_token_count",
        "summary_source_token_target",
    ):
        normalized = _coerce_non_negative_int(metadata.get(key))
        if normalized is not None:
            cleaned[key] = normalized

    summary_mode = str(metadata.get("summary_mode") or "").strip().lower()
    if summary_mode in CHAT_SUMMARY_ALLOWED_MODES:
        cleaned["summary_mode"] = summary_mode

    summary_model = str(metadata.get("summary_model") or "").strip()
    if summary_model:
        cleaned["summary_model"] = summary_model[:120]

    summary_format = str(metadata.get("summary_format") or "").strip().lower()
    if summary_format in {"plain_text", "structured_json"}:
        cleaned["summary_format"] = summary_format

    summary_level = _coerce_non_negative_int(metadata.get("summary_level"))
    if summary_level is not None:
        cleaned["summary_level"] = max(1, summary_level)

    summary_data = metadata.get("summary_data") if isinstance(metadata.get("summary_data"), dict) else None
    if summary_data:
        normalized_summary_data = {}
        for key in ("facts", "decisions", "open_issues", "entities", "tool_outcomes"):
            raw_items = summary_data.get(key) if isinstance(summary_data.get(key), list) else []
            cleaned_items = []
            for raw_item in raw_items[:16]:
                item_text = str(raw_item or "").strip()
                if item_text and item_text not in cleaned_items:
                    cleaned_items.append(item_text[:500])
            if cleaned_items:
                normalized_summary_data[key] = cleaned_items
        if normalized_summary_data:
            cleaned["summary_data"] = normalized_summary_data

    summary_insert_strategy = str(metadata.get("summary_insert_strategy") or "").strip()
    if summary_insert_strategy in {
        "after_covered_block",
        "replace_first_covered_message",
        "replace_first_covered_message_preserve_positions",
    }:
        cleaned["summary_insert_strategy"] = summary_insert_strategy

    covered_message_ids = metadata.get("covered_message_ids")
    if isinstance(covered_message_ids, list):
        normalized_ids = []
        for raw_value in covered_message_ids[:64]:
            normalized = _coerce_non_negative_int(raw_value)
            if normalized is not None and normalized not in normalized_ids:
                normalized_ids.append(normalized)
        if normalized_ids:
            cleaned["covered_message_ids"] = normalized_ids

    for key in (
        "covered_visible_message_ids",
        "covered_tool_call_message_ids",
        "covered_tool_message_ids",
    ):
        raw_ids = metadata.get(key)
        if not isinstance(raw_ids, list):
            continue
        normalized_ids = []
        for raw_value in raw_ids[:64]:
            normalized = _coerce_non_negative_int(raw_value)
            if normalized is not None and normalized not in normalized_ids:
                normalized_ids.append(normalized)
        if normalized_ids:
            cleaned[key] = normalized_ids

    tool_results = extract_message_tool_results(metadata)
    if tool_results:
        cleaned["tool_results"] = tool_results

    tool_trace = extract_message_tool_trace(metadata)
    if tool_trace:
        cleaned["tool_trace"] = tool_trace

    usage = extract_message_usage(metadata)
    if usage:
        cleaned["usage"] = usage

    pending_clarification = extract_pending_clarification(metadata)
    if pending_clarification:
        cleaned["pending_clarification"] = pending_clarification

    clarification_response = extract_clarification_response(metadata)
    if clarification_response:
        cleaned["clarification_response"] = clarification_response

    sub_agent_traces = extract_sub_agent_traces(metadata)
    if sub_agent_traces:
        cleaned["sub_agent_traces"] = sub_agent_traces

    canvas_documents = extract_canvas_documents(metadata)
    if canvas_documents or metadata.get("canvas_cleared") is True:
        cleaned["canvas_documents"] = canvas_documents
    active_document_id = extract_canvas_active_document_id(metadata, canvas_documents)
    if active_document_id:
        cleaned["active_document_id"] = active_document_id
    canvas_viewports = extract_canvas_viewports(metadata, canvas_documents)
    if canvas_viewports:
        cleaned["canvas_viewports"] = canvas_viewports
    if metadata.get("canvas_cleared") is True:
        cleaned["canvas_cleared"] = True

    project_workflow = metadata.get("project_workflow") if isinstance(metadata.get("project_workflow"), dict) else None
    if project_workflow:
        cleaned_workflow = {}
        for key, max_length in (("project_name", 120), ("goal", 300), ("target_type", 40), ("stage", 40)):
            value = str(project_workflow.get(key) or "").strip()
            if value:
                cleaned_workflow[key] = value[:max_length]
        files = project_workflow.get("files") if isinstance(project_workflow.get("files"), list) else []
        cleaned_files = []
        for entry in files[:64]:
            if not isinstance(entry, dict):
                continue
            path = str(entry.get("path") or "").strip()[:240]
            if not path:
                continue
            cleaned_entry = {"path": path}
            for key, max_length in (("role", 24), ("purpose", 180), ("status", 40)):
                value = str(entry.get(key) or "").strip()
                if value:
                    cleaned_entry[key] = value[:max_length]
            cleaned_files.append(cleaned_entry)
        if cleaned_files:
            cleaned_workflow["files"] = cleaned_files
        for list_key in ("dependencies", "open_issues"):
            values = project_workflow.get(list_key) if isinstance(project_workflow.get(list_key), list) else []
            normalized_values = []
            for value in values[:24]:
                item = str(value or "").strip()
                if item and item not in normalized_values:
                    normalized_values.append(item[:200])
            if normalized_values:
                cleaned_workflow[list_key] = normalized_values
        validation = project_workflow.get("validation") if isinstance(project_workflow.get("validation"), dict) else None
        if validation:
            cleaned_validation = {}
            status = str(validation.get("status") or "").strip()[:40]
            if status:
                cleaned_validation["status"] = status
            for list_key in ("issues", "warnings"):
                values = validation.get(list_key) if isinstance(validation.get(list_key), list) else []
                normalized_values = []
                for value in values[:24]:
                    item = str(value or "").strip()
                    if item and item not in normalized_values:
                        normalized_values.append(item[:200])
                if normalized_values:
                    cleaned_validation[list_key] = normalized_values
            if cleaned_validation:
                cleaned_workflow["validation"] = cleaned_validation
        if cleaned_workflow:
            cleaned["project_workflow"] = cleaned_workflow

    file_id = (metadata.get("file_id") or (primary_document or {}).get("file_id") or "").strip()
    file_name = (metadata.get("file_name") or (primary_document or {}).get("file_name") or "").strip()
    file_mime_type = (metadata.get("file_mime_type") or (primary_document or {}).get("file_mime_type") or "").strip()
    file_context_block = (metadata.get("file_context_block") or "").strip()
    if not file_context_block and attachments:
        file_context_block = "\n\n".join(
            str(entry.get("file_context_block") or "").strip()
            for entry in attachments
            if entry.get("kind") == "document" and str(entry.get("file_context_block") or "").strip()
        ).strip()

    if file_id:
        cleaned["file_id"] = file_id[:64]
    if file_name:
        cleaned["file_name"] = file_name[:255]
    if file_mime_type:
        cleaned["file_mime_type"] = file_mime_type[:120]
    if metadata.get("file_text_truncated") is True or (primary_document or {}).get("file_text_truncated") is True:
        cleaned["file_text_truncated"] = True
    if file_context_block:
        cleaned["file_context_block"] = file_context_block[:CONTENT_MAX_CHARS]

    if not cleaned:
        return None
    return json.dumps(cleaned, ensure_ascii=False)


def message_row_to_dict(row, *, include_private_metadata: bool = False) -> dict:
    row_keys = set(row.keys()) if hasattr(row, "keys") else set()
    metadata = parse_message_metadata(
        row["metadata"],
        include_private_fields=include_private_metadata,
    )
    usage = extract_message_usage(
        metadata,
        prompt_tokens=row["prompt_tokens"],
        completion_tokens=row["completion_tokens"],
        total_tokens=row["total_tokens"],
    )
    tool_calls = parse_message_tool_calls(row["tool_calls"]) if "tool_calls" in row_keys else []
    tool_call_id = str(row["tool_call_id"] or "").strip() if "tool_call_id" in row_keys else ""
    return {
        "id": row["id"],
        "position": row["position"] if "position" in row_keys else None,
        "role": row["role"],
        "content": row["content"],
        "metadata": metadata,
        "tool_calls": tool_calls,
        "tool_call_id": tool_call_id or None,
        "prompt_tokens": row["prompt_tokens"],
        "completion_tokens": row["completion_tokens"],
        "total_tokens": row["total_tokens"],
        "usage": usage,
        "created_at": row["created_at"] if "created_at" in row_keys else None,
        "deleted_at": row["deleted_at"] if "deleted_at" in row_keys else None,
    }


def _serialize_json_value(value) -> str:
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return json.dumps(str(value), ensure_ascii=False)


def _parse_json_value(raw_value, fallback):
    if raw_value in (None, ""):
        return fallback
    if isinstance(raw_value, (dict, list)):
        return raw_value
    try:
        return json.loads(raw_value)
    except Exception:
        return fallback


def _model_invocation_row_to_dict(row) -> dict:
    return {
        "id": int(row["id"]),
        "conversation_id": int(row["conversation_id"]),
        "assistant_message_id": _coerce_positive_int(row["assistant_message_id"]),
        "source_message_id": _coerce_positive_int(row["source_message_id"]),
        "step": int(row["step"] or 0),
        "call_index": int(row["call_index"] or 0),
        "call_type": str(row["call_type"] or "").strip(),
        "is_retry": bool(row["is_retry"]),
        "retry_reason": str(row["retry_reason"] or "").strip() or None,
        "sub_agent_depth": int(row["sub_agent_depth"] or 0),
        "provider": str(row["provider"] or "").strip(),
        "api_model": str(row["api_model"] or "").strip(),
        "request": _parse_json_value(row["request_payload"], {}),
        "response_summary": _parse_json_value(row["response_summary"], {}),
        "created_at": str(row["created_at"] or "").strip() or None,
    }


def insert_model_invocation(
    conn: sqlite3.Connection,
    conversation_id: int,
    *,
    provider: str,
    api_model: str,
    request_payload,
    response_summary=None,
    assistant_message_id: int | None = None,
    source_message_id: int | None = None,
    step: int | None = None,
    call_index: int | None = None,
    call_type: str = "agent_step",
    is_retry: bool = False,
    retry_reason: str | None = None,
    sub_agent_depth: int = 0,
) -> int:
    cursor = conn.execute(
        """INSERT INTO model_invocations (
               conversation_id,
               assistant_message_id,
               source_message_id,
               step,
               call_index,
               call_type,
               is_retry,
               retry_reason,
               sub_agent_depth,
               provider,
               api_model,
               request_payload,
               response_summary
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            int(conversation_id),
            _coerce_positive_int(assistant_message_id),
            _coerce_positive_int(source_message_id),
            max(0, int(step or 0)),
            max(0, int(call_index or 0)),
            str(call_type or "agent_step").strip() or "agent_step",
            1 if is_retry else 0,
            str(retry_reason or "").strip() or None,
            max(0, int(sub_agent_depth or 0)),
            str(provider or "").strip(),
            str(api_model or "").strip(),
            _serialize_json_value(request_payload),
            _serialize_json_value(response_summary if response_summary is not None else {}),
        ),
    )
    return int(cursor.lastrowid)


def list_conversation_model_invocations(conversation_id: int) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, conversation_id, assistant_message_id, source_message_id, step, call_index,
                      call_type, is_retry, retry_reason, sub_agent_depth, provider, api_model,
                      request_payload, response_summary, created_at
               FROM model_invocations
               WHERE conversation_id = ?
               ORDER BY id ASC""",
            (int(conversation_id),),
        ).fetchall()
    return [_model_invocation_row_to_dict(row) for row in rows]


def get_app_settings() -> dict:
    settings = DEFAULT_SETTINGS.copy()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT key, value FROM app_settings WHERE key IN ({})".format(", ".join("?" for _ in settings)),
            tuple(settings.keys()),
        ).fetchall()

    for row in rows:
        settings[row["key"]] = row["value"]

    settings = _migrate_legacy_scratchpad_settings(settings)
    return _migrate_legacy_assistant_behavior_settings(settings)


def get_proxy_enabled_operations(settings: dict | None = None) -> list[str]:
    source = settings if settings is not None else get_app_settings()
    raw_value = source.get("proxy_enabled_operations") if isinstance(source, dict) else None
    return normalize_proxy_enabled_operations(raw_value)


def normalize_scratchpad_text(value) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    seen = set()
    for raw_line in text.split("\n"):
        line = " ".join(raw_line.strip().split())
        if not line or line in seen:
            continue
        seen.add(line)
        lines.append(line)

    normalized = "\n".join(lines)
    return normalized


def normalize_assistant_behavior_text(value) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def count_personas() -> int:
    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM personas").fetchone()
    return int(row["count"] or 0)


def list_personas() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, name, general_instructions, ai_personality, created_at, updated_at
               FROM personas
               ORDER BY lower(name) ASC, id ASC"""
        ).fetchall()
    return [_persona_row_to_dict(row) for row in rows if row]


def get_persona(persona_id: int | None) -> dict | None:
    with get_db() as conn:
        return _get_persona_by_id(conn, persona_id)


def get_default_persona_id(settings: dict | None = None) -> int | None:
    source = settings if settings is not None else get_app_settings()
    raw_value = source.get("default_persona_id") if isinstance(source, dict) else None
    return _coerce_positive_int(raw_value)


def get_default_persona(settings: dict | None = None) -> dict | None:
    return get_persona(get_default_persona_id(settings))


def build_persona_preferences(persona: dict | None) -> str:
    if not isinstance(persona, dict):
        return ""
    general_instructions = normalize_assistant_behavior_text(persona.get("general_instructions", ""))
    ai_personality = normalize_assistant_behavior_text(persona.get("ai_personality", ""))
    parts = []
    if general_instructions:
        parts.append(f"General instructions:\n{general_instructions}")
    if ai_personality:
        parts.append(f"AI personality:\n{ai_personality}")
    return "\n\n".join(parts).strip()


def create_persona(name: str, general_instructions: str = "", ai_personality: str = "") -> dict:
    normalized_name = normalize_persona_name(name)
    if not normalized_name:
        raise ValueError("Persona name is required.")

    normalized_general_instructions = _normalize_persona_behavior(general_instructions, MAX_USER_PREFERENCES_LENGTH)
    normalized_ai_personality = _normalize_persona_behavior(ai_personality, MAX_AI_PERSONALITY_LENGTH)

    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM personas").fetchone()
        if int(row["count"] or 0) >= MAX_PERSONA_COUNT:
            raise ValueError(f"Persona limit reached ({MAX_PERSONA_COUNT}).")
        cursor = conn.execute(
            "INSERT INTO personas (name, general_instructions, ai_personality) VALUES (?, ?, ?)",
            (normalized_name, normalized_general_instructions, normalized_ai_personality),
        )
        return _get_persona_by_id(conn, cursor.lastrowid)


def upsert_default_persona(
    general_instructions: str = "",
    ai_personality: str = "",
    *,
    name: str = "Default",
) -> dict:
    normalized_name = normalize_persona_name(name) or "Default"
    normalized_general_instructions = _normalize_persona_behavior(general_instructions, MAX_USER_PREFERENCES_LENGTH)
    normalized_ai_personality = _normalize_persona_behavior(ai_personality, MAX_AI_PERSONALITY_LENGTH)

    with get_db() as conn:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = ?",
            ("default_persona_id",),
        ).fetchone()
        current_default_persona = _get_persona_by_id(conn, row["value"] if row else None)
        if current_default_persona:
            conn.execute(
                """UPDATE personas
                   SET name = ?, general_instructions = ?, ai_personality = ?, updated_at = datetime('now')
                   WHERE id = ?""",
                (
                    normalized_name,
                    normalized_general_instructions,
                    normalized_ai_personality,
                    current_default_persona["id"],
                ),
            )
            persona = _get_persona_by_id(conn, current_default_persona["id"])
        else:
            row = conn.execute("SELECT COUNT(*) AS count FROM personas").fetchone()
            if int(row["count"] or 0) >= MAX_PERSONA_COUNT:
                raise ValueError(f"Persona limit reached ({MAX_PERSONA_COUNT}).")
            cursor = conn.execute(
                "INSERT INTO personas (name, general_instructions, ai_personality) VALUES (?, ?, ?)",
                (normalized_name, normalized_general_instructions, normalized_ai_personality),
            )
            persona = _get_persona_by_id(conn, cursor.lastrowid)

        _upsert_app_setting(conn, "default_persona_id", str(persona["id"]))
        return persona


def update_persona(
    persona_id: int,
    *,
    name: str | None = None,
    general_instructions: str | None = None,
    ai_personality: str | None = None,
) -> dict | None:
    normalized_persona_id = _coerce_positive_int(persona_id)
    if normalized_persona_id is None:
        return None

    with get_db() as conn:
        current = _get_persona_by_id(conn, normalized_persona_id)
        if not current:
            return None

        next_name = current["name"] if name is None else normalize_persona_name(name)
        if not next_name:
            raise ValueError("Persona name is required.")

        next_general_instructions = (
            current["general_instructions"]
            if general_instructions is None
            else _normalize_persona_behavior(general_instructions, MAX_USER_PREFERENCES_LENGTH)
        )
        next_ai_personality = (
            current["ai_personality"]
            if ai_personality is None
            else _normalize_persona_behavior(ai_personality, MAX_AI_PERSONALITY_LENGTH)
        )
        conn.execute(
            """UPDATE personas
               SET name = ?, general_instructions = ?, ai_personality = ?, updated_at = datetime('now')
               WHERE id = ?""",
            (
                next_name,
                next_general_instructions,
                next_ai_personality,
                normalized_persona_id,
            ),
        )
        return _get_persona_by_id(conn, normalized_persona_id)


def delete_persona(persona_id: int) -> bool:
    normalized_persona_id = _coerce_positive_int(persona_id)
    if normalized_persona_id is None:
        return False

    with get_db() as conn:
        current = _get_persona_by_id(conn, normalized_persona_id)
        if not current:
            return False
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = ?",
            ("default_persona_id",),
        ).fetchone()
        default_persona_id = _coerce_positive_int(row["value"] if row else None)
        conn.execute("DELETE FROM personas WHERE id = ?", (normalized_persona_id,))
        if default_persona_id == normalized_persona_id:
            _upsert_app_setting(conn, "default_persona_id", "")
        return True


def get_conversation_persona(conversation_id: int | None) -> dict | None:
    normalized_conversation_id = _coerce_positive_int(conversation_id)
    if normalized_conversation_id is None:
        return None
    with get_db() as conn:
        row = conn.execute(
            """SELECT p.id, p.name, p.general_instructions, p.ai_personality, p.created_at, p.updated_at
               FROM conversations c
               JOIN personas p ON p.id = c.persona_id
               WHERE c.id = ?""",
            (normalized_conversation_id,),
        ).fetchone()
    return _persona_row_to_dict(row)


def get_effective_conversation_persona(conversation_id: int | None, settings: dict | None = None) -> dict | None:
    persona = get_conversation_persona(conversation_id)
    if persona:
        return persona
    return get_default_persona(settings)


def build_conversation_assistant_behavior(conversation_id: int | None, settings: dict | None = None) -> str:
    persona = get_effective_conversation_persona(conversation_id, settings)
    if persona:
        return build_persona_preferences(persona)
    return build_effective_user_preferences(settings)


def set_conversation_persona(conversation_id: int, persona_id: int | None) -> bool:
    normalized_conversation_id = _coerce_positive_int(conversation_id)
    if normalized_conversation_id is None:
        return False
    normalized_persona_id = _coerce_positive_int(persona_id)

    with get_db() as conn:
        conversation = conn.execute(
            "SELECT id FROM conversations WHERE id = ?",
            (normalized_conversation_id,),
        ).fetchone()
        if not conversation:
            return False
        if normalized_persona_id is not None and _get_persona_by_id(conn, normalized_persona_id) is None:
            raise ValueError("Persona not found.")
        conn.execute(
            "UPDATE conversations SET persona_id = ?, updated_at = datetime('now') WHERE id = ?",
            (normalized_persona_id, normalized_conversation_id),
        )
        return True


def get_general_instructions(settings: dict | None = None) -> str:
    source = settings if settings is not None else get_app_settings()
    general_instructions = normalize_assistant_behavior_text(source.get("general_instructions", ""))
    if general_instructions:
        return general_instructions
    return normalize_assistant_behavior_text(source.get("user_preferences", ""))


def get_ai_personality(settings: dict | None = None) -> str:
    source = settings if settings is not None else get_app_settings()
    return normalize_assistant_behavior_text(source.get("ai_personality", ""))


def build_effective_user_preferences(settings: dict | None = None) -> str:
    general_instructions = get_general_instructions(settings)
    ai_personality = get_ai_personality(settings)
    parts = []
    if general_instructions:
        parts.append(f"General instructions:\n{general_instructions}")
    if ai_personality:
        parts.append(f"AI personality:\n{ai_personality}")
    return "\n\n".join(parts).strip()


def normalize_scratchpad_section_id(section: str | None) -> str:
    normalized = str(section or "").strip().lower()
    if normalized not in SCRATCHPAD_SECTION_SETTING_KEYS:
        raise ValueError(f"Invalid scratchpad section: {section!r}")
    return normalized


def get_all_scratchpad_sections(settings: dict | None = None) -> dict[str, str]:
    source = settings if settings is not None else get_app_settings()
    return {
        section_id: normalize_scratchpad_text(source.get(SCRATCHPAD_SECTION_SETTING_KEYS[section_id], ""))
        for section_id in SCRATCHPAD_SECTION_ORDER
    }


def count_scratchpad_notes(value) -> int:
    normalized = normalize_scratchpad_text(value)
    return len(normalized.splitlines()) if normalized else 0


def _normalize_app_setting_value(key: str, value):
    if key == "scratchpad" or key in SCRATCHPAD_SECTION_SETTING_KEYS.values():
        return normalize_scratchpad_text(value)
    if key == "default_persona_id":
        return str(_coerce_positive_int(value) or "")
    if key in {"user_preferences", "general_instructions", "ai_personality"}:
        return normalize_assistant_behavior_text(value)
    return value


def _upsert_app_setting(conn, key: str, value) -> None:
    conn.execute(
        """INSERT INTO app_settings (key, value, updated_at)
           VALUES (?, ?, datetime('now'))
           ON CONFLICT(key) DO UPDATE SET
               value = excluded.value,
               updated_at = datetime('now')""",
        (key, value),
    )


def _migrate_legacy_scratchpad_settings(settings: dict) -> dict:
    legacy_value = normalize_scratchpad_text(settings.get("scratchpad", ""))
    section_values = {
        section_id: normalize_scratchpad_text(settings.get(section_key, ""))
        for section_id, section_key in SCRATCHPAD_SECTION_SETTING_KEYS.items()
    }
    notes_key = SCRATCHPAD_SECTION_SETTING_KEYS[SCRATCHPAD_DEFAULT_SECTION]
    notes_value = section_values.get(SCRATCHPAD_DEFAULT_SECTION, "")

    if legacy_value and not notes_value:
        section_values[SCRATCHPAD_DEFAULT_SECTION] = legacy_value
        settings[notes_key] = legacy_value
        settings["scratchpad"] = ""
        with get_db() as conn:
            _upsert_app_setting(conn, notes_key, legacy_value)
            _upsert_app_setting(conn, "scratchpad", "")

    for section_id, section_key in SCRATCHPAD_SECTION_SETTING_KEYS.items():
        settings[section_key] = section_values.get(section_id, "")

    settings["scratchpad"] = section_values.get(SCRATCHPAD_DEFAULT_SECTION, "")
    return settings


def _migrate_legacy_assistant_behavior_settings(settings: dict) -> dict:
    general_instructions = normalize_assistant_behavior_text(settings.get("general_instructions", ""))
    legacy_preferences = normalize_assistant_behavior_text(settings.get("user_preferences", ""))
    ai_personality = normalize_assistant_behavior_text(settings.get("ai_personality", ""))

    should_persist = False
    if legacy_preferences and not general_instructions:
        general_instructions = legacy_preferences
        should_persist = True

    if legacy_preferences != general_instructions:
        should_persist = True

    settings["general_instructions"] = general_instructions
    settings["user_preferences"] = general_instructions
    settings["ai_personality"] = ai_personality

    if should_persist:
        with get_db() as conn:
            _upsert_app_setting(conn, "general_instructions", general_instructions)
            _upsert_app_setting(conn, "user_preferences", general_instructions)
            _upsert_app_setting(conn, "ai_personality", ai_personality)

    return settings


def append_to_scratchpad(
    notes,
    section: str = SCRATCHPAD_DEFAULT_SECTION,
    *,
    conversation_id: int | None = None,
    source_message_id: int | None = None,
) -> tuple[dict, str]:
    """Append one or more notes. `notes` may be a string or a list of strings."""
    section_id = normalize_scratchpad_section_id(section)
    section_key = SCRATCHPAD_SECTION_SETTING_KEYS[section_id]
    if isinstance(notes, str):
        note_list = [notes]
    else:
        note_list = list(notes or [])

    settings = get_app_settings()
    current = normalize_scratchpad_text(settings.get(section_key, ""))
    current_lines = current.splitlines() if current else []
    current_set = set(current_lines)

    appended = []
    skipped = []
    for raw in note_list:
        normalized_note = " ".join(str(raw or "").strip().split())
        if not normalized_note:
            continue
        if normalized_note in current_set:
            skipped.append(normalized_note)
        else:
            current_lines.append(normalized_note)
            current_set.add(normalized_note)
            appended.append(normalized_note)

    if not appended:
        if not skipped:
            return {"status": "rejected", "reason": "empty_notes"}, "Scratchpad notes are empty"
        return {
            "status": "skipped",
            "reason": "duplicate_notes",
            "section": section_id,
            "notes": skipped,
            "scratchpad": current,
            "scratchpad_sections": get_all_scratchpad_sections(settings),
        }, "Scratchpad notes already exist"

    next_value = normalize_scratchpad_text("\n".join(current_lines))
    settings[section_key] = next_value
    save_app_settings(settings)
    if int(conversation_id or 0) > 0 and appended:
        record_conversation_state_mutation(
            int(conversation_id),
            source_message_id=_normalize_state_mutation_source_message_id(source_message_id),
            target_kind=STATE_MUTATION_TARGET_SCRATCHPAD_SECTION,
            target_key=section_id,
            operation=STATE_MUTATION_OPERATION_APPEND,
            before_value={"content": current},
            after_value={"content": next_value, "appended_notes": appended},
        )
    return {
        "status": "appended",
        "section": section_id,
        "notes": appended,
        "skipped": skipped,
        "scratchpad": next_value,
        "scratchpad_sections": get_all_scratchpad_sections(settings),
    }, "Scratchpad updated"


def replace_scratchpad(
    new_content,
    section: str = SCRATCHPAD_DEFAULT_SECTION,
    *,
    conversation_id: int | None = None,
    source_message_id: int | None = None,
) -> tuple[dict, str]:
    section_id = normalize_scratchpad_section_id(section)
    section_key = SCRATCHPAD_SECTION_SETTING_KEYS[section_id]
    normalized_content = normalize_scratchpad_text(new_content)

    settings = get_app_settings()
    current_content = normalize_scratchpad_text(settings.get(section_key, ""))
    settings[section_key] = normalized_content
    save_app_settings(settings)
    if int(conversation_id or 0) > 0 and current_content != normalized_content:
        record_conversation_state_mutation(
            int(conversation_id),
            source_message_id=_normalize_state_mutation_source_message_id(source_message_id),
            target_kind=STATE_MUTATION_TARGET_SCRATCHPAD_SECTION,
            target_key=section_id,
            operation=STATE_MUTATION_OPERATION_REPLACE,
            before_value={"content": current_content},
            after_value={"content": normalized_content},
        )
    return {
        "status": "replaced",
        "section": section_id,
        "scratchpad": normalized_content,
        "scratchpad_sections": get_all_scratchpad_sections(settings),
    }, "Scratchpad content replaced successfully"


def save_app_settings(settings: dict) -> None:
    normalized_settings = dict(settings or {})
    has_section_keys = any(key in normalized_settings for key in SCRATCHPAD_SECTION_SETTING_KEYS.values())
    if "user_preferences" in normalized_settings and "general_instructions" not in normalized_settings:
        normalized_settings["general_instructions"] = normalize_assistant_behavior_text(normalized_settings.get("user_preferences"))
    if "general_instructions" in normalized_settings:
        normalized_settings["general_instructions"] = normalize_assistant_behavior_text(normalized_settings.get("general_instructions"))
        normalized_settings["user_preferences"] = normalized_settings["general_instructions"]
    if "ai_personality" in normalized_settings:
        normalized_settings["ai_personality"] = normalize_assistant_behavior_text(normalized_settings.get("ai_personality"))
    if "scratchpad" in normalized_settings:
        legacy_value = normalize_scratchpad_text(normalized_settings.pop("scratchpad"))
        if not has_section_keys:
            normalized_settings[SCRATCHPAD_SECTION_SETTING_KEYS[SCRATCHPAD_DEFAULT_SECTION]] = legacy_value
        normalized_settings["scratchpad"] = ""

    with get_db() as conn:
        for key, value in normalized_settings.items():
            _upsert_app_setting(conn, key, _normalize_app_setting_value(key, value))


def cache_get(key: str):
    ttl_hours = get_web_cache_ttl_hours()
    if ttl_hours <= 0:
        return None
    with get_db() as conn:
        row = conn.execute(
            "SELECT value FROM web_cache WHERE key = ? AND cached_at > datetime('now', ?)",
            (key, f"-{ttl_hours} hours"),
        ).fetchone()
    if row:
        try:
            return json.loads(row["value"])
        except Exception:
            return None
    return None


def cache_set(key: str, value) -> None:
    if get_web_cache_ttl_hours() <= 0:
        return
    with get_db() as conn:
        conn.execute(
            """INSERT INTO web_cache (key, value, cached_at)
               VALUES (?, ?, datetime('now'))
               ON CONFLICT(key) DO UPDATE SET
                   value     = excluded.value,
                   cached_at = excluded.cached_at""",
            (key, json.dumps(value, ensure_ascii=False)),
        )


def normalize_active_tool_names(raw_value) -> list[str]:
    if isinstance(raw_value, list):
        names = raw_value
    else:
        try:
            names = json.loads(raw_value or "[]")
        except Exception:
            names = []

    normalized = []
    allowed = set(TOOL_SPEC_BY_NAME)
    for name in names:
        if isinstance(name, str) and name in allowed and name not in normalized:
            normalized.append(name)
    return normalized


def normalize_sub_agent_allowed_tool_names(raw_value) -> list[str]:
    if raw_value in (None, ""):
        return list(SUB_AGENT_ALLOWED_TOOL_NAMES)

    if isinstance(raw_value, list):
        names = raw_value
    else:
        try:
            names = json.loads(raw_value or "[]")
        except Exception:
            names = []

    normalized = []
    allowed = set(SUB_AGENT_ALLOWED_TOOL_NAMES)
    for name in names:
        if isinstance(name, str) and name in allowed and name not in normalized:
            normalized.append(name)
    return normalized


def normalize_rag_source_types(raw_value) -> list[str]:
    if raw_value in (None, ""):
        return list(RAG_SOURCE_TYPE_SETTING_OPTIONS)

    if isinstance(raw_value, list):
        values = raw_value
    else:
        parsed = None
        if isinstance(raw_value, str):
            try:
                parsed = json.loads(raw_value or "[]")
            except Exception:
                parsed = [part.strip() for part in raw_value.split(",") if part.strip()]
        values = parsed if isinstance(parsed, list) else []

    normalized: list[str] = []
    for value in values:
        candidate = str(value or "").strip().lower()
        if candidate in RAG_SOURCE_TYPE_SETTING_OPTIONS and candidate not in normalized:
            normalized.append(candidate)

    return normalized


def _ensure_tool(name: str, names: list[str]) -> list[str]:
    if name in names:
        return names
    return [*names, name]


_CANVAS_EDIT_TOOL_NAMES = {
    "rewrite_canvas_document",
    "replace_canvas_lines",
    "insert_canvas_lines",
    "delete_canvas_lines",
    "delete_canvas_document",
    "clear_canvas",
}
_CANVAS_INSPECTION_TOOL_NAMES = ("expand_canvas_document", "scroll_canvas_document")


def _ensure_canvas_inspection_tools(names: list[str]) -> list[str]:
    if not any(name in _CANVAS_EDIT_TOOL_NAMES for name in names):
        return names
    for tool_name in _CANVAS_INSPECTION_TOOL_NAMES:
        names = _ensure_tool(tool_name, names)
    return names


def get_active_tool_names(settings: dict | None = None) -> list[str]:
    source = settings if settings is not None else get_app_settings()
    names = normalize_active_tool_names(source.get("active_tools"))
    if not RAG_ENABLED:
        names = [name for name in names if name != "search_knowledge_base"]
    if not IMAGE_UPLOADS_ENABLED:
        names = [name for name in names if name != "image_explain"]
    if not CONVERSATION_MEMORY_ENABLED:
        names = [
            name
            for name in names
            if name not in {"save_to_conversation_memory", "delete_conversation_memory_entry"}
        ]
    if names:
        if any(name in names for name in {"append_scratchpad", "replace_scratchpad"}):
            names = _ensure_tool("replace_scratchpad", names)
            names = _ensure_tool("read_scratchpad", names)
        return names
    if source.get("active_tools") is None:
        names = normalize_active_tool_names(DEFAULT_SETTINGS["active_tools"])
        if not RAG_ENABLED:
            names = [name for name in names if name != "search_knowledge_base"]
        if not IMAGE_UPLOADS_ENABLED:
            names = [name for name in names if name != "image_explain"]
        if not CONVERSATION_MEMORY_ENABLED:
            names = [
                name
                for name in names
                if name not in {"save_to_conversation_memory", "delete_conversation_memory_entry"}
            ]
        if any(name in names for name in {"append_scratchpad", "replace_scratchpad"}):
            names = _ensure_tool("replace_scratchpad", names)
            names = _ensure_tool("read_scratchpad", names)
        names = _ensure_canvas_inspection_tools(names)
        return names
    return []


def get_model_temperature(settings: dict | None = None) -> float:
    source = settings if settings is not None else get_app_settings()
    raw_value = source.get("temperature", DEFAULT_SETTINGS["temperature"])
    try:
        temperature = float(raw_value)
    except (TypeError, ValueError):
        temperature = float(DEFAULT_SETTINGS["temperature"])
    return max(0.0, min(2.0, temperature))


def get_rag_auto_inject_enabled(settings: dict | None = None) -> bool:
    if not RAG_ENABLED:
        return False
    source = settings if settings is not None else get_app_settings()
    raw_value = source.get("rag_auto_inject", DEFAULT_SETTINGS["rag_auto_inject"])
    return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}


def get_rag_sensitivity(settings: dict | None = None) -> str:
    source = settings if settings is not None else get_app_settings()
    raw_value = str(source.get("rag_sensitivity", DEFAULT_SETTINGS["rag_sensitivity"]) or "").strip().lower()
    if raw_value in RAG_SENSITIVITY_PRESETS:
        return raw_value
    return RAG_DEFAULT_SENSITIVITY_PRESET


def get_rag_context_size(settings: dict | None = None) -> str:
    source = settings if settings is not None else get_app_settings()
    raw_value = str(source.get("rag_context_size", DEFAULT_SETTINGS["rag_context_size"]) or "").strip().lower()
    if raw_value in RAG_CONTEXT_SIZE_PRESETS:
        return raw_value
    return RAG_DEFAULT_CONTEXT_SIZE_PRESET


def get_rag_source_types(settings: dict | None = None) -> list[str]:
    if not RAG_ENABLED:
        return []
    source = settings if settings is not None else get_app_settings()
    raw_value = source.get("rag_source_types", DEFAULT_SETTINGS["rag_source_types"])
    return normalize_rag_source_types(raw_value)


def get_rag_auto_inject_source_types(settings: dict | None = None) -> list[str]:
    if not RAG_ENABLED:
        return []
    source = settings if settings is not None else get_app_settings()
    raw_value = source.get("rag_auto_inject_source_types", DEFAULT_SETTINGS["rag_auto_inject_source_types"])
    return normalize_rag_source_types(raw_value)


def get_rag_auto_inject_top_k(settings: dict | None = None) -> int:
    return int(RAG_CONTEXT_SIZE_PRESETS[get_rag_context_size(settings)])


def get_context_selection_strategy(settings: dict | None = None) -> str:
    source = settings if settings is not None else get_app_settings()
    raw_value = str(source.get("context_selection_strategy", DEFAULT_SETTINGS["context_selection_strategy"]) or "").strip().lower()
    if raw_value in CONTEXT_SELECTION_ALLOWED_STRATEGIES:
        return raw_value
    return DEFAULT_SETTINGS["context_selection_strategy"]


def get_entropy_profile(settings: dict | None = None) -> str:
    source = settings if settings is not None else get_app_settings()
    raw_value = str(source.get("entropy_profile", DEFAULT_SETTINGS["entropy_profile"]) or "").strip().lower()
    if raw_value in ENTROPY_PROFILE_PRESETS:
        return raw_value
    return DEFAULT_SETTINGS["entropy_profile"]


def get_entropy_rag_budget_ratio(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    raw_value = source.get("entropy_rag_budget_ratio", DEFAULT_SETTINGS["entropy_rag_budget_ratio"])
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = int(DEFAULT_SETTINGS["entropy_rag_budget_ratio"])
    return max(0, min(80, value))


def get_entropy_protect_code_blocks_enabled(settings: dict | None = None) -> bool:
    source = settings if settings is not None else get_app_settings()
    raw_value = source.get("entropy_protect_code_blocks", DEFAULT_SETTINGS["entropy_protect_code_blocks"])
    return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}


def get_entropy_protect_tool_results_enabled(settings: dict | None = None) -> bool:
    source = settings if settings is not None else get_app_settings()
    raw_value = source.get("entropy_protect_tool_results", DEFAULT_SETTINGS["entropy_protect_tool_results"])
    return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}


def get_entropy_reference_boost_enabled(settings: dict | None = None) -> bool:
    source = settings if settings is not None else get_app_settings()
    raw_value = source.get("entropy_reference_boost", DEFAULT_SETTINGS["entropy_reference_boost"])
    return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}


def get_tool_memory_auto_inject_enabled(settings: dict | None = None) -> bool:
    if not RAG_ENABLED:
        return False
    source = settings if settings is not None else get_app_settings()
    raw_value = source.get("tool_memory_auto_inject", DEFAULT_SETTINGS["tool_memory_auto_inject"])
    return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}


def get_chat_summary_mode(settings: dict | None = None) -> str:
    source = settings if settings is not None else get_app_settings()
    raw_value = str(source.get("chat_summary_mode", DEFAULT_SETTINGS["chat_summary_mode"]) or "").strip().lower()
    if raw_value in CHAT_SUMMARY_ALLOWED_MODES:
        return raw_value
    fallback = CHAT_SUMMARY_MODE if CHAT_SUMMARY_MODE in CHAT_SUMMARY_ALLOWED_MODES else "auto"
    return fallback


def get_chat_summary_trigger_token_count(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    raw_value = source.get("chat_summary_trigger_token_count")
    if raw_value in (None, ""):
        raw_value = source.get(
            "chat_summary_trigger_message_count",
            DEFAULT_SETTINGS["chat_summary_trigger_token_count"],
        )
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = CHAT_SUMMARY_TRIGGER_TOKEN_COUNT
    return max(1_000, min(200_000, value))


def get_chat_summary_detail_level(settings: dict | None = None) -> str:
    source = settings if settings is not None else get_app_settings()
    raw_value = str(source.get("chat_summary_detail_level", DEFAULT_SETTINGS["chat_summary_detail_level"]) or "").strip().lower()
    if raw_value in CHAT_SUMMARY_DETAIL_LEVELS:
        return raw_value
    return DEFAULT_SETTINGS["chat_summary_detail_level"]


def get_summary_skip_first(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    raw_value = source.get("summary_skip_first", DEFAULT_SETTINGS["summary_skip_first"])
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = 2
    return max(0, min(20, value))


def get_summary_skip_last(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    raw_value = source.get("summary_skip_last", DEFAULT_SETTINGS["summary_skip_last"])
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = 1
    return max(0, min(20, value))


def get_clarification_max_questions(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    raw_value = source.get("clarification_max_questions", DEFAULT_SETTINGS["clarification_max_questions"])
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = CLARIFICATION_DEFAULT_MAX_QUESTIONS
    return max(CLARIFICATION_QUESTION_LIMIT_MIN, min(CLARIFICATION_QUESTION_LIMIT_MAX, value))


def get_canvas_prompt_max_lines(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    raw_value = source.get("canvas_prompt_max_lines", DEFAULT_SETTINGS["canvas_prompt_max_lines"])
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = CANVAS_PROMPT_DEFAULT_MAX_LINES
    return max(100, min(3_000, value))


def get_canvas_prompt_max_tokens(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    raw_value = source.get("canvas_prompt_max_tokens", DEFAULT_SETTINGS["canvas_prompt_max_tokens"])
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = CANVAS_PROMPT_DEFAULT_MAX_TOKENS
    return max(500, min(50_000, value))


def get_canvas_prompt_max_chars(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    raw_value = source.get("canvas_prompt_max_chars", DEFAULT_SETTINGS["canvas_prompt_max_chars"])
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = CANVAS_PROMPT_DEFAULT_MAX_CHARS
    return max(1_000, min(200_000, value))


def get_canvas_prompt_code_line_max_chars(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    raw_value = source.get(
        "canvas_prompt_code_line_max_chars",
        DEFAULT_SETTINGS["canvas_prompt_code_line_max_chars"],
    )
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = CANVAS_PROMPT_CODE_LINE_MAX_CHARS
    return max(40, min(1_000, value))


def get_canvas_prompt_text_line_max_chars(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    raw_value = source.get(
        "canvas_prompt_text_line_max_chars",
        DEFAULT_SETTINGS["canvas_prompt_text_line_max_chars"],
    )
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = CANVAS_PROMPT_TEXT_LINE_MAX_CHARS
    return max(40, min(1_000, value))


def get_canvas_expand_max_lines(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    raw_value = source.get("canvas_expand_max_lines", DEFAULT_SETTINGS["canvas_expand_max_lines"])
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = CANVAS_EXPAND_DEFAULT_MAX_LINES
    return max(100, min(4_000, value))


def get_canvas_scroll_window_lines(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    raw_value = source.get("canvas_scroll_window_lines", DEFAULT_SETTINGS["canvas_scroll_window_lines"])
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = CANVAS_SCROLL_WINDOW_LINES
    return max(50, min(800, value))


def get_sub_agent_max_steps(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    raw_value = source.get("sub_agent_max_steps", SUB_AGENT_DEFAULT_MAX_STEPS)
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = SUB_AGENT_DEFAULT_MAX_STEPS
    return max(SUB_AGENT_MAX_STEPS_MIN, min(SUB_AGENT_MAX_STEPS_MAX, value))


def get_sub_agent_allowed_tool_names(settings: dict | None = None) -> list[str]:
    source = settings if settings is not None else get_app_settings()
    return normalize_sub_agent_allowed_tool_names(source.get("sub_agent_allowed_tool_names"))


def get_web_cache_ttl_hours(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    raw_value = source.get("web_cache_ttl_hours", DEFAULT_WEB_CACHE_TTL_HOURS)
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = DEFAULT_WEB_CACHE_TTL_HOURS
    return max(WEB_CACHE_TTL_HOURS_MIN, min(WEB_CACHE_TTL_HOURS_MAX, value))


def get_openrouter_prompt_cache_enabled(settings: dict | None = None) -> bool:
    source = settings if settings is not None else get_app_settings()
    raw_value = source.get("openrouter_prompt_cache_enabled")
    if raw_value is None:
        return OPENROUTER_PROMPT_CACHE_DEFAULT_ENABLED
    return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}


def get_sub_agent_timeout_seconds(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    raw_value = source.get("sub_agent_timeout_seconds", SUB_AGENT_DEFAULT_TIMEOUT_SECONDS)
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = SUB_AGENT_DEFAULT_TIMEOUT_SECONDS
    return max(SUB_AGENT_TIMEOUT_MIN_SECONDS, min(SUB_AGENT_TIMEOUT_MAX_SECONDS, value))


def get_sub_agent_retry_attempts(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    raw_value = source.get("sub_agent_retry_attempts", SUB_AGENT_DEFAULT_RETRY_ATTEMPTS)
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = SUB_AGENT_DEFAULT_RETRY_ATTEMPTS
    return max(SUB_AGENT_RETRY_ATTEMPTS_MIN, min(SUB_AGENT_RETRY_ATTEMPTS_MAX, value))


def get_sub_agent_retry_delay_seconds(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    raw_value = source.get("sub_agent_retry_delay_seconds", SUB_AGENT_DEFAULT_RETRY_DELAY_SECONDS)
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = SUB_AGENT_DEFAULT_RETRY_DELAY_SECONDS
    return max(SUB_AGENT_RETRY_DELAY_MIN_SECONDS, min(SUB_AGENT_RETRY_DELAY_MAX_SECONDS, value))


def get_max_parallel_tools(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    raw_value = source.get("max_parallel_tools", DEFAULT_SETTINGS["max_parallel_tools"])
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = DEFAULT_MAX_PARALLEL_TOOLS
    return max(MAX_PARALLEL_TOOLS_MIN, min(MAX_PARALLEL_TOOLS_MAX, value))


def get_sub_agent_max_parallel_tools(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    raw_value = source.get("sub_agent_max_parallel_tools")
    if raw_value in (None, ""):
        raw_value = source.get("max_parallel_tools", SUB_AGENT_DEFAULT_MAX_PARALLEL_TOOLS)
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = SUB_AGENT_DEFAULT_MAX_PARALLEL_TOOLS
    return max(MAX_PARALLEL_TOOLS_MIN, min(MAX_PARALLEL_TOOLS_MAX, value))


def _get_int_setting_value(
    source: dict,
    key: str,
    default_value: int,
    minimum: int,
    maximum: int,
) -> int:
    raw_value = source.get(key, default_value)
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = int(default_value)
    return max(minimum, min(maximum, value))


def _get_float_setting_value(
    source: dict,
    key: str,
    default_value: float,
    minimum: float,
    maximum: float,
) -> float:
    raw_value = source.get(key, default_value)
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        value = float(default_value)
    return max(minimum, min(maximum, value))


def get_prompt_max_input_tokens(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    return _get_int_setting_value(
        source,
        "prompt_max_input_tokens",
        PROMPT_MAX_INPUT_TOKENS,
        8_000,
        120_000,
    )


def get_prompt_response_token_reserve(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    prompt_max_input_tokens = get_prompt_max_input_tokens(source)
    return _get_int_setting_value(
        source,
        "prompt_response_token_reserve",
        PROMPT_RESPONSE_TOKEN_RESERVE,
        1_000,
        max(1_000, prompt_max_input_tokens - 2_000),
    )


def get_prompt_recent_history_max_tokens(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    prompt_max_input_tokens = get_prompt_max_input_tokens(source)
    return _get_int_setting_value(
        source,
        "prompt_recent_history_max_tokens",
        PROMPT_RECENT_HISTORY_MAX_TOKENS,
        1_000,
        prompt_max_input_tokens,
    )


def get_prompt_summary_max_tokens(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    prompt_max_input_tokens = get_prompt_max_input_tokens(source)
    return _get_int_setting_value(
        source,
        "prompt_summary_max_tokens",
        PROMPT_SUMMARY_MAX_TOKENS,
        500,
        prompt_max_input_tokens,
    )


def get_prompt_rag_max_tokens(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    prompt_max_input_tokens = get_prompt_max_input_tokens(source)
    return _get_int_setting_value(
        source,
        "prompt_rag_max_tokens",
        PROMPT_RAG_MAX_TOKENS,
        0,
        prompt_max_input_tokens,
    )


def get_prompt_tool_memory_max_tokens(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    prompt_max_input_tokens = get_prompt_max_input_tokens(source)
    return _get_int_setting_value(
        source,
        "prompt_tool_memory_max_tokens",
        PROMPT_TOOL_MEMORY_MAX_TOKENS,
        0,
        prompt_max_input_tokens,
    )


def get_prompt_tool_trace_max_tokens(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    prompt_max_input_tokens = get_prompt_max_input_tokens(source)
    return _get_int_setting_value(
        source,
        "prompt_tool_trace_max_tokens",
        PROMPT_TOOL_TRACE_MAX_TOKENS,
        0,
        prompt_max_input_tokens,
    )


def get_context_compaction_threshold(settings: dict | None = None) -> float:
    source = settings if settings is not None else get_app_settings()
    return _get_float_setting_value(
        source,
        "context_compaction_threshold",
        AGENT_CONTEXT_COMPACTION_THRESHOLD,
        0.5,
        0.98,
    )


def get_context_compaction_keep_recent_rounds(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    return _get_int_setting_value(
        source,
        "context_compaction_keep_recent_rounds",
        AGENT_CONTEXT_COMPACTION_KEEP_RECENT_ROUNDS,
        0,
        6,
    )


def get_prompt_preflight_summary_token_count(settings: dict | None = None) -> int:
    del settings
    return PROMPT_PREFLIGHT_SUMMARY_TOKEN_COUNT


def get_summary_source_target_tokens(settings: dict | None = None) -> int:
    del settings
    return SUMMARY_SOURCE_TARGET_TOKENS


def get_summary_retry_min_source_tokens(settings: dict | None = None) -> int:
    del settings
    return SUMMARY_RETRY_MIN_SOURCE_TOKENS


def get_fetch_url_token_threshold(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    raw_value = source.get("fetch_url_token_threshold", DEFAULT_SETTINGS["fetch_url_token_threshold"])
    try:
        threshold = int(raw_value)
    except (TypeError, ValueError):
        threshold = FETCH_SUMMARY_TOKEN_THRESHOLD
    return max(400, min(20_000, threshold))


def get_fetch_url_clip_aggressiveness(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    raw_value = source.get("fetch_url_clip_aggressiveness", DEFAULT_SETTINGS["fetch_url_clip_aggressiveness"])
    try:
        aggressiveness = int(raw_value)
    except (TypeError, ValueError):
        aggressiveness = 50
    return max(0, min(100, aggressiveness))


def get_fetch_url_summarized_max_input_chars(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    return _get_int_setting_value(
        source,
        "fetch_url_summarized_max_input_chars",
        FETCH_SUMMARIZE_MAX_INPUT_CHARS,
        4_000,
        CONTENT_MAX_CHARS,
    )


def get_fetch_url_summarized_max_output_tokens(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    return _get_int_setting_value(
        source,
        "fetch_url_summarized_max_output_tokens",
        FETCH_SUMMARIZE_MAX_OUTPUT_TOKENS,
        200,
        4_000,
    )


def get_fetch_url_to_canvas_chunk_threshold(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    return _get_int_setting_value(
        source,
        "fetch_url_to_canvas_chunk_threshold",
        FETCH_URL_TO_CANVAS_CHUNK_THRESHOLD,
        2_000,
        CONTENT_MAX_CHARS,
    )


def get_fetch_url_to_canvas_chunk_chars(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    return _get_int_setting_value(
        source,
        "fetch_url_to_canvas_chunk_chars",
        FETCH_URL_TO_CANVAS_CHUNK_CHARS,
        4_000,
        CONTENT_MAX_CHARS,
    )


def get_fetch_url_to_canvas_max_chunks(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    return _get_int_setting_value(
        source,
        "fetch_url_to_canvas_max_chunks",
        FETCH_URL_TO_CANVAS_MAX_CHUNKS,
        1,
        20,
    )


def get_pruning_enabled(settings: dict | None = None) -> bool:
    source = settings if settings is not None else get_app_settings()
    raw_value = source.get("pruning_enabled", DEFAULT_SETTINGS["pruning_enabled"])
    return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}


def get_reasoning_auto_collapse(settings: dict | None = None) -> bool:
    source = settings if settings is not None else get_app_settings()
    raw_value = source.get("reasoning_auto_collapse", DEFAULT_SETTINGS["reasoning_auto_collapse"])
    return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}


def get_pruning_token_threshold(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    raw_value = source.get("pruning_token_threshold", DEFAULT_SETTINGS["pruning_token_threshold"])
    try:
        threshold = int(raw_value)
    except (TypeError, ValueError):
        threshold = CHAT_SUMMARY_TRIGGER_TOKEN_COUNT
    return max(1_000, min(200_000, threshold))


def get_pruning_batch_size(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    raw_value = source.get("pruning_batch_size", DEFAULT_SETTINGS["pruning_batch_size"])
    try:
        batch_size = int(raw_value)
    except (TypeError, ValueError):
        batch_size = 10
    return max(1, min(50, batch_size))


def get_pruning_target_reduction_ratio(settings: dict | None = None) -> float:
    source = settings if settings is not None else get_app_settings()
    return _get_float_setting_value(
        source,
        "pruning_target_reduction_ratio",
        PRUNING_TARGET_REDUCTION_RATIO,
        0.1,
        0.9,
    )


def get_pruning_min_target_tokens(settings: dict | None = None) -> int:
    source = settings if settings is not None else get_app_settings()
    return _get_int_setting_value(
        source,
        "pruning_min_target_tokens",
        PRUNING_MIN_TARGET_TOKENS,
        50,
        5_000,
    )


def get_next_message_position(conn: sqlite3.Connection, conversation_id: int) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(position), 0) AS max_position FROM messages WHERE conversation_id = ?",
        (conversation_id,),
    ).fetchone()
    max_position = row["max_position"] if row else 0
    return int(max_position or 0) + 1


def insert_message(
    conn: sqlite3.Connection,
    conversation_id: int,
    role: str,
    content: str,
    metadata: str | None = None,
    tool_calls: str | None = None,
    tool_call_id: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    position: int | None = None,
) -> int:
    normalized_role = str(role or "").strip()
    normalized_content = content if isinstance(content, str) else str(content or "")
    cursor = conn.execute(
        """INSERT INTO messages (
               conversation_id, position, role, content, metadata, tool_calls, tool_call_id,
               prompt_tokens, completion_tokens, total_tokens
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            conversation_id,
            position,
            normalized_role,
            normalized_content,
            metadata,
            tool_calls,
            tool_call_id,
            prompt_tokens,
            completion_tokens,
            total_tokens,
        ),
    )
    return int(cursor.lastrowid)


def update_message_metadata(message_id: int, metadata_updates: dict | None) -> None:
    normalized_message_id = int(message_id or 0)
    if normalized_message_id <= 0:
        return

    updates = metadata_updates if isinstance(metadata_updates, dict) else {}
    with get_db() as conn:
        row = conn.execute("SELECT metadata FROM messages WHERE id = ?", (normalized_message_id,)).fetchone()
        if row is None:
            return

        merged = parse_message_metadata(row["metadata"], include_private_fields=True)
        for key, value in updates.items():
            if value in (None, "", [], {}):
                merged.pop(key, None)
                continue
            merged[key] = value

        conn.execute(
            "UPDATE messages SET metadata = ? WHERE id = ?",
            (serialize_message_metadata(merged, include_private_fields=True), normalized_message_id),
        )


def get_conversation_message_rows(
    conn: sqlite3.Connection,
    conversation_id: int,
    include_deleted: bool = False,
) -> list[sqlite3.Row]:
    query = (
        """SELECT id, position, role, content, metadata, tool_calls, tool_call_id,
                  prompt_tokens, completion_tokens, total_tokens, created_at, deleted_at
           FROM messages
           WHERE conversation_id = ?"""
    )
    params: list[object] = [conversation_id]
    if not include_deleted:
        query += " AND deleted_at IS NULL"
    query += " ORDER BY position, id"
    return conn.execute(query, tuple(params)).fetchall()


def get_conversation_messages(conversation_id: int, include_deleted: bool = False) -> list[dict]:
    with get_db() as conn:
        rows = get_conversation_message_rows(conn, conversation_id, include_deleted=include_deleted)
    return [message_row_to_dict(row) for row in rows]


def soft_delete_messages(
    conn: sqlite3.Connection,
    conversation_id: int,
    message_ids: Iterable[int],
    deleted_at: str,
) -> None:
    normalized_ids = [int(message_id) for message_id in message_ids if int(message_id) > 0]
    if not normalized_ids:
        return
    placeholders = ", ".join("?" for _ in normalized_ids)
    conn.execute(
        f"UPDATE messages SET deleted_at = ? WHERE conversation_id = ? AND id IN ({placeholders}) AND deleted_at IS NULL",
        (deleted_at, conversation_id, *normalized_ids),
    )


def mark_messages_deleted_by_edit_replay(
    conn: sqlite3.Connection,
    conversation_id: int,
    message_ids: Iterable[int],
) -> None:
    """Stamp soft-deleted edit-replay messages so RAG sync skips archiving them."""
    normalized_ids = [int(mid) for mid in message_ids if int(mid) > 0]
    if not normalized_ids:
        return
    placeholders = ", ".join("?" for _ in normalized_ids)
    rows = conn.execute(
        f"SELECT id, metadata FROM messages WHERE conversation_id = ? AND id IN ({placeholders})",
        (conversation_id, *normalized_ids),
    ).fetchall()
    for row in rows:
        try:
            meta = json.loads(row["metadata"]) if row["metadata"] else {}
            if not isinstance(meta, dict):
                meta = {}
        except Exception:
            meta = {}
        meta["_edit_replay_deleted"] = True
        conn.execute(
            "UPDATE messages SET metadata = ? WHERE id = ?",
            (json.dumps(meta, ensure_ascii=False), row["id"]),
        )


def restore_soft_deleted_messages(
    conn: sqlite3.Connection,
    conversation_id: int,
    message_ids: Iterable[int],
) -> int:
    normalized_ids = [int(message_id) for message_id in message_ids if int(message_id) > 0]
    if not normalized_ids:
        return 0
    placeholders = ", ".join("?" for _ in normalized_ids)
    cursor = conn.execute(
        f"UPDATE messages SET deleted_at = NULL WHERE conversation_id = ? AND id IN ({placeholders}) AND deleted_at IS NOT NULL",
        (conversation_id, *normalized_ids),
    )
    return max(0, int(cursor.rowcount or 0))


def shift_message_positions(
    conn: sqlite3.Connection,
    conversation_id: int,
    start_position: int,
    delta: int,
    exclude_message_ids: Iterable[int] | None = None,
) -> None:
    if delta == 0:
        return
    normalized_start = int(start_position or 0)
    excluded_ids = [int(message_id) for message_id in (exclude_message_ids or []) if int(message_id) > 0]
    query = "UPDATE messages SET position = position + ? WHERE conversation_id = ? AND position >= ?"
    params: list[object] = [delta, conversation_id, normalized_start]
    if excluded_ids:
        placeholders = ", ".join("?" for _ in excluded_ids)
        query += f" AND id NOT IN ({placeholders})"
        params.extend(excluded_ids)
    conn.execute(query, tuple(params))


def is_renderable_chat_message(message: dict) -> bool:
    if not isinstance(message, dict):
        return False
    role = str(message.get("role") or "").strip()
    if role == "assistant":
        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list) and tool_calls:
            return False
    return role in VISIBLE_CHAT_ROLES


def count_visible_message_tokens(messages: list[dict], include_context_injections: bool = True) -> int:
    total = 0
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "").strip()
        if role == "assistant":
            tool_calls = message.get("tool_calls")
            if isinstance(tool_calls, list) and tool_calls:
                continue
        if role not in {"user", "assistant", "tool", "summary"}:
            continue
        total += estimate_text_tokens(str(message.get("content") or ""))
        if not include_context_injections:
            continue
        metadata = parse_message_metadata(message.get("metadata"))
        context_injection = str(metadata.get("context_injection") or "").strip()
        if context_injection:
            total += estimate_text_tokens(context_injection)
    return total


def get_unsummarized_visible_messages(
    messages: list[dict],
    limit: int | None = None,
    skip_first: int = 0,
    skip_last: int = 0,
) -> list[dict]:
    ordered_messages = sorted(
        (message for message in messages if isinstance(message, dict)),
        key=lambda message: (int(message.get("position") or 0), int(message.get("id") or 0)),
    )
    candidates = []
    for message in ordered_messages:
        if not is_renderable_chat_message(message):
            continue
        role = str(message.get("role") or "").strip()
        if role == "summary":
            continue
        candidates.append(message)

    skip_first = max(0, skip_first)
    skip_last = max(0, skip_last)
    if skip_first + skip_last >= len(candidates):
        return []
    eligible = candidates[skip_first:len(candidates) - skip_last] if skip_last > 0 else candidates[skip_first:]

    if limit is not None:
        eligible = eligible[:limit]
    return eligible


def find_summary_covering_message_id(conversation_id: int, message_id: int) -> dict | None:
    target_id = _coerce_non_negative_int(message_id)
    if target_id is None:
        return None
    for message in get_conversation_messages(conversation_id):
        metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
        covered_ids = metadata.get("covered_message_ids") if isinstance(metadata.get("covered_message_ids"), list) else []
        if target_id in covered_ids:
            return message
    return None
