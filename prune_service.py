from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import logging
import re
from typing import Any

from config import (
    PRUNE_WEIGHT_ENTROPY,
    PRUNE_WEIGHT_RAG,
    PRUNE_WEIGHT_STALENESS,
    PRUNE_WEIGHT_TOKEN,
    PRUNING_MIN_TARGET_TOKENS,
    PRUNING_TARGET_REDUCTION_RATIO,
    RAG_ENABLED,
    RAG_SOURCE_CONVERSATION,
)
from db import (
    get_app_settings,
    get_conversation_message_rows,
    get_db,
    get_entropy_profile,
    get_entropy_protect_code_blocks_enabled,
    get_entropy_protect_tool_results_enabled,
    get_entropy_reference_boost_enabled,
    get_pruning_min_target_tokens,
    get_pruning_target_reduction_ratio,
    get_rag_source_types,
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
from rag_service import conversation_rag_source_key, search_knowledge_base_tool
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
PRUNE_SCORE_CONTENT_PREVIEW_MAX_CHARS = 260
PRUNE_SCORE_RAG_TOP_K = 4
PRUNE_SCORE_RAG_MIN_SIMILARITY = 0.35
PRUNE_SCORE_RAG_MAX_WORKERS = 4
LOGGER = logging.getLogger(__name__)


class _PruneScoreWeights(dict):
    def __getitem__(self, key):
        normalized_key = "staleness" if str(key) == "recency" else key
        return super().__getitem__(normalized_key)

    def get(self, key, default=None):
        normalized_key = "staleness" if str(key) == "recency" else key
        return super().get(normalized_key, default)


PRUNE_SCORE_WEIGHTS = _PruneScoreWeights(
    {
        "entropy_prunability": PRUNE_WEIGHT_ENTROPY,
        "rag_coverage": PRUNE_WEIGHT_RAG,
        "staleness": PRUNE_WEIGHT_STALENESS,
        "token_weight": PRUNE_WEIGHT_TOKEN,
    }
)


def _normalize_prune_score_weights(weights: dict[str, float]) -> dict[str, float]:
    alias_value = (weights or {}).get("staleness", (weights or {}).get("recency", 0.0))
    normalized = {
        "entropy_prunability": max(0.0, float((weights or {}).get("entropy_prunability") or 0.0)),
        "rag_coverage": max(0.0, float((weights or {}).get("rag_coverage") or 0.0)),
        "staleness": max(0.0, float(alias_value or 0.0)),
        "token_weight": max(0.0, float((weights or {}).get("token_weight") or 0.0)),
    }
    total = sum(normalized.values())
    if total <= 0:
        return _PruneScoreWeights(
            {
            "entropy_prunability": 0.35,
            "rag_coverage": 0.30,
            "staleness": 0.25,
            "token_weight": 0.10,
            }
        )
    return _PruneScoreWeights(
        {
            key: value / total
            for key, value in normalized.items()
        }
    )


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


def _clamp_score(value: float) -> float:
    return max(0.0, min(1.0, float(value or 0.0)))


def _clip_preview_text(text: str, limit: int = PRUNE_SCORE_CONTENT_PREVIEW_MAX_CHARS) -> str:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit].rstrip() + "…"


def _extract_entropy_terms(text: str) -> list[str]:
    return [term.lower() for term in re.findall(r"[A-Za-z0-9_./:-]{3,}", str(text or ""))]


def _extract_entropy_reference_terms(text: str) -> list[str]:
    unique_terms: list[str] = []
    seen_terms: set[str] = set()
    for term in _extract_entropy_terms(text):
        if len(term) < 5 or term.isdigit() or term in seen_terms:
            continue
        seen_terms.add(term)
        unique_terms.append(term)
        if len(unique_terms) >= 8:
            break
    return unique_terms


def _content_contains_code_signal(text: str) -> bool:
    normalized_text = str(text or "")
    return "```" in normalized_text or bool(re.search(r"^\s{4,}\S", normalized_text, re.MULTILINE))


def _content_contains_tool_signal(text: str) -> bool:
    normalized_text = str(text or "")
    return bool(re.search(r"\btool\s*:|\bsummary\s*:|\binput\s*:", normalized_text, re.IGNORECASE))


