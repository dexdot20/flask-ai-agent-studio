from __future__ import annotations

import json
from typing import Any

PROXY_OPERATION_OPENROUTER = "openrouter"
PROXY_OPERATION_FETCH_URL = "fetch_url"
PROXY_OPERATION_SEARCH_WEB = "search_web"
PROXY_OPERATION_SEARCH_NEWS_DDGS = "search_news_ddgs"
PROXY_OPERATION_SEARCH_NEWS_GOOGLE = "search_news_google"

PROXY_OPERATION_KEYS = (
    PROXY_OPERATION_OPENROUTER,
    PROXY_OPERATION_FETCH_URL,
    PROXY_OPERATION_SEARCH_WEB,
    PROXY_OPERATION_SEARCH_NEWS_DDGS,
    PROXY_OPERATION_SEARCH_NEWS_GOOGLE,
)

# Default to proxying web research only. Provider traffic stays direct unless the user opts in.
DEFAULT_PROXY_ENABLED_OPERATIONS = [
    PROXY_OPERATION_FETCH_URL,
    PROXY_OPERATION_SEARCH_WEB,
    PROXY_OPERATION_SEARCH_NEWS_DDGS,
    PROXY_OPERATION_SEARCH_NEWS_GOOGLE,
]


def normalize_proxy_enabled_operations(raw_value: Any) -> list[str]:
    if raw_value in (None, ""):
        return list(DEFAULT_PROXY_ENABLED_OPERATIONS)

    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
        except Exception:
            return list(DEFAULT_PROXY_ENABLED_OPERATIONS)
    elif isinstance(raw_value, (list, tuple, set)):
        parsed = list(raw_value)
    else:
        return list(DEFAULT_PROXY_ENABLED_OPERATIONS)

    normalized: list[str] = []
    for item in parsed:
        candidate = str(item or "").strip().lower()
        if candidate in PROXY_OPERATION_KEYS and candidate not in normalized:
            normalized.append(candidate)
    return normalized


def is_proxy_operation_enabled(operation: str, raw_value: Any) -> bool:
    return str(operation or "").strip().lower() in normalize_proxy_enabled_operations(raw_value)