from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import html
import hashlib
import json
import logging
import math
import os
import re
import time
from datetime import datetime, timezone
from threading import Lock

from flask import current_app, has_app_context

from config import (
    RAG_DISABLED_FEATURE_ERROR,
    RAG_ENABLED,
    RAG_MAX_CHUNKS_PER_SOURCE,
    RAG_QUERY_EXPANSION_ENABLED,
    RAG_QUERY_EXPANSION_MAX_VARIANTS,
    RAG_SEARCH_DEFAULT_TOP_K,
    RAG_SEARCH_MIN_SIMILARITY,
    RAG_SOURCE_CONVERSATION,
    RAG_SOURCE_TOOL_MEMORY,
    RAG_SOURCE_TOOL_RESULT,
    RAG_SOURCE_UPLOADED_DOCUMENT,
    RAG_SUPPORTED_CATEGORIES,
    RAG_SUPPORTED_SOURCE_TYPES,
    RAG_TEMPORAL_DECAY_ALPHA,
    RAG_TEMPORAL_DECAY_LAMBDA,
    TOOL_MEMORY_TTL_DEFAULT_SECONDS,
    TOOL_MEMORY_TTL_NEWS_SECONDS,
    TOOL_MEMORY_TTL_WEB_SECONDS,
)
from db import (
    delete_rag_document_records,
    extract_clarification_response,
    extract_message_tool_results,
    get_db,
    get_expired_rag_document_source_keys,
    get_rag_source_types,
    parse_message_metadata,
)
from messages import build_user_message_for_model
from rag import (
    chunks_from_records,
    chunks_from_text,
    normalize_category,
)
from rag import (
    delete_source as rag_delete_source,
)
from rag import (
    get_source_chunks as rag_get_source_chunks,
)
from rag import (
    query_chunks as rag_query_chunks,
)
from rag import (
    upsert_chunks as rag_upsert_chunks,
)

_rag_sources_verified = False
_rag_sources_last_verified_at = 0.0
_RAG_SOURCES_VERIFY_COOLDOWN_SECS = 60.0
_rag_background_executor = None
_rag_background_executor_lock = Lock()
_rag_background_sync_jobs: dict[str, dict] = {}
_rag_background_sync_jobs_lock = Lock()
_RAG_ALL_CONVERSATIONS_SYNC_KEY = "__all__"
CATEGORY_TOOL_MEMORY = RAG_SOURCE_TOOL_MEMORY
DYNAMIC_RAG_CATEGORIES = {RAG_SOURCE_CONVERSATION, RAG_SOURCE_TOOL_MEMORY, RAG_SOURCE_TOOL_RESULT}
AUTO_INJECT_EXCERPT_LIMIT = 560
AUTO_INJECT_STRONG_MATCH_MARGIN = 0.12
MANUAL_UPLOAD_DESCRIPTION_LIMIT = 1_200
logger = logging.getLogger(__name__)


def _require_rag_enabled() -> None:
    if not RAG_ENABLED:
        raise RuntimeError(RAG_DISABLED_FEATURE_ERROR)


def _clean_rag_text_block(text: str, limit: int | None = None) -> str:
    cleaned = re.sub(r"\n{3,}", "\n\n", str(text or "").strip())
    if limit and len(cleaned) > limit:
        return cleaned[:limit].rstrip() + "…"
    return cleaned


def _sanitize_tool_result_text(text: str) -> str:
    cleaned = html.unescape(str(text or ""))
    cleaned = re.sub(r"[\u00ad\u200b-\u200f\u2028\u2029\ufeff]", "", cleaned)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    return _clean_rag_text_block(cleaned)


def _resolve_background_app(app_obj=None):
    if app_obj is not None:
        return app_obj
    if has_app_context():
        return current_app._get_current_object()
    raise RuntimeError("A Flask app object is required for background RAG work.")


def _get_rag_background_executor() -> ThreadPoolExecutor:
    global _rag_background_executor
    if _rag_background_executor is not None:
        return _rag_background_executor
    with _rag_background_executor_lock:
        if _rag_background_executor is not None:
            return _rag_background_executor
        _rag_background_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rag-sync")
        return _rag_background_executor


def _normalize_allowed_source_types(
    allowed_source_types: set[str] | list[str] | tuple[str, ...] | None,
) -> set[str] | None:
    if allowed_source_types is None:
        return set(get_rag_source_types())
    return {
        normalize_category(value)
        for value in allowed_source_types
        if normalize_category(value) in RAG_SUPPORTED_SOURCE_TYPES
    }


def _coerce_metadata_bool(metadata: dict | None, key: str, default: bool = True) -> bool:
    source = metadata if isinstance(metadata, dict) else {}
    value = source.get(key)
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