def _get_prune_entropy_profile_settings(settings: dict | None) -> dict[str, float]:
    profile = get_entropy_profile(settings)
    if profile == "conservative":
        return {
            "lexical_weight": 0.42,
            "structural_weight": 0.34,
            "density_weight": 0.14,
            "reference_weight": 0.10,
        }
    if profile == "aggressive":
        return {
            "lexical_weight": 0.36,
            "structural_weight": 0.28,
            "density_weight": 0.18,
            "reference_weight": 0.18,
        }
    return {
        "lexical_weight": 0.40,
        "structural_weight": 0.30,
        "density_weight": 0.15,
        "reference_weight": 0.15,
    }


def _compute_entropy_score(content: str, *, later_text: str = "", settings: dict | None = None) -> float:
    normalized_content = str(content or "").strip()
    if not normalized_content:
        return 0.0

    terms = _extract_entropy_terms(normalized_content)
    lexical_score = 0.0
    if terms:
        lexical_score = min(1.0, (len(set(terms)) / len(terms)) * 1.4)

    structural_score = 0.0
    if _content_contains_code_signal(normalized_content):
        structural_score += 0.45
    if _content_contains_tool_signal(normalized_content):
        structural_score += 0.22
    if re.search(r"https?://|www\.", normalized_content):
        structural_score += 0.14
    if re.search(r"\b\d[\d.,_:/-]*\b", normalized_content):
        structural_score += 0.12
    if "{" in normalized_content and "}" in normalized_content:
        structural_score += 0.10
    if re.search(r"^[\-*•]\s+", normalized_content, re.MULTILINE):
        structural_score += 0.10
    structural_score = min(1.0, structural_score)

    density_score = min(1.0, max(1, estimate_text_tokens(normalized_content)) / 220.0)

    reference_score = 0.0
    if get_entropy_reference_boost_enabled(settings):
        lowered_later_text = str(later_text or "").lower()
        reference_terms = _extract_entropy_reference_terms(normalized_content)
        if reference_terms and any(term in lowered_later_text for term in reference_terms):
            reference_score = 1.0

    profile_settings = _get_prune_entropy_profile_settings(settings)
    total_weight = sum(profile_settings.values())
    if total_weight <= 0:
        return 0.0

    score = (
        lexical_score * profile_settings["lexical_weight"]
        + structural_score * profile_settings["structural_weight"]
        + density_score * profile_settings["density_weight"]
        + reference_score * profile_settings["reference_weight"]
    ) / total_weight

    if get_entropy_protect_code_blocks_enabled(settings) and _content_contains_code_signal(normalized_content):
        score = max(score, 0.85)
    if get_entropy_protect_tool_results_enabled(settings) and _content_contains_tool_signal(normalized_content):
        score = max(score, 0.72)
    return _clamp_score(score)


def _normalize_rag_query_text(content: str) -> str:
    normalized = re.sub(r"\s+", " ", str(content or "")).strip()
    if len(normalized) <= 1_200:
        return normalized
    return normalized[:1_200].rstrip() + "…"


def _compute_rag_coverage_score_for_query(
    query: str,
    *,
    allowed_source_types: list[str],
    excluded_source_key: str,
    conversation_id: int,
) -> float:
    if not RAG_ENABLED:
        return 0.0

    normalized_query = _normalize_rag_query_text(query)
    if not normalized_query or not allowed_source_types:
        return 0.0

    try:
        result = search_knowledge_base_tool(
            normalized_query,
            top_k=PRUNE_SCORE_RAG_TOP_K,
            allowed_source_types=allowed_source_types,
            min_similarity=PRUNE_SCORE_RAG_MIN_SIMILARITY,
        )
    except Exception:
        LOGGER.exception("Failed to compute prune RAG coverage for conversation %s.", conversation_id)
        return 0.0

    matches = [
        match
        for match in (result.get("matches") if isinstance(result, dict) else []) or []
        if isinstance(match, dict) and str(match.get("source_key") or "").strip() != excluded_source_key
    ]
    if not matches:
        return 0.0

    strongest_similarity = max(
        float(match.get("similarity") or 0.0)
        for match in matches
        if isinstance(match.get("similarity"), (int, float))
    ) if any(isinstance(match.get("similarity"), (int, float)) for match in matches) else 0.0
    threshold = float((result or {}).get("min_similarity") or PRUNE_SCORE_RAG_MIN_SIMILARITY)
    similarity_score = 0.0
    if strongest_similarity > threshold:
        similarity_score = (strongest_similarity - threshold) / max(0.01, 1.0 - threshold)

    unique_sources = {
        str(match.get("source_key") or "").strip()
        for match in matches
        if str(match.get("source_key") or "").strip()
    }
    diversity_bonus = min(0.2, max(0, len(unique_sources) - 1) * 0.05)
    return _clamp_score(similarity_score + diversity_bonus)


