from __future__ import annotations

import json

from db import get_app_settings
from model_registry import DEFAULT_CHAT_MODEL, canonicalize_model_id, is_valid_model_id as registry_is_valid_model_id


def parse_optional_int(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_messages_payload(raw_value) -> list:
    if isinstance(raw_value, list):
        return raw_value
    if raw_value in (None, ""):
        return []
    try:
        parsed = json.loads(raw_value)
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


def normalize_model_id(value, default: str = DEFAULT_CHAT_MODEL) -> str:
    normalized = canonicalize_model_id(value)
    if normalized:
        return normalized
    normalized_default = canonicalize_model_id(default)
    return normalized_default or DEFAULT_CHAT_MODEL


def is_valid_model_id(model_id: str) -> bool:
    settings = get_app_settings()
    return registry_is_valid_model_id(model_id, settings)