def _coerce_optional_timestamp(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        normalized = int(value)
        return normalized if normalized > 0 else None
    text = str(value or "").strip()
    if not text:
        return None
    try:
        normalized = int(float(text))
    except (TypeError, ValueError):
        return None
    return normalized if normalized > 0 else None


def normalize_rag_category(category: str | None, default: str | None = RAG_SOURCE_CONVERSATION) -> str | None:
    cleaned = normalize_category(category)
    if cleaned in RAG_SUPPORTED_CATEGORIES:
        return cleaned
    if default is None:
        return None
    fallback = normalize_category(default)
    return fallback if fallback in RAG_SUPPORTED_CATEGORIES else None


def _is_supported_rag_source_type(source_type: str | None) -> bool:
    return normalize_category(source_type) in RAG_SUPPORTED_SOURCE_TYPES


def build_rag_source_key(source_type: str, source_name: str) -> str:
    normalized_type = str(source_type or "document").strip().lower() or "document"
    normalized_name = str(source_name or "untitled").strip() or "untitled"
    digest = hashlib.sha1(f"{normalized_type}|{normalized_name}".encode("utf-8")).hexdigest()
    return f"src-{digest}"


def _build_rag_sync_signature(payload) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(serialized.encode("utf-8")).hexdigest()


def _conversation_rag_source_name(source_type: str, conversation_id: int, title: str) -> str:
    title = str(title or "Untitled")[:80]
    return f"{source_type}:{conversation_id}:{title}"


def conversation_rag_source_key(source_type: str, conversation_id: int) -> str:
    return build_rag_source_key(source_type, str(conversation_id))


def conversation_archived_rag_source_key(conversation_id: int) -> str:
    return build_rag_source_key(RAG_SOURCE_CONVERSATION, f"{int(conversation_id)}:archived")


def _conversation_archived_rag_source_name(conversation_id: int, title: str) -> str:
    title = str(title or "Untitled")[:80]
    return f"conversation_archive:{conversation_id}:{title}"


def _build_archived_conversation_record(role: str, content: str, metadata: dict | None, deleted_at: str) -> dict | None:
    normalized_role = str(role or "").strip().lower()
    normalized_content = _clean_rag_text_block(content, limit=2_400)
    if not normalized_content:
        return None

    prefix = f"Hidden transcript message from this conversation. Original role: {normalized_role or 'unknown'}."
    deleted_at_text = str(deleted_at or "").strip()
    if deleted_at_text:
        prefix += f" Hidden at: {deleted_at_text}."

    tool_lines: list[str] = []
    for entry in extract_message_tool_results(metadata):
        tool_name = str(entry.get("tool_name") or "tool").strip() or "tool"
        tool_text = _clean_rag_text_block(
            str(entry.get("summary") or entry.get("content") or entry.get("raw_content") or ""),
            limit=320,
        )
        if tool_text:
            tool_lines.append(f"- {tool_name}: {tool_text}")

    parts = [prefix, normalized_content]
    if tool_lines:
        parts.append("Associated tool findings:\n" + "\n".join(tool_lines[:6]))
    return {
        "role": "archived_conversation",
        "content": "\n\n".join(part for part in parts if part).strip(),
    }


def build_tool_memory_source_key(tool_name: str, args_hash: str) -> str:
    normalized_tool_name = normalize_category(tool_name) or "tool"
    normalized_args_hash = str(args_hash or "").strip() or "unknown"
    return build_rag_source_key(RAG_SOURCE_TOOL_MEMORY, f"{normalized_tool_name}:{normalized_args_hash}")


def build_tool_result_record_content(entry: dict, index: int) -> str:
    parts = [f"[{index}] tool:{entry['tool_name']}"]
    if entry.get("input_preview"):
        parts.append(f"Input: {entry['input_preview']}")
    if entry.get("summary"):
        parts.append(f"Summary: {entry['summary']}")
    if entry.get("content_mode"):
        parts.append(f"Content mode: {entry['content_mode']}")
    if entry.get("summary_notice"):
        parts.append(f"Note: {entry['summary_notice']}")
    parts.append(_sanitize_tool_result_text(entry.get("content", "")))
    return "\n".join(parts)


def serialize_rag_metadata(metadata: dict | None) -> str | None:
    if not isinstance(metadata, dict) or not metadata:
        return None
    cleaned = {}
    for key, value in metadata.items():
        if value in (None, ""):
            continue
        if isinstance(value, (dict, list, bool, int, float)):
            cleaned[str(key)] = value
        else:
            cleaned[str(key)] = str(value)
    if not cleaned:
        return None
    return json.dumps(cleaned, ensure_ascii=False)


def parse_rag_metadata(raw_metadata) -> dict:
    if isinstance(raw_metadata, dict):
        return raw_metadata
    if not raw_metadata:
        return {}
    try:
        parsed = json.loads(raw_metadata)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _format_utc_timestamp(timestamp: int | None) -> str | None:
    if not isinstance(timestamp, int) or timestamp <= 0:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _tool_memory_ttl_seconds(tool_name: str) -> int:
    normalized_name = normalize_category(tool_name)
    if normalized_name in {"search_news_ddgs", "search_news_google"}:
        return TOOL_MEMORY_TTL_NEWS_SECONDS
    if normalized_name in {"search_web", "fetch_url"}:
        return TOOL_MEMORY_TTL_WEB_SECONDS
    return TOOL_MEMORY_TTL_DEFAULT_SECONDS


def _tool_memory_args_hash(args_preview: str) -> str:
    cleaned_args_preview = _clean_rag_text_block(args_preview, limit=300)
    args_basis = cleaned_args_preview or ""
    return hashlib.sha1(json.dumps(args_basis, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]


def purge_expired_rag_documents() -> int:
    expired_source_keys = get_expired_rag_document_source_keys()
    if not expired_source_keys:
        return 0

    removed = 0
    for source_key in expired_source_keys:
        removed += rag_delete_source(source_key)
    delete_rag_document_records(expired_source_keys)
    return removed


def upsert_rag_document_record(
    source_key: str,
    source_name: str,
    source_type: str,
    category: str,
    chunk_count: int,
    metadata: dict | None = None,
    expires_at: str | None = None,
):
    category = normalize_rag_category(category, default=RAG_SOURCE_CONVERSATION) or RAG_SOURCE_CONVERSATION
    source_type = normalize_category(source_type)
    with get_db() as conn:
        conn.execute(
            """INSERT INTO rag_documents
               (source_key, source_name, source_type, category, chunk_count, metadata, expires_at, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
               ON CONFLICT(source_key) DO UPDATE SET
                   source_name = excluded.source_name,
                   source_type = excluded.source_type,
                   category = excluded.category,
                   chunk_count = excluded.chunk_count,
                   metadata = excluded.metadata,
                   expires_at = excluded.expires_at,
                   updated_at = datetime('now')""",
            (source_key, source_name, source_type, category, int(chunk_count), serialize_rag_metadata(metadata), expires_at),
        )


def _fetch_rag_documents_db() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT source_key, source_name, source_type, category, chunk_count, metadata, expires_at, created_at, updated_at
               FROM rag_documents
               ORDER BY updated_at DESC, source_name ASC"""
        ).fetchall()
    return [
        {
            "source_key": row["source_key"],
            "source_name": row["source_name"],
            "source_type": row["source_type"],
            "category": row["category"],
            "chunk_count": row["chunk_count"],
            "metadata": parse_rag_metadata(row["metadata"]),
            "expires_at": row["expires_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


def ensure_supported_rag_sources(force: bool = False) -> int:
    _require_rag_enabled()
    global _rag_sources_verified, _rag_sources_last_verified_at
    now = time.time()
    removed = purge_expired_rag_documents()
    if _rag_sources_verified and not force and (now - _rag_sources_last_verified_at) < _RAG_SOURCES_VERIFY_COOLDOWN_SECS:
        return removed

    with get_db() as conn:
        rows = conn.execute("SELECT source_key, source_type FROM rag_documents ORDER BY updated_at DESC").fetchall()

    removed_invalid = 0
    for row in rows:
        if _is_supported_rag_source_type(row["source_type"]):
            continue
        rag_delete_source(row["source_key"])
        delete_rag_document_record(row["source_key"])
        removed_invalid += 1

    _rag_sources_verified = True
    _rag_sources_last_verified_at = now
    return removed + removed_invalid


def list_rag_documents_db() -> list[dict]:
    _require_rag_enabled()
    ensure_supported_rag_sources()
    return [doc for doc in _fetch_rag_documents_db() if _is_supported_rag_source_type(doc["source_type"])]


def get_rag_document_record(source_key: str):
    with get_db() as conn:
        return conn.execute(
            "SELECT source_key, source_name, source_type, metadata, expires_at, updated_at FROM rag_documents WHERE source_key = ?",
            (source_key,),
        ).fetchone()


def delete_rag_document_record(source_key: str):
    with get_db() as conn:
        conn.execute("DELETE FROM rag_documents WHERE source_key = ?", (source_key,))


def delete_rag_source_record(source_key: str) -> int:
    _require_rag_enabled()
    deleted_chunks = rag_delete_source(source_key)
    delete_rag_document_record(source_key)
    return deleted_chunks


def _delete_rag_source_if_present(source_key: str) -> int:
    existing = get_rag_document_record(source_key)
    if not existing:
        return 0
    return delete_rag_source_record(source_key)


def _build_conversation_sync_metadata(conversation: dict, source_key: str, sync_signature: str) -> dict:
    metadata = {
        "source_key": source_key,
        "conversation_id": conversation["conversation_id"],
        "title": conversation["title"],
        "sync_signature": sync_signature,
    }
    updated_at = str(conversation.get("updated_at") or "").strip()
    if updated_at:
        metadata["conversation_updated_at"] = updated_at
    return metadata


def _conversation_source_needs_sync(
    source_key: str,
    sync_signature: str | None = None,
    *,
    sync_marker: str | None = None,
    force: bool = False,
) -> bool:
    if force:
        return True
    row = get_rag_document_record(source_key)
    if not row:
        return True
    metadata = parse_rag_metadata(row["metadata"])
    normalized_marker = str(sync_marker or "").strip()
    if normalized_marker and str(metadata.get("conversation_updated_at") or "").strip() != normalized_marker:
        return True
    if sync_signature is None:
        return False
    return metadata.get("sync_signature") != sync_signature


def _normalize_rag_background_sync_key(conversation_id: int | None) -> str:
    if conversation_id is None:
        return _RAG_ALL_CONVERSATIONS_SYNC_KEY
    return f"conversation:{int(conversation_id)}"


def _queue_rag_background_sync_request(conversation_id: int | None, force: bool) -> tuple[str, bool, object | None]:
    job_key = _normalize_rag_background_sync_key(conversation_id)
    with _rag_background_sync_jobs_lock:
        existing = _rag_background_sync_jobs.get(job_key)
        if existing is not None:
            existing["requested"] = True
            existing["force"] = existing.get("force") is True or force is True
            return job_key, False, existing.get("future")
        _rag_background_sync_jobs[job_key] = {
            "requested": True,
            "force": force is True,
            "future": None,
        }
    return job_key, True, None


def _start_rag_background_sync_run(job_key: str) -> bool:
    with _rag_background_sync_jobs_lock:
        entry = _rag_background_sync_jobs.get(job_key)
        if entry is None:
            return False
        force = entry.get("force") is True
        entry["force"] = False
        entry["requested"] = False
        return force


def _finish_rag_background_sync_run(job_key: str) -> bool:
    with _rag_background_sync_jobs_lock:
        entry = _rag_background_sync_jobs.get(job_key)
        if entry is None:
            return False
        if entry.get("requested") is True:
            return True
        _rag_background_sync_jobs.pop(job_key, None)
        return False


def _set_rag_background_sync_future(job_key: str, future) -> None:
    with _rag_background_sync_jobs_lock:
        entry = _rag_background_sync_jobs.get(job_key)
        if entry is not None:
            entry["future"] = future


def _clip_rag_excerpt(text: str, limit: int = 1200) -> str:
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def _normalize_query_tokens(query: str) -> list[str]:
    return [token for token in re.findall(r"[^\W_]+", str(query or "").lower(), flags=re.UNICODE) if token]


def _expand_query_variants(query: str) -> list[str]:
    normalized_query = re.sub(r"\s+", " ", str(query or "").strip())
    if not normalized_query:
        return []

    if not RAG_QUERY_EXPANSION_ENABLED:
        return [normalized_query]

    variants: list[str] = []

    def add_variant(value: str) -> None:
        candidate = re.sub(r"\s+", " ", str(value or "").strip())
        if not candidate:
            return
        key = candidate.casefold()
        if any(existing.casefold() == key for existing in variants):
            return
        variants.append(candidate)

    add_variant(normalized_query)
    cleaned_query = re.sub(r"[^\w\s]+", " ", normalized_query, flags=re.UNICODE)
    add_variant(cleaned_query)

    tokens = _normalize_query_tokens(normalized_query)
    if len(tokens) >= 2:
        add_variant(" ".join(tokens))
    informative_tokens = [token for token in tokens if len(token) > 2]
    if len(informative_tokens) >= 2:
        add_variant(" ".join(informative_tokens))
    if len(informative_tokens) >= 3:
        add_variant(" ".join(informative_tokens[: max(2, len(informative_tokens) // 2 + 1)]))

    return variants[:RAG_QUERY_EXPANSION_MAX_VARIANTS]


def _coerce_similarity_threshold(min_similarity: float | int | str | None) -> float:
    if min_similarity in (None, ""):
        return RAG_SEARCH_MIN_SIMILARITY
    try:
        return max(0.0, min(1.0, float(min_similarity)))
    except (TypeError, ValueError):
        return RAG_SEARCH_MIN_SIMILARITY


def _resolve_source_type_hint(
    category: str | None,
    allowed_source_types: set[str] | list[str] | tuple[str, ...] | None,
) -> str | None:
    if category or allowed_source_types is None:
        return None
    normalized_types = _normalize_allowed_source_types(allowed_source_types)
    if not normalized_types or len(normalized_types) != 1:
        return None
    return next(iter(normalized_types))


def _get_chunk_counts_for_source_keys(source_keys: list[str]) -> dict[str, int]:
    cleaned_keys = [str(source_key or "").strip() for source_key in source_keys if str(source_key or "").strip()]
    if not cleaned_keys:
        return {}

    placeholders = ", ".join("?" for _ in cleaned_keys)
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT source_key, chunk_count FROM rag_documents WHERE source_key IN ({placeholders})",
            cleaned_keys,
        ).fetchall()
    return {str(row["source_key"] or "").strip(): int(row["chunk_count"] or 0) for row in rows}


def _attach_match_context_metadata(matches: list[dict]) -> list[dict]:
    chunk_counts = _get_chunk_counts_for_source_keys([match.get("source_key") for match in matches])
    annotated_matches: list[dict] = []
    for match in matches:
        enriched = dict(match)
        source_key = str(match.get("source_key") or "").strip()
        total_chunks = chunk_counts.get(source_key)
        if total_chunks:
            enriched["total_chunks"] = total_chunks
            chunk_index = match.get("chunk_index")
            try:
                normalized_chunk_index = int(chunk_index)
            except (TypeError, ValueError):
                normalized_chunk_index = None
            enriched["has_more_context"] = bool(
                normalized_chunk_index is not None and normalized_chunk_index < max(0, int(total_chunks) - 1)
            )
        annotated_matches.append(enriched)
    return annotated_matches


def _attach_tool_memory_expiry_warnings(matches: list[dict]) -> list[dict]:
    warning_threshold = int(time.time()) + 3_600
    annotated_matches: list[dict] = []
    for match in matches:
        enriched = dict(match)
        expires_at_ts = match.get("_expires_at_ts")
        if isinstance(expires_at_ts, int) and expires_at_ts <= warning_threshold:
            enriched["expiry_warning"] = "Expires within 1 hour"
        annotated_matches.append(enriched)
    return annotated_matches


def _finalize_match_payload(matches: list[dict]) -> list[dict]:
    finalized_matches: list[dict] = []
    for match in matches:
        cleaned = dict(match)
        cleaned.pop("_expires_at_ts", None)
        finalized_matches.append(cleaned)
    return finalized_matches


def _coerce_hit_timestamp(metadata: dict | None) -> int | None:
    source = metadata if isinstance(metadata, dict) else {}
    for key in ("indexed_at_ts", "created_at_ts"):
        value = source.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            normalized = int(value)
            if normalized > 0:
                return normalized
            continue
        text = str(value or "").strip()
        if not text:
            continue
        try:
            normalized = int(float(text))
        except (TypeError, ValueError):
            continue
        if normalized > 0:
            return normalized
    return None


def _apply_temporal_decay(similarity: float | None, metadata: dict | None) -> float | None:
    if similarity is None:
        return None

    source = metadata if isinstance(metadata, dict) else {}
    category = normalize_rag_category(source.get("category"), default=source.get("source_type"))
    if category not in DYNAMIC_RAG_CATEGORIES:
        return round(float(similarity), 4)

    timestamp = _coerce_hit_timestamp(source)
    if timestamp is None:
        return round(float(similarity), 4)

    days_old = max(0.0, (time.time() - timestamp) / 86_400)
    boost = 1.0 + (RAG_TEMPORAL_DECAY_ALPHA * math.exp(-RAG_TEMPORAL_DECAY_LAMBDA * days_old))
    return round(min(1.0, float(similarity) * boost), 4)


def _dedupe_rag_hits(hits: list[dict]) -> list[dict]:
    deduped: dict[str, dict] = {}
    ordered_keys: list[str] = []
    for hit in hits:
        metadata = hit.get("metadata") if isinstance(hit.get("metadata"), dict) else {}
        dedupe_key = str(hit.get("id") or metadata.get("source_key") or hit.get("text") or "").strip()
        if not dedupe_key:
            continue
        current = deduped.get(dedupe_key)
        if current is None:
            deduped[dedupe_key] = hit
            ordered_keys.append(dedupe_key)
            continue
        current_similarity = current.get("similarity")
        incoming_similarity = hit.get("similarity")
        if isinstance(incoming_similarity, (int, float)) and (
            not isinstance(current_similarity, (int, float)) or incoming_similarity > current_similarity
        ):
            deduped[dedupe_key] = hit
    return [deduped[key] for key in ordered_keys]


def _apply_source_diversity_limit(matches: list[dict]) -> list[dict]:
    per_source_limit = max(1, int(RAG_MAX_CHUNKS_PER_SOURCE))
    if per_source_limit <= 0:
        return matches

    limited_matches: list[dict] = []
    source_counts: dict[str, int] = {}
    for match in matches:
        source_key = str(match.get("source_key") or match.get("source_name") or "").strip()
        if not source_key:
            limited_matches.append(match)
            continue
        source_count = source_counts.get(source_key, 0)
        if source_count >= per_source_limit:
            continue
        source_counts[source_key] = source_count + 1
        limited_matches.append(match)
    return limited_matches


def _query_rag_hits(
    query: str,
    top_k: int,
    category: str | None = None,
    *,
    allowed_source_types: set[str] | list[str] | tuple[str, ...] | None = None,
    expand_query: bool = True,
) -> list[dict]:
    collected_hits: list[dict] = []
    requested_top_k = max(1, int(top_k))
    candidate_top_k = max(requested_top_k, requested_top_k * max(2, int(RAG_MAX_CHUNKS_PER_SOURCE)))
    normalized_query = re.sub(r"\s+", " ", str(query or "").strip())
    variants = _expand_query_variants(normalized_query) if expand_query else ([normalized_query] if normalized_query else [])
    source_type_hint = _resolve_source_type_hint(category, allowed_source_types)
    for variant in variants:
        collected_hits.extend(
            rag_query_chunks(
                variant,
                top_k=candidate_top_k,
                category=category,
                source_type_hint=source_type_hint,
            )
        )
    return _dedupe_rag_hits(collected_hits)


def _query_auto_injected_rag_hits(
    query: str,
    top_k: int,
    threshold: float,
    allowed_source_types: set[str] | list[str] | tuple[str, ...] | None = None,
) -> list[dict]:
    normalized_top_k = max(1, int(top_k))
    base_hits = _query_rag_hits(
        query,
        top_k=normalized_top_k,
        allowed_source_types=allowed_source_types,
        expand_query=False,
    )
    base_matches = _normalize_rag_hits(
        query,
        base_hits,
        threshold,
        allowed_source_types=allowed_source_types,
        auto_inject_only=True,
    )
    strong_threshold = min(1.0, float(threshold) + AUTO_INJECT_STRONG_MATCH_MARGIN)
    strong_match_count = sum(
        1
        for match in base_matches
        if isinstance(match.get("similarity"), (int, float)) and float(match["similarity"]) >= strong_threshold
    )
    if strong_match_count >= (1 if normalized_top_k == 1 else 2):
        return base_hits
    return _query_rag_hits(query, top_k=normalized_top_k, allowed_source_types=allowed_source_types)


def _compact_auto_injected_rag_match(match: dict) -> dict | None:
    if not isinstance(match, dict):
        return None
    excerpt = _clip_rag_excerpt(match.get("text", ""), limit=AUTO_INJECT_EXCERPT_LIMIT)
    if not excerpt:
        return None
    source_name = str(match.get("source_name") or match.get("source_type") or "Knowledge base").strip() or "Knowledge base"
    compact_match = {
        "source_name": source_name,
        "text": excerpt,
    }
    similarity = match.get("similarity")
    if isinstance(similarity, (int, float)):
        compact_match["similarity"] = round(float(similarity), 4)
    if match.get("archived_conversation") is True:
        compact_match["archived_conversation"] = True
        compact_match["source_key"] = str(match.get("source_key") or "").strip() or None
    archived_message_count = match.get("archived_message_count")
    if isinstance(archived_message_count, (int, float)) and int(archived_message_count) > 0:
        compact_match["archived_message_count"] = int(archived_message_count)
    return compact_match


def _normalize_rag_hits(
    query: str,
    hits: list[dict],
    threshold: float,
    *,
    allowed_source_types: set[str] | list[str] | tuple[str, ...] | None = None,
    auto_inject_only: bool = False,
) -> list[dict]:
    del query
    allowed_types = _normalize_allowed_source_types(allowed_source_types)
    matches = []
    for hit in hits:
        metadata = hit.get("metadata") or {}
        similarity = _apply_temporal_decay(hit.get("similarity"), metadata)
        if similarity is not None and similarity < threshold:
            continue
        source_type = normalize_category(metadata.get("source_type"))
        if source_type not in RAG_SUPPORTED_SOURCE_TYPES:
            continue
        if allowed_types is not None and source_type not in allowed_types:
            continue
        if auto_inject_only and not _coerce_metadata_bool(metadata, "auto_inject_enabled", default=True):
            continue
        expires_at_ts = _coerce_optional_timestamp(metadata.get("expires_at_ts"))
        matches.append(
            {
                "id": hit.get("id"),
                "source_key": metadata.get("source_key"),
                "source_name": metadata.get("source_name"),
                "source_type": source_type,
                "category": normalize_rag_category(metadata.get("category"), default=source_type),
                "chunk_index": metadata.get("chunk_index"),
                "archived_conversation": metadata.get("archived_conversation") is True,
                "archived_message_count": int(metadata.get("archived_message_count") or 0) if metadata.get("archived_message_count") not in (None, "") else 0,
                "_expires_at_ts": expires_at_ts,
                "expires_at_utc": _format_utc_timestamp(expires_at_ts),
                "similarity": round(float(similarity), 4) if similarity is not None else None,
                "text": _clip_rag_excerpt(hit.get("text", "")),
            }
        )
    matches.sort(key=lambda item: float(item.get("similarity") or 0.0), reverse=True)
    return _apply_source_diversity_limit(matches)


def search_knowledge_base_tool(
    query: str,
    category: str | None = None,
    top_k: int = RAG_SEARCH_DEFAULT_TOP_K,
    allowed_source_types: set[str] | list[str] | tuple[str, ...] | None = None,
    min_similarity: float | int | str | None = None,
) -> dict:
    _require_rag_enabled()
    query = str(query or "").strip()
    if not query:
        return {"query": "", "matches": [], "count": 0}

    ensure_supported_rag_sources()
    normalized_category = normalize_rag_category(category, default=None) if category else None
    similarity_threshold = _coerce_similarity_threshold(min_similarity)
    hits = _query_rag_hits(
        query,
        top_k=top_k,
        category=normalized_category,
        allowed_source_types=allowed_source_types,
    )
    matches = _normalize_rag_hits(
        query,
        hits,
        similarity_threshold,
        allowed_source_types=allowed_source_types,
    )
    matches = _attach_match_context_metadata(matches)
    matches = _finalize_match_payload(matches)
    return {
        "query": query,
        "category": normalized_category,
        "min_similarity": similarity_threshold,
        "count": len(matches[: max(1, int(top_k))]),
        "matches": matches[: max(1, int(top_k))],
    }


def upsert_tool_memory_result(tool_name: str, args_preview: str, result_content: str, summary: str = "") -> dict | None:
    _require_rag_enabled()
    cleaned_content = _sanitize_tool_result_text(result_content)
    if not cleaned_content:
        return None

    cleaned_tool_name = normalize_category(tool_name) or "tool"
    cleaned_args_preview = _clean_rag_text_block(args_preview, limit=300)
    cleaned_summary = _clean_rag_text_block(summary, limit=300)
    args_hash = _tool_memory_args_hash(cleaned_args_preview)
    source_key = build_tool_memory_source_key(cleaned_tool_name, args_hash)
    source_name = cleaned_tool_name if not cleaned_args_preview else f"{cleaned_tool_name}: {cleaned_args_preview[:80]}"
    expires_at_ts = int(time.time()) + _tool_memory_ttl_seconds(cleaned_tool_name)
    expires_at = _format_utc_timestamp(expires_at_ts)

    record_parts = [f"tool:{cleaned_tool_name}"]
    if cleaned_args_preview:
        record_parts.append(f"Input: {cleaned_args_preview}")
    if cleaned_summary:
        record_parts.append(f"Summary: {cleaned_summary}")
    record_parts.append(cleaned_content)
    records = [{"role": "tool_memory", "content": "\n".join(record_parts)}]
    metadata = {
        "source_key": source_key,
        "tool_name": cleaned_tool_name,
        "args_preview": cleaned_args_preview,
        "summary": cleaned_summary,
        "source_type": RAG_SOURCE_TOOL_MEMORY,
        "expires_at_ts": expires_at_ts,
    }
    chunks = chunks_from_records(
        records,
        source_name=source_name,
        source_type=RAG_SOURCE_TOOL_MEMORY,
        category=CATEGORY_TOOL_MEMORY,
        metadata=metadata,
    )
    if not chunks:
        return None
    return ingest_rag_chunks(
        source_key=source_key,
        source_name=source_name,
        source_type=RAG_SOURCE_TOOL_MEMORY,
        category=CATEGORY_TOOL_MEMORY,
        chunks=chunks,
        metadata=metadata,
        expires_at=expires_at,
    )


def search_tool_memory(
    query: str,
    top_k: int = RAG_SEARCH_DEFAULT_TOP_K,
    min_similarity: float | int | str | None = None,
) -> dict:
    _require_rag_enabled()
    query = str(query or "").strip()
    if not query:
        return {"query": "", "count": 0, "matches": []}

    ensure_supported_rag_sources()
    similarity_threshold = _coerce_similarity_threshold(min_similarity)
    hits = _query_rag_hits(query, top_k=top_k, category=CATEGORY_TOOL_MEMORY)
    matches = _normalize_rag_hits(query, hits, similarity_threshold)
    matches = _attach_match_context_metadata(matches)
    matches = _attach_tool_memory_expiry_warnings(matches)
    matches = _finalize_match_payload(matches)
    return {
        "query": query,
        "category": CATEGORY_TOOL_MEMORY,
        "min_similarity": similarity_threshold,
        "count": len(matches[: max(1, int(top_k))]),
        "matches": matches[: max(1, int(top_k))],
    }


def get_exact_tool_memory_match(tool_name: str, args_preview: str) -> dict | None:
    _require_rag_enabled()
    cleaned_tool_name = normalize_category(tool_name)
    cleaned_args_preview = _clean_rag_text_block(args_preview, limit=300)
    if not cleaned_tool_name or not cleaned_args_preview:
        return None

    ensure_supported_rag_sources()
    source_key = build_tool_memory_source_key(cleaned_tool_name, _tool_memory_args_hash(cleaned_args_preview))
    record = get_rag_document_record(source_key)
    if not record:
        return None

    rows = rag_get_source_chunks(source_key, category=CATEGORY_TOOL_MEMORY)
    if not rows:
        return None

    content = "\n\n".join(_clean_rag_text_block(row.get("text") or "") for row in rows if _clean_rag_text_block(row.get("text") or ""))
    if not content:
        return None

    metadata = parse_rag_metadata(record["metadata"])
    return {
        "source_key": str(record["source_key"] or "").strip(),
        "source_name": str(record["source_name"] or "").strip(),
        "tool_name": cleaned_tool_name,
        "args_preview": cleaned_args_preview,
        "summary": str(metadata.get("summary") or "").strip(),
        "content": content,
        "expires_at": str(record["expires_at"] or "").strip(),
    }


def build_tool_memory_auto_context(query: str, top_k: int) -> str | None:
    query = str(query or "").strip()
    if not query:
        return None
    try:
        results = search_tool_memory(query, top_k=max(1, int(top_k)))
    except Exception:
        return None

    matches = results.get("matches") or []
    if not matches:
        return None

    sections = []
    for match in matches:
        source_name = str(match.get("source_name") or "Tool memory").strip()
        similarity = match.get("similarity")
        similarity_text = f"{float(similarity):.2f}" if isinstance(similarity, (int, float)) else "n/a"
        excerpt = _clip_rag_excerpt(match.get("text", ""), limit=1000)
        if excerpt:
            sections.append(f"Source: {source_name}\nSimilarity: {similarity_text}\n{excerpt}")
    if not sections:
        return None
    return "\n\n".join(sections)


def _build_compact_clarification_rag_text(content: str, metadata: dict | None) -> str:
    clarification_response = extract_clarification_response(metadata)
    answers = clarification_response.get("answers") if isinstance(clarification_response, dict) else None
    if not isinstance(answers, dict) or not answers:
        return build_user_message_for_model(content, metadata)

    query_parts: list[str] = []
    seen_parts: set[str] = set()

    for line in str(content or "").splitlines():
        match = re.match(r"^\s*A:\s*(.+?)\s*$", line)
        if not match:
            continue
        normalized_display = " ".join(match.group(1).split())
        if not normalized_display:
            continue
        dedupe_key = normalized_display.casefold()
        if dedupe_key in seen_parts:
            continue
        seen_parts.add(dedupe_key)
        query_parts.append(normalized_display)

    if not query_parts:
        for answer in answers.values():
            if not isinstance(answer, dict):
                continue
            normalized_display = " ".join(str(answer.get("display") or "").split())
            if not normalized_display:
                continue
            dedupe_key = normalized_display.casefold()
            if dedupe_key in seen_parts:
                continue
            seen_parts.add(dedupe_key)
            query_parts.append(normalized_display)

    return " ".join(query_parts).strip() or build_user_message_for_model(content, metadata)


def build_rag_auto_context(
    query: str,
    enabled: bool,
    threshold: float,
    top_k: int,
    exclude_source_keys: set[str] | None = None,
    allowed_source_types: set[str] | list[str] | tuple[str, ...] | None = None,
) -> dict | None:
    query = str(query or "").strip()
    if not RAG_ENABLED or not enabled or not query:
        return None
    try:
        ensure_supported_rag_sources()
        normalized_top_k = max(1, int(top_k))
        hits = _query_auto_injected_rag_hits(
            query,
            top_k=normalized_top_k,
            threshold=max(0.0, min(1.0, float(threshold))),
            allowed_source_types=allowed_source_types,
        )
    except Exception:
        return None

    matches = _normalize_rag_hits(
        query,
        hits,
        max(0.0, min(1.0, float(threshold))),
        allowed_source_types=allowed_source_types,
        auto_inject_only=True,
    )
    if exclude_source_keys:
        matches = [m for m in matches if m.get("source_key") not in exclude_source_keys]
    if not matches:
        return None

    compact_matches = []
    for match in matches[:normalized_top_k]:
        compact_match = _compact_auto_injected_rag_match(match)
        if compact_match is not None:
            compact_matches.append(compact_match)
    if not compact_matches:
        return None

    return {
        "query": query,
        "count": len(compact_matches),
        "matches": compact_matches,
    }


def ingest_uploaded_rag_document(
    filename: str,
    text: str,
    *,
    source_name: str | None = None,
    description: str = "",
    auto_inject_enabled: bool = True,
) -> dict:
    _require_rag_enabled()
    cleaned_filename = os.path.basename(str(filename or "").strip())[:255] or "uploaded.txt"
    cleaned_source_name = _clean_rag_text_block(source_name or cleaned_filename, limit=120) or cleaned_filename
    cleaned_description = _clean_rag_text_block(description, limit=MANUAL_UPLOAD_DESCRIPTION_LIMIT)
    cleaned_text = _clean_rag_text_block(text)
    if not cleaned_text:
        raise ValueError("Uploaded document is empty after text extraction.")

    source_key = build_rag_source_key(RAG_SOURCE_UPLOADED_DOCUMENT, f"{cleaned_source_name}|{cleaned_filename}")
    metadata = {
        "source_key": source_key,
        "title": cleaned_source_name,
        "file_name": cleaned_filename,
        "description": cleaned_description,
        "auto_inject_enabled": bool(auto_inject_enabled),
        "source_type": RAG_SOURCE_UPLOADED_DOCUMENT,
        "created_at_ts": int(time.time()),
    }
    parts = [f"Title: {cleaned_source_name}"]
    if cleaned_filename and cleaned_filename != cleaned_source_name:
        parts.append(f"File: {cleaned_filename}")
    if cleaned_description:
        parts.append(f"Relevance note: {cleaned_description}")
    parts.append(cleaned_text)

    chunks = chunks_from_text(
        text="\n\n".join(parts),
        source_name=cleaned_source_name,
        source_type=RAG_SOURCE_UPLOADED_DOCUMENT,
        category=RAG_SOURCE_UPLOADED_DOCUMENT,
        metadata=metadata,
    )
    if not chunks:
        raise ValueError("Uploaded document did not produce any RAG chunks.")

    return ingest_rag_chunks(
        source_key=source_key,
        source_name=cleaned_source_name,
        source_type=RAG_SOURCE_UPLOADED_DOCUMENT,
        category=RAG_SOURCE_UPLOADED_DOCUMENT,
        chunks=chunks,
        metadata=metadata,
    )


def ingest_rag_chunks(
    source_key: str,
    source_name: str,
    source_type: str,
    category: str,
    chunks: list,
    metadata: dict | None = None,
    expires_at: str | None = None,
) -> dict:
    _require_rag_enabled()
    category = normalize_rag_category(category, default=source_type)
    source_type = normalize_category(source_type)
    if source_type not in RAG_SUPPORTED_SOURCE_TYPES or category not in RAG_SUPPORTED_CATEGORIES:
        raise ValueError("Unsupported RAG source type or category.")
    normalized_metadata = dict(metadata or {})
    normalized_metadata["indexed_at_ts"] = int(time.time())
    for chunk in chunks:
        if hasattr(chunk, "metadata"):
            merged_metadata = dict(getattr(chunk, "metadata", {}) or {})
            merged_metadata.update(normalized_metadata)
            chunk.metadata = merged_metadata
    rag_delete_source(source_key)
    inserted = rag_upsert_chunks(chunks)
    upsert_rag_document_record(
        source_key,
        source_name,
        source_type,
        category,
        inserted,
        metadata=normalized_metadata,
        expires_at=expires_at,
    )
    return {
        "source_key": source_key,
        "source_name": source_name,
        "source_type": source_type,
        "category": category,
        "chunk_count": inserted,
        "metadata": normalized_metadata,
        "expires_at": expires_at,
    }


def ingest_rag_chunks_background(
    app_obj,
    source_key: str,
    source_name: str,
    source_type: str,
    category: str,
    chunks: list,
    metadata: dict | None = None,
    expires_at: str | None = None,
):
    _require_rag_enabled()
    background_app = _resolve_background_app(app_obj)

    def task():
        with background_app.app_context():
            return ingest_rag_chunks(
                source_key=source_key,
                source_name=source_name,
                source_type=source_type,
                category=category,
                chunks=chunks,
                metadata=metadata,
                expires_at=expires_at,
            )

    return _get_rag_background_executor().submit(task)


def get_conversation_records_for_rag(
    conversation_id: int | None = None,
    *,
    conversation_ids: list[int] | tuple[int, ...] | set[int] | None = None,
) -> list[dict]:
    _require_rag_enabled()
    ensure_supported_rag_sources()
    normalized_ids = None
    if conversation_ids is not None:
        normalized_ids = sorted({int(value) for value in conversation_ids})
        if not normalized_ids:
            return []
    with get_db() as conn:
        if normalized_ids is not None:
            placeholders = ", ".join("?" for _ in normalized_ids)
            rows = conn.execute(
                f"SELECT id, title, updated_at FROM conversations WHERE id IN ({placeholders}) ORDER BY updated_at DESC",
                tuple(normalized_ids),
            ).fetchall()
        elif conversation_id is None:
            rows = conn.execute("SELECT id, title, updated_at FROM conversations ORDER BY updated_at DESC").fetchall()
        else:
            rows = conn.execute(
                "SELECT id, title, updated_at FROM conversations WHERE id = ? ORDER BY updated_at DESC",
                (conversation_id,),
            ).fetchall()

        conversations = []
        for row in rows:
            messages = conn.execute(
                "SELECT role, content, metadata, deleted_at FROM messages WHERE conversation_id = ? ORDER BY position, id",
                (row["id"],),
            ).fetchall()
            conversation_messages = []
            tool_messages = []
            archived_messages = []
            for msg in messages:
                role = str(msg["role"] or "").strip()
                metadata = parse_message_metadata(msg["metadata"])
                content = str(msg["content"] or "").strip()
                deleted_at = str(msg["deleted_at"] or "").strip()
                if deleted_at:
                    archived_record = _build_archived_conversation_record(role, content, metadata, deleted_at)
                    if archived_record is not None:
                        archived_messages.append(archived_record)
                    continue
                if role == "user":
                    content = _build_compact_clarification_rag_text(content, metadata)
                if role == "summary" and content:
                    conversation_messages.append({"role": "assistant", "content": content})
                elif role in {"user", "assistant"} and content:
                    conversation_messages.append({"role": role, "content": content})

                for tool_index, tool_result in enumerate(extract_message_tool_results(metadata), start=1):
                    tool_messages.append(
                        {
                            "role": "tool",
                            "content": build_tool_result_record_content(tool_result, tool_index),
                        }
                    )

            conversations.append(
                {
                    "conversation_id": row["id"],
                    "title": row["title"],
                    "updated_at": row["updated_at"],
                    "messages": conversation_messages,
                    "archived_messages": archived_messages,
                    "tool_results": tool_messages,
                }
            )
    return conversations


def _get_conversation_sync_candidates(conversation_id: int | None = None) -> list[dict]:
    with get_db() as conn:
        if conversation_id is None:
            rows = conn.execute("SELECT id, title, updated_at FROM conversations ORDER BY updated_at DESC").fetchall()
        else:
            rows = conn.execute(
                "SELECT id, title, updated_at FROM conversations WHERE id = ? ORDER BY updated_at DESC",
                (conversation_id,),
            ).fetchall()
    return [
        {
            "conversation_id": int(row["id"]),
            "title": str(row["title"] or "").strip(),
            "updated_at": str(row["updated_at"] or "").strip(),
        }
        for row in rows
    ]


def sync_conversations_to_rag(conversation_id: int | None = None, force: bool = False) -> list[dict]:
    _require_rag_enabled()
    ensure_supported_rag_sources()
    synced = []
    sync_plan: list[dict] = []
    for candidate in _get_conversation_sync_candidates(conversation_id):
        conversation_key = conversation_rag_source_key(RAG_SOURCE_CONVERSATION, candidate["conversation_id"])
        archived_conversation_key = conversation_archived_rag_source_key(candidate["conversation_id"])
        tool_key = conversation_rag_source_key(RAG_SOURCE_TOOL_RESULT, candidate["conversation_id"])
        sync_marker = candidate.get("updated_at")
        sync_conversation = _conversation_source_needs_sync(
            conversation_key,
            sync_marker=sync_marker,
            force=force,
        )
        sync_archived_conversation = _conversation_source_needs_sync(
            archived_conversation_key,
            sync_marker=sync_marker,
            force=force,
        )
        sync_tool_results = _conversation_source_needs_sync(
            tool_key,
            sync_marker=sync_marker,
            force=force,
        )
        if sync_conversation or sync_archived_conversation or sync_tool_results:
            sync_plan.append(
                {
                    **candidate,
                    "sync_conversation": sync_conversation,
                    "sync_archived_conversation": sync_archived_conversation,
                    "sync_tool_results": sync_tool_results,
                }
            )

    if not sync_plan:
        return synced

    planned_ids = [int(item["conversation_id"]) for item in sync_plan]
    conversations = get_conversation_records_for_rag(conversation_ids=planned_ids)
    planned_by_id = {int(item["conversation_id"]): item for item in sync_plan}
    for conversation in conversations:
        planned = planned_by_id.get(int(conversation["conversation_id"]))
        if planned is None:
            continue
        conversation_key = conversation_rag_source_key(RAG_SOURCE_CONVERSATION, conversation["conversation_id"])
        conversation_name = _conversation_rag_source_name(
            RAG_SOURCE_CONVERSATION,
            conversation["conversation_id"],
            conversation["title"],
        )
        if planned["sync_conversation"]:
            conversation_signature = _build_rag_sync_signature(
                {
                    "title": conversation["title"],
                    "messages": conversation["messages"],
                }
            )
            conversation_metadata = _build_conversation_sync_metadata(conversation, conversation_key, conversation_signature)
            if conversation["messages"]:
                conversation_chunks = chunks_from_records(
                    conversation["messages"],
                    source_name=conversation_name,
                    source_type=RAG_SOURCE_CONVERSATION,
                    category=RAG_SOURCE_CONVERSATION,
                    metadata=conversation_metadata,
                )
                if conversation_chunks:
                    synced.append(
                        ingest_rag_chunks(
                            source_key=conversation_key,
                            source_name=conversation_name,
                            source_type=RAG_SOURCE_CONVERSATION,
                            category=RAG_SOURCE_CONVERSATION,
                            chunks=conversation_chunks,
                            metadata=conversation_metadata,
                        )
                    )
                else:
                    _delete_rag_source_if_present(conversation_key)
            else:
                _delete_rag_source_if_present(conversation_key)

        archived_conversation_key = conversation_archived_rag_source_key(conversation["conversation_id"])
        archived_conversation_name = _conversation_archived_rag_source_name(
            conversation["conversation_id"],
            conversation["title"],
        )
        if planned["sync_archived_conversation"]:
            archived_signature = _build_rag_sync_signature(
                {
                    "title": conversation["title"],
                    "archived_messages": conversation.get("archived_messages") or [],
                }
            )
            archived_metadata = _build_conversation_sync_metadata(conversation, archived_conversation_key, archived_signature)
            archived_metadata["archived_conversation"] = True
            archived_metadata["archived_message_count"] = len(conversation.get("archived_messages") or [])
            if conversation.get("archived_messages"):
                archived_chunks = chunks_from_records(
                    conversation["archived_messages"],
                    source_name=archived_conversation_name,
                    source_type=RAG_SOURCE_CONVERSATION,
                    category=RAG_SOURCE_CONVERSATION,
                    metadata=archived_metadata,
                )
                if archived_chunks:
                    synced.append(
                        ingest_rag_chunks(
                            source_key=archived_conversation_key,
                            source_name=archived_conversation_name,
                            source_type=RAG_SOURCE_CONVERSATION,
                            category=RAG_SOURCE_CONVERSATION,
                            chunks=archived_chunks,
                            metadata=archived_metadata,
                        )
                    )
                else:
                    _delete_rag_source_if_present(archived_conversation_key)
            else:
                _delete_rag_source_if_present(archived_conversation_key)

        tool_key = conversation_rag_source_key(RAG_SOURCE_TOOL_RESULT, conversation["conversation_id"])
        tool_name = _conversation_rag_source_name(
            RAG_SOURCE_TOOL_RESULT,
            conversation["conversation_id"],
            conversation["title"],
        )
        if planned["sync_tool_results"]:
            tool_signature = _build_rag_sync_signature(
                {
                    "title": conversation["title"],
                    "tool_results": conversation["tool_results"],
                }
            )
            tool_metadata = _build_conversation_sync_metadata(conversation, tool_key, tool_signature)
            if conversation["tool_results"]:
                tool_chunks = chunks_from_records(
                    conversation["tool_results"],
                    source_name=tool_name,
                    source_type=RAG_SOURCE_TOOL_RESULT,
                    category=RAG_SOURCE_TOOL_RESULT,
                    metadata=tool_metadata,
                )
                if tool_chunks:
                    synced.append(
                        ingest_rag_chunks(
                            source_key=tool_key,
                            source_name=tool_name,
                            source_type=RAG_SOURCE_TOOL_RESULT,
                            category=RAG_SOURCE_TOOL_RESULT,
                            chunks=tool_chunks,
                            metadata=tool_metadata,
                        )
                    )
                else:
                    _delete_rag_source_if_present(tool_key)
            else:
                _delete_rag_source_if_present(tool_key)
    return synced


def sync_conversations_to_rag_safe(conversation_id: int | None = None, force: bool = False) -> list[dict]:
    if not RAG_ENABLED:
        return []
    try:
        return sync_conversations_to_rag(conversation_id=conversation_id, force=force)
    except Exception:
        logger.exception("Automatic conversation sync failed", extra={"conversation_id": conversation_id, "force": force})
        return []


def sync_conversations_to_rag_background(app_obj, conversation_id: int | None = None, force: bool = False):
    if not RAG_ENABLED:
        return None
    job_key, should_submit, existing_future = _queue_rag_background_sync_request(conversation_id, force)
    if not should_submit:
        return existing_future
    background_app = _resolve_background_app(app_obj)

    def task():
        latest_result = []
        while True:
            run_force = _start_rag_background_sync_run(job_key)
            with background_app.app_context():
                latest_result = sync_conversations_to_rag_safe(conversation_id=conversation_id, force=run_force)
            if not _finish_rag_background_sync_run(job_key):
                return latest_result

    future = _get_rag_background_executor().submit(task)
    _set_rag_background_sync_future(job_key, future)
    return future