def _compute_rag_coverage_score(
    conversation_id: int,
    message_id: int,
    content: str,
    *,
    settings: dict | None = None,
) -> float:
    del message_id
    if not RAG_ENABLED:
        return 0.0

    query = _normalize_rag_query_text(content)
    if not query:
        return 0.0

    allowed_source_types = get_rag_source_types(settings)
    if not allowed_source_types:
        return 0.0

    return _compute_rag_coverage_score_for_query(
        query,
        allowed_source_types=allowed_source_types,
        excluded_source_key=conversation_rag_source_key(RAG_SOURCE_CONVERSATION, conversation_id),
        conversation_id=conversation_id,
    )


def _resolve_prune_score_weights(*, rag_enabled: bool) -> dict[str, float]:
    weights = _normalize_prune_score_weights(PRUNE_SCORE_WEIGHTS)
    if rag_enabled:
        return weights

    redistributed_weight = weights.get("rag_coverage", 0.0)
    weights["rag_coverage"] = 0.0
    recipient_keys = ("entropy_prunability", "staleness")
    recipient_total = sum(weights[key] for key in recipient_keys)
    if recipient_total <= 0 or redistributed_weight <= 0:
        return weights

    for key in recipient_keys:
        weights[key] += redistributed_weight * (weights[key] / recipient_total)
    return weights


def _load_conversation_messages(conversation_id: int) -> list[dict]:
    with get_db() as conn:
        rows = get_conversation_message_rows(conn, conversation_id)
    return [message_row_to_dict(row) for row in rows]


def _normalize_message_id_filter(message_ids: list[int] | tuple[int, ...] | set[int] | None) -> set[int] | None:
    if message_ids is None:
        return None
    normalized_ids: set[int] = set()
    for raw_message_id in message_ids:
        try:
            message_id = int(raw_message_id)
        except (TypeError, ValueError):
            continue
        if message_id > 0:
            normalized_ids.add(message_id)
    return normalized_ids


