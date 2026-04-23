"""Activity logging service.

Provides a single, normalized entry point for recording every outbound LLM
provider call to the model_invocations Activity log. All call-paths
(agent loop, prune, image, summarize, title generation, …) route through
``log_activity_call`` so the Activity table always contains comparable rows.
"""
from __future__ import annotations

import logging
import time
from typing import Any

LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Response-status constants
# ---------------------------------------------------------------------------
STATUS_OK = "ok"
STATUS_ERROR = "error"
STATUS_STREAM_ERROR = "stream_error"
STATUS_CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Public helper
# ---------------------------------------------------------------------------

def log_activity_call(
    *,
    conversation_id: int,
    provider: str,
    api_model: str,
    operation: str,
    call_type: str = "agent_step",
    request_payload: Any = None,
    response_summary: Any = None,
    response_status: str = STATUS_OK,
    error_type: str | None = None,
    error_message: str | None = None,
    latency_ms: int | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    estimated_input_tokens: int | None = None,
    prompt_cache_hit_tokens: int | None = None,
    prompt_cache_miss_tokens: int | None = None,
    prompt_cache_write_tokens: int | None = None,
    cost: float | None = None,
    assistant_message_id: int | None = None,
    source_message_id: int | None = None,
    step: int = 0,
    call_index: int = 0,
    is_retry: bool = False,
    retry_reason: str | None = None,
    sub_agent_depth: int = 0,
    conn=None,
) -> int | None:
    """Insert a normalized activity record.

    Returns the new row id, or None if logging fails (non-fatal).
    If *conn* is provided the insert runs inside the caller's transaction;
    otherwise a new connection is obtained from ``get_db()``.
    """
    try:
        from db import get_db, insert_model_invocation  # local to avoid circular imports

        kwargs = dict(
            provider=provider,
            api_model=api_model,
            operation=operation,
            call_type=call_type,
            request_payload=request_payload or {},
            response_summary=response_summary or {},
            response_status=response_status,
            error_type=error_type,
            error_message=error_message,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_input_tokens=estimated_input_tokens,
            prompt_cache_hit_tokens=prompt_cache_hit_tokens,
            prompt_cache_miss_tokens=prompt_cache_miss_tokens,
            prompt_cache_write_tokens=prompt_cache_write_tokens,
            cost=cost,
            assistant_message_id=assistant_message_id,
            source_message_id=source_message_id,
            step=step,
            call_index=call_index,
            is_retry=is_retry,
            retry_reason=retry_reason,
            sub_agent_depth=sub_agent_depth,
        )

        if conn is not None:
            return insert_model_invocation(conn, conversation_id, **kwargs)

        with get_db() as _conn:
            return insert_model_invocation(_conn, conversation_id, **kwargs)

    except Exception:
        LOGGER.exception("activity_service: failed to log activity call (non-fatal)")
        return None


def extract_usage_from_response(response) -> dict:
    """Extract token/cost fields from an OpenAI-compat response object."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}

    result: dict = {}
    prompt_tokens = getattr(usage, "prompt_tokens", None)
    completion_tokens = getattr(usage, "completion_tokens", None)
    total_tokens = getattr(usage, "total_tokens", None)
    if prompt_tokens is not None:
        result["prompt_tokens"] = int(prompt_tokens)
    if completion_tokens is not None:
        result["completion_tokens"] = int(completion_tokens)
    if total_tokens is not None:
        result["total_tokens"] = int(total_tokens)

    # MiniMax / Anthropic extended fields (input_tokens → prompt, output_tokens → completion)
    for attr in ("input_tokens", "prompt_tokens"):
        val = getattr(usage, attr, None)
        if val is not None and result.get("prompt_tokens") is None:
            result["prompt_tokens"] = int(val)
            break
    for attr in ("output_tokens", "completion_tokens"):
        val = getattr(usage, attr, None)
        if val is not None and result.get("completion_tokens") is None:
            result["completion_tokens"] = int(val)
            break

    # prompt_tokens_details (OpenAI / DeepSeek cache fields)
    ptd = getattr(usage, "prompt_tokens_details", None)
    if ptd:
        cached = getattr(ptd, "cached_tokens", None)
        if cached is not None:
            result["prompt_cache_hit_tokens"] = int(cached)

    # OpenRouter / DeepSeek extended fields
    for attr in ("cache_read_input_tokens", "cache_hit_tokens"):
        val = getattr(usage, attr, None)
        if val is not None:
            result["prompt_cache_hit_tokens"] = int(val)
            break
    for attr in ("cache_miss_input_tokens", "cache_miss_tokens"):
        val = getattr(usage, attr, None)
        if val is not None:
            result["prompt_cache_miss_tokens"] = int(val)
            break
    for attr in ("cache_creation_input_tokens", "cache_write_tokens"):
        val = getattr(usage, attr, None)
        if val is not None:
            result["prompt_cache_write_tokens"] = int(val)
            break

    return result


class ActivityTimer:
    """Context manager that measures wall-clock latency in milliseconds."""

    def __init__(self) -> None:
        self._start: float = 0.0
        self.elapsed_ms: int = 0

    def __enter__(self) -> "ActivityTimer":
        self._start = time.monotonic()
        return self

    def __exit__(self, *_) -> None:
        self.elapsed_ms = max(0, round((time.monotonic() - self._start) * 1000))