def score_conversation_messages_for_prune(
    conversation_id: int,
    message_ids: list[int] | tuple[int, ...] | set[int] | None = None,
) -> list[dict]:
    normalized_conversation_id = int(conversation_id or 0)
    if normalized_conversation_id <= 0:
        return []

    settings = get_app_settings()
    filtered_ids = _normalize_message_id_filter(message_ids)
    candidates = [
        message
        for message in sorted(
            _load_conversation_messages(normalized_conversation_id),
            key=lambda message: (int(message.get("position") or 0), int(message.get("id") or 0)),
        )
        if is_prunable_message(message)
        and (filtered_ids is None or int(message.get("id") or 0) in filtered_ids)
    ]
    if not candidates:
        return []

    rag_enabled_for_score = bool(RAG_ENABLED)
    weights = _resolve_prune_score_weights(rag_enabled=rag_enabled_for_score)
    allowed_source_types = get_rag_source_types(settings) if rag_enabled_for_score else []
    excluded_source_key = conversation_rag_source_key(RAG_SOURCE_CONVERSATION, normalized_conversation_id)

    later_text = ""
    later_text_by_message_id: dict[int, str] = {}
    for candidate in reversed(candidates):
        candidate_id = int(candidate.get("id") or 0)
        later_text_by_message_id[candidate_id] = later_text
        candidate_content = str(candidate.get("content") or "").strip()
        if candidate_content:
            later_text = f"{candidate_content}\n{later_text}".strip()

    token_counts = {
        int(candidate.get("id") or 0): max(1, estimate_text_tokens(str(candidate.get("content") or "")))
        for candidate in candidates
    }
    max_tokens = max(token_counts.values(), default=1)
    max_rank = max(1, len(candidates) - 1)
    rag_query_by_message_id: dict[int, str] = {}
    rag_coverage_scores_by_query: dict[str, float] = {}

    if rag_enabled_for_score and allowed_source_types:
        unique_queries: list[str] = []
        for candidate in candidates:
            candidate_id = int(candidate.get("id") or 0)
            normalized_query = _normalize_rag_query_text(str(candidate.get("content") or ""))
            rag_query_by_message_id[candidate_id] = normalized_query
            if normalized_query and normalized_query not in rag_coverage_scores_by_query:
                rag_coverage_scores_by_query[normalized_query] = 0.0
                unique_queries.append(normalized_query)

        if len(unique_queries) == 1:
            only_query = unique_queries[0]
            rag_coverage_scores_by_query[only_query] = _compute_rag_coverage_score_for_query(
                only_query,
                allowed_source_types=allowed_source_types,
                excluded_source_key=excluded_source_key,
                conversation_id=normalized_conversation_id,
            )
        elif unique_queries:
            max_workers = min(PRUNE_SCORE_RAG_MAX_WORKERS, len(unique_queries))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_by_query = {
                    executor.submit(
                        _compute_rag_coverage_score_for_query,
                        query,
                        allowed_source_types=allowed_source_types,
                        excluded_source_key=excluded_source_key,
                        conversation_id=normalized_conversation_id,
                    ): query
                    for query in unique_queries
                }
                for future, query in future_by_query.items():
                    rag_coverage_scores_by_query[query] = future.result()

    scored_candidates: list[dict] = []
    for rank, candidate in enumerate(candidates):
        candidate_id = int(candidate.get("id") or 0)
        candidate_content = str(candidate.get("content") or "")
        estimated_tokens = token_counts.get(candidate_id, 1)
        entropy_score = _compute_entropy_score(
            candidate_content,
            later_text=later_text_by_message_id.get(candidate_id, ""),
            settings=settings,
        )
        rag_coverage_score = (
            rag_coverage_scores_by_query.get(rag_query_by_message_id.get(candidate_id, ""), 0.0)
            if rag_enabled_for_score and allowed_source_types
            else 0.0
        )
        staleness_score = _clamp_score(1.0 - (rank / max_rank))
        token_weight = _clamp_score(estimated_tokens / max_tokens)
        entropy_prunability = _clamp_score(1.0 - entropy_score)
        prune_score = _clamp_score(
            entropy_prunability * weights["entropy_prunability"]
            + rag_coverage_score * weights["rag_coverage"]
            + staleness_score * weights["staleness"]
            + token_weight * weights["token_weight"]
        )
        scored_candidates.append(
            {
                "id": candidate_id,
                "position": int(candidate.get("position") or 0),
                "role": str(candidate.get("role") or "").strip() or "message",
                "content_preview": _clip_preview_text(candidate_content),
                "estimated_tokens": estimated_tokens,
                "entropy_score": round(entropy_score, 4),
                "rag_coverage_score": round(rag_coverage_score, 4),
                "staleness_score": round(staleness_score, 4),
                "recency_score": round(staleness_score, 4),
                "token_weight": round(token_weight, 4),
                "prune_score": round(prune_score, 4),
            }
        )

    scored_candidates.sort(
        key=lambda candidate: (
            float(candidate.get("prune_score") or 0.0),
            int(candidate.get("estimated_tokens") or 0),
            -int(candidate.get("position") or 0),
        ),
        reverse=True,
    )
    return scored_candidates


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

    candidate_ids = [
        int(candidate.get("id") or 0)
        for candidate in score_conversation_messages_for_prune(normalized_conversation_id)[:normalized_batch_size]
        if int(candidate.get("id") or 0) > 0
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
        LOGGER.info("Pruned %d message(s) for conversation_id=%s.", pruned_count, normalized_conversation_id)
    else:
        LOGGER.debug(
            "No messages were pruned for conversation_id=%s; eligible candidates were either absent or failed.",
            normalized_conversation_id,
        )
    return pruned_